"""
find_skill_gaps.py

Reads a resume text file, queries the tagged jobs database, and returns the
technical skills present in the job market that the resume is missing.

Key design decisions for DETERMINISM:
  - The model outputs a JSON list.
  - We sort + lowercase all skills before returning.
  - Temperature is set to 0 via the Gemini GenerateContentConfig.
  - Skills from the DB are aggregated deterministically (set union, sorted).

Usage:
    uv run find_skill_gaps.py
    uv run find_skill_gaps.py data/resume.txt data/jobs_d1.db
"""

import sys
import re
import time
import json
import sqlite3
import os
from typing import List
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

# ── configuration ─────────────────────────────────────────────────────────────
DEFAULT_RESUME = "data/resources/resume.txt"
DEFAULT_DB     = "data/resources/jobs_d1.db"
MODEL          = "gemini-2.5-flash"
RETRY_LIMIT    = 3
RETRY_DELAY    = 1

# ── Pydantic model ────────────────────────────────────────────────────────────

class SkillGapResult(BaseModel):
    gaps:         List[str]        # sorted, lowercase skill gaps
    tokens_used:  int   = 0        # bonus
    elapsed_ms:   float = 0.0      # bonus
    # Bonus statistics
    skill_demand: dict  = {}       # {skill: job_count} – how many jobs need each gap skill
    top_demanded: List[str] = []   # top 5 gap skills by demand


# ── jailbreak / input sanitisation ────────────────────────────────────────────

_JAILBREAK_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(your\s+)?instructions",
    r"you\s+are\s+now\s+(?:a\s+)?(?:dan|jailbreak|evil|unrestricted)",
    r"act\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?(?:an?\s+)?(?:unrestricted|evil|jailbreak)",
    r"reveal\s+(your\s+)?(system\s+)?prompt",
    r"print\s+(your\s+)?(system\s+)?prompt",
    r"forget\s+(that\s+)?you\s+are",
    r"pretend\s+you\s+(?:are|have\s+no)",
    r"override\s+(your\s+)?(?:safety|guidelines|instructions)",
    r"do\s+anything\s+now",
]
_JAILBREAK_RE = re.compile("|".join(_JAILBREAK_PATTERNS), re.IGNORECASE)


def _sanitise(text: str) -> str:
    """
    Detect jailbreak attempts in user-provided text and raise ValueError.
    This prevents a malicious resume from hijacking the model.
    """
    if _JAILBREAK_RE.search(text):
        raise ValueError(
            "[Security] Jailbreak pattern detected in input file. Aborting."
        )
    # Strip any embedded instruction-like XML / markdown fences
    text = re.sub(r"<\s*/?system\s*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    return text.strip()


# ── DB helpers ─────────────────────────────────────────────────────────────────

def _load_tech_stacks(db_url: str) -> tuple[list[str], dict[str, int]]:
    """
    Read all distinct tech_stack values from the DB.
    Returns:
      - sorted list of unique skills (lowercase)
      - dict of {skill: job_count}
    """
    conn = sqlite3.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute("SELECT tech_stack FROM jobs WHERE tech_stack IS NOT NULL AND tech_stack != ''")
        rows = cur.fetchall()
    finally:
        conn.close()

    skill_count: dict[str, int] = {}
    for (stack,) in rows:
        for skill in stack.split(","):
            s = skill.strip().lower()
            if s:
                skill_count[s] = skill_count.get(s, 0) + 1

    return sorted(skill_count.keys()), skill_count


# ── AI call ────────────────────────────────────────────────────────────────────

def _call_gemini(prompt: str) -> tuple[str, int, int]:
    from google import genai
    from google.genai import types

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set in environment / .env file")
    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0),   # determinism
    )
    text = response.text or ""
    try:
        in_tok  = response.usage_metadata.prompt_token_count     or 0
        out_tok = response.usage_metadata.candidates_token_count or 0
    except Exception:
        in_tok  = len(prompt.split()) * 4
        out_tok = len(text.split())   * 4
    return text, in_tok, out_tok


def _extract_skills_from_resume(resume_text: str) -> tuple[list[str], int, int]:
    """Ask the model to extract technical skills from the resume as a JSON list."""
    prompt = (
        "You are a resume parser. Extract ONLY technical skills from the resume below. "
        "Include: programming languages, frameworks, libraries, cloud platforms, tools, databases. "
        "Exclude: soft skills, certifications, spoken languages, hobbies. "
        "Return ONLY a valid JSON array of lowercase strings. No markdown, no explanation.\n\n"
        "RESUME:\n" + resume_text
    )
    text, in_tok, out_tok = _call_gemini(prompt)
    clean = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    skills = json.loads(clean)
    return [s.strip().lower() for s in skills if isinstance(s, str) and s.strip()], in_tok, out_tok


# ── core function ──────────────────────────────────────────────────────────────

def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    """
    Compare resume skills against the tech stacks in the jobs database and
    return what is missing.

    Parameters
    ----------
    input_file_path : str  – path to the resume text file
    db_url          : str  – path to the SQLite database

    Returns
    -------
    SkillGapResult  – Pydantic model with gaps list and bonus stats
    """
    start_ms    = time.time()
    total_tokens = 0

    # 1. Read and sanitise resume
    try:
        with open(input_file_path, "r", encoding="utf-8", errors="replace") as f:
            raw_resume = f.read()
    except Exception as e:
        print(f"[Error] Cannot read resume file: {e}", file=sys.stderr)
        return SkillGapResult(gaps=[])

    try:
        resume_text = _sanitise(raw_resume)
    except ValueError as e:
        print(e, file=sys.stderr)
        return SkillGapResult(gaps=[])

    # 2. Load job tech stacks from DB
    try:
        all_job_skills, skill_demand = _load_tech_stacks(db_url)
    except Exception as e:
        print(f"[DB Error] {e}", file=sys.stderr)
        return SkillGapResult(gaps=[])

    if not all_job_skills:
        print("[Warning] No tech stacks found in DB. Run tag_data.py first.", file=sys.stderr)
        return SkillGapResult(gaps=[])

    # 3. Extract skills from resume (with retry)
    resume_skills: list[str] = []
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            resume_skills, in_tok, out_tok = _extract_skills_from_resume(resume_text)
            total_tokens += in_tok + out_tok
            break
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Attempt {attempt} failed: {e}")
            if attempt < RETRY_LIMIT:
                print(f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
        except Exception as e:
            print(f"Attempt {attempt} error: {e}", file=sys.stderr)
            if attempt < RETRY_LIMIT:
                time.sleep(RETRY_DELAY)

    # 4. Compute gaps deterministically
    #    A skill is a "gap" if it appears in the job market but NOT in the resume.
    #
    #    Direct-match check: we compare lowercase strings exactly.
    #    E.g. if resume has "c/c++" we check if "c/c++" is in resume_skills —
    #    we do NOT split it into "c" and "c++" unless the DB also stores it that way.
    resume_set = set(resume_skills)
    gaps = sorted(s for s in all_job_skills if s not in resume_set)

    # 5. Bonus statistics – demand for each gap skill
    gap_demand = {g: skill_demand[g] for g in gaps if g in skill_demand}
    top_demanded = sorted(gap_demand, key=lambda k: gap_demand[k], reverse=True)[:5]

    elapsed = (time.time() - start_ms) * 1000
    result = SkillGapResult(
        gaps=gaps,
        tokens_used=total_tokens,
        elapsed_ms=round(elapsed, 3),
        skill_demand=gap_demand,
        top_demanded=top_demanded,
    )
    return result


# ── entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    resume_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RESUME
    db_path     = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_DB

    result = find_skill_gaps(resume_path, db_path)
    print(result)
    print(f"\ntime={result.elapsed_ms:.0f}ms tokens={result.tokens_used}")

    if result.top_demanded:
        print("\n📊 Top demanded skills you're missing:")
        for skill in result.top_demanded:
            demand = result.skill_demand.get(skill, 0)
            print(f"  {skill:30s} — {demand} job(s)")