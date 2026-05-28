import asyncio
import os
import re
import time
import json
import sqlite3
from typing import List
from pydantic import BaseModel
from dotenv import load_dotenv
from google import genai

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_RETRIES = 5
RETRY_DELAY = 5.0
BATCH_SIZE = 10

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class SkillStats(BaseModel):
    skill: str
    job_count: int
    demand_pct: float        # % of jobs requiring this skill
    demand_level: str        # "High" / "Medium" / "Low"

class SkillGapResult(BaseModel):
    gaps: List[str]
    tokens: int = 0
    time_ms: float = 0.0
    skill_demand: dict = {}
    statistics: List[SkillStats] = []
    most_wanted: str = ""
    demand_range: str = ""

class DailyQuotaExceededError(Exception):
    pass


# ---------------------------------------------------------------------------
# Jailbreak / input sanitisation
# ---------------------------------------------------------------------------
JAILBREAK_PATTERNS = [
    r"ignore (all |previous |above |prior )?instructions?",
    r"forget (everything|all|your instructions?)",
    r"you are now",
    r"act as (a |an )?",
    r"pretend (you are|to be)",
    r"do anything now",
    r"disregard (your |all )?",
    r"new (role|persona|instructions?|task)",
    r"override",
    r"system prompt",
    r"jailbreak",
    r"<\s*(script|iframe|object|embed)",
    r"\\x[0-9a-f]{2}",
]

def is_jailbreak(text: str) -> bool:
    lower = text.lower()
    for pattern in JAILBREAK_PATTERNS:
        if re.search(pattern, lower):
            return True
    return False


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------
def count_tokens_fallback(text: str) -> int:
    return len(text.split()) * 4


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
EXTRACT_SKILLS_PROMPT = """You are a resume parser. Extract ONLY the technical skills from the resume below.

Rules:
- Include: programming languages, frameworks, tools, platforms, databases, cloud services, DevOps tools
- Exclude: certifications (e.g. CCNA, AWS Certified), soft skills (leadership, management, cooking), spoken languages
- CRITICAL: Preserve compound skills EXACTLY as written. If the resume says "C/C++", output "C/C++" as ONE item. Never split it into "C" and "C++" as two items.
- CRITICAL: Do not alter, expand, or split any skill name. Copy it exactly as it appears.
- Return a JSON array of strings only, no explanation, no markdown fences

Examples of correct behaviour:
- "C, C++" in resume → ["C", "C++"] (two separate items, they were listed separately)
- "C/C++" in resume → ["C/C++"] (one item, slash means combined)

Resume:
{resume}"""


# ---------------------------------------------------------------------------
# Invalid skill filter
# ---------------------------------------------------------------------------
INVALID_SKILLS = {"not specified", "n/a", "none", "not mentioned", "not available"}


# ---------------------------------------------------------------------------
# Parse JSON array safely from model response
# ---------------------------------------------------------------------------
def parse_json_list(text: str) -> List[str]:
    text = text.strip()
    text = re.sub(r"^```[a-z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text)
    text = text.strip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Build demand map: skill -> number of jobs mentioning it
# ---------------------------------------------------------------------------
def build_demand_map(tech_stacks: List[str]) -> dict:
    demand: dict = {}
    for stack in tech_stacks:
        for skill in stack.split(","):
            skill = skill.strip().lower()
            if skill and skill not in INVALID_SKILLS:
                demand[skill] = demand.get(skill, 0) + 1
    return demand


# ---------------------------------------------------------------------------
# Fetch tech stacks directly from SQLite (no MCP)
# ---------------------------------------------------------------------------
def fetch_tech_stacks(db_url: str) -> List[str]:
    with sqlite3.connect(db_url) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tech_stack FROM jobs "
            "WHERE tech_stack IS NOT NULL AND tech_stack != ''"
        )
        rows = cursor.fetchall()
    return [row[0] for row in rows]


# ---------------------------------------------------------------------------
# Gemini call with retry
# ---------------------------------------------------------------------------
async def call_gemini(gemini, prompt: str, label: str) -> tuple:
    """Returns (response_text, tokens_used)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = await gemini.aio.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=prompt,
            )
            response_text = response.text.strip()

            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens = (
                    (response.usage_metadata.prompt_token_count or 0) +
                    (response.usage_metadata.candidates_token_count or 0)
                )
            else:
                tokens = count_tokens_fallback(prompt) + count_tokens_fallback(response_text)

            return response_text, tokens

        except Exception as e:
            error_str = str(e)

            # ── Detect daily quota exhaustion — stop retrying immediately ──
            is_daily_quota = (
                "PerDay" in error_str or
                "per_day" in error_str.lower() or
                "GenerateRequestsPerDay" in error_str
            )

            if "429" in error_str and is_daily_quota:
                raise DailyQuotaExceededError(
                    "Daily API quota exceeded. Please try again tomorrow or check "
                    "your quota at https://ai.dev/rate-limit"
                )

            print(f"Attempt {attempt} failed ({label}): {e}")
            if attempt < MAX_RETRIES:
                match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
                wait = float(match.group(1)) + 2 if match else RETRY_DELAY
                print(f"Retrying in {wait:.0f}s...")
                await asyncio.sleep(wait)
            else:
                raise

# ---------------------------------------------------------------------------
# Build statistics
# ---------------------------------------------------------------------------
def build_statistics(gaps: List[str], demand_map: dict, total_jobs: int) -> tuple:
    stats = []
    counts = [demand_map.get(skill, 0) for skill in gaps]

    if not counts:
        return [], "", ""

    max_count = max(counts)
    high_threshold = max_count * 0.66
    mid_threshold = max_count * 0.33

    for skill, count in zip(gaps, counts):
        pct = round((count / total_jobs) * 100, 1)
        if count >= high_threshold:
            level = "High"
        elif count >= mid_threshold:
            level = "Medium"
        else:
            level = "Low"

        stats.append(SkillStats(
            skill=skill,
            job_count=count,
            demand_pct=pct,
            demand_level=level,
        ))

    stats.sort(key=lambda x: -x.job_count)

    most_wanted = stats[0].skill if stats else ""
    top = stats[0]
    bottom = stats[-1]
    demand_range = (
        f"{top.skill} ({top.job_count} jobs) vs "
        f"{bottom.skill} ({bottom.job_count} jobs)"
    )

    return stats, most_wanted, demand_range


# ---------------------------------------------------------------------------
# Main async logic
# ---------------------------------------------------------------------------
async def _find_skill_gaps_async(input_file_path: str, db_url: str) -> SkillGapResult:
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    gemini = genai.Client(api_key=api_key)

    start_time = time.time()
    total_tokens = 0

    # 1. Read resume
    try:
        with open(input_file_path, "r", encoding="utf-8") as f:
            resume_text = f.read()
    except Exception as e:
        print(f"Failed to read resume: {e}")
        return SkillGapResult(gaps=[])

    # 2. Jailbreak check
    if is_jailbreak(resume_text):
        print("Warning: Potentially malicious content detected in resume. Aborting.")
        return SkillGapResult(gaps=[])

    # 3. Extract candidate skills from resume via Gemini
    try:
        prompt = EXTRACT_SKILLS_PROMPT.format(resume=resume_text)
        response_text, tokens = await call_gemini(gemini, prompt, "resume extraction")
        total_tokens += tokens
        candidate_skills = [s.strip().lower() for s in parse_json_list(response_text)]
    except DailyQuotaExceededError as e:
        print(f"Quota error: {e}")
        raise   # ← bubble up to app.py so user gets a clear message
    except Exception as e:
        print(f"Could not extract resume skills: {e}")
        return SkillGapResult(gaps=[])

    print(f"Candidate skills: {candidate_skills}")

    # 4. Fetch job tech stacks directly from SQLite
    try:
        tech_stacks = fetch_tech_stacks(db_url)
    except Exception as e:
        print(f"Failed to fetch tech stacks from DB: {e}")
        return SkillGapResult(gaps=[])

    if not tech_stacks:
        print("No tagged jobs found in database.")
        return SkillGapResult(gaps=[])

    demand_map = build_demand_map(tech_stacks)
    all_job_skills = sorted(set(demand_map.keys()))

    # 5. Normalise job skills in batches
    normalised_job_skills: List[str] = []

    for i in range(0, len(all_job_skills), BATCH_SIZE):
        batch = all_job_skills[i:i + BATCH_SIZE]
        norm_prompt = (
            "Normalise these technical skill names to their canonical lowercase form. "
            "Preserve exact compound names (e.g. c/c++, node.js, scikit-learn). "
            "Return a JSON array of strings in the same order, no explanation, no markdown fences.\n\n"
            + json.dumps(batch)
        )
        try:
            response_text, tokens = await call_gemini(
                gemini, norm_prompt, f"normalisation batch {i // BATCH_SIZE}"
            )
            total_tokens += tokens
            normalised_batch = [s.strip().lower() for s in parse_json_list(response_text)]
            normalised_job_skills.extend(normalised_batch)
        except DailyQuotaExceededError as e:
            print(f"Quota error: {e}")
            raise   # ← bubble up immediately, stop all batches
        except Exception as e:
            print(f"Normalisation batch {i // BATCH_SIZE} failed, using raw values: {e}")
            normalised_job_skills.extend(batch)

        await asyncio.sleep(3)

    # 6. Deterministic set subtraction
    candidate_set = set(candidate_skills)
    job_skill_set = set(normalised_job_skills)
    gaps = sorted(job_skill_set - candidate_set)

    # 7. Demand statistics for gap skills only
    total_jobs = len(tech_stacks)
    statistics, most_wanted, demand_range = build_statistics(gaps, demand_map, total_jobs)
    gap_demand = {s.skill: s.job_count for s in statistics}

    elapsed = (time.time() - start_time) * 1000

    return SkillGapResult(
        gaps=gaps,
        tokens=total_tokens,
        time_ms=round(elapsed, 3),
        skill_demand=gap_demand,
        statistics=statistics,
        most_wanted=most_wanted,
        demand_range=demand_range,
    )


# ---------------------------------------------------------------------------
# Public sync wrapper — matches required signature exactly
# ---------------------------------------------------------------------------
def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    return asyncio.run(_find_skill_gaps_async(input_file_path, db_url))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    result = find_skill_gaps("resources/resume_d3.txt", "resources/jobs_d1.db")

    print(f"\ngaps={result.gaps} time={result.time_ms:.0f} tokens={result.tokens}")
    print(f"Most wanted skill you're missing: {result.most_wanted}")
    print(f"Demand range: {result.demand_range}")

    if result.statistics:
        print("\n--- Skill Gap Statistics ---")
        print(f"{'Skill':<30} {'Jobs':>5}  {'% of Jobs':>10}  {'Demand'}")
        print("-" * 60)
        for s in result.statistics:
            print(f"{s.skill:<30} {s.job_count:>5}  {s.demand_pct:>9}%  {s.demand_level}")