"""
find_skill_gaps.py

Reads a resume text file, queries the tagged jobs database, and returns
the technical skills present in the job market that the resume is missing.

Determinism strategy:
  - temperature=0 on every Gemini call
  - Structured JSON output via response_schema (no free-text parsing)
  - All output sorted + lowercased before returning

Usage:
    uv run find_skill_gaps.py
    uv run find_skill_gaps.py data/resume.txt data/jobs_d1.db
"""

import os
import sys
import re
import time
import sqlite3
import json
from typing import List
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


# ── Pydantic models ───────────────────────────────────────────────────────────

class SkillGapResult(BaseModel):
    gaps: List[str]
    tokens_used: int  = 0
    elapsed_ms:  float = 0.0
    # Bonus: demand statistics
    skill_demand: dict = {}   # {skill: number_of_jobs_requiring_it}
    top_demanded: List[str] = []  # top 5 gap skills by demand


# ── configuration ─────────────────────────────────────────────────────────────

MODEL        = "gemini-2.5-flash"
MAX_ATTEMPTS = 3
RETRY_DELAY  = 1   # seconds


# ── jailbreak / input sanitisation ────────────────────────────────────────────

_JAILBREAK_PATTERNS = re.compile(
    r"ignore\s+(all\s+)?previous\s+instructions"
    r"|disregard\s+(your\s+)?instructions"
    r"|you\s+are\s+now\s+(?:a\s+)?(?:dan|jailbreak|evil|unrestricted)"
    r"|act\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?(?:an?\s+)?(?:unrestricted|evil|jailbreak)"
    r"|reveal\s+(your\s+)?(system\s+)?prompt"
    r"|print\s+(your\s+)?(system\s+)?prompt"
    r"|override\s+(your\s+)?(?:safety|guidelines|instructions)"
    r"|do\s+anything\s+now"
    r"|forget\s+(that\s+)?you\s+are",
    re.IGNORECASE,
)

def _sanitise(text: str) -> str:
    """Raise ValueError if jailbreak patterns detected; strip XML/code fences."""
    if _JAILBREAK_PATTERNS.search(text):
        raise ValueError("[Security] Jailbreak pattern detected in input. Aborting.")
    # Remove system-prompt-style XML tags and markdown code fences
    text = re.sub(r"<\s*/?system\s*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```[\s\S]*?```", "", text)
    return text.strip()


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_client():
    from google import genai
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("API key not found. Set GOOGLE_API_KEY in your .env file.")
    return genai.Client(api_key=api_key)


def _load_market_skills(db_url: str) -> tuple[list[str], dict[str, int]]:
    """Return (sorted_unique_skills, {skill: job_count})."""
    conn = sqlite3.connect(db_url)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT tech_stack FROM jobs "
            "WHERE tech_stack IS NOT NULL AND tech_stack != ''"
        )
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


# ── main function ─────────────────────────────────────────────────────────────

def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    """
    Compare resume skills against the market and return what is missing.

    Parameters
    ----------
    input_file_path : str  – path to the resume .txt file
    db_url          : str  – path to the SQLite database

    Returns SkillGapResult with:
      gaps         – sorted, lowercase list of missing skills
      tokens_used  – total tokens consumed
      elapsed_ms   – wall-clock time in ms
      skill_demand – {skill: job_count} for each gap skill
      top_demanded – top 5 gap skills by demand
    """
    start = time.time()
    total_tokens = 0

    # 1. Read & sanitise resume
    try:
        with open(input_file_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()
    except Exception as e:
        print(f"[File Error] Cannot read '{input_file_path}': {e}", file=sys.stderr)
        return SkillGapResult(gaps=[])

    try:
        resume_text = _sanitise(raw)
    except ValueError as e:
        print(e, file=sys.stderr)
        return SkillGapResult(gaps=[])

    # 2. Load market skills from DB
    try:
        market_skills, skill_count = _load_market_skills(db_url)
    except Exception as e:
        print(f"[DB Error] {e}", file=sys.stderr)
        return SkillGapResult(gaps=[])

    if not market_skills:
        print("[Warning] No tech stacks in DB. Run tag_data.py first.", file=sys.stderr)
        return SkillGapResult(gaps=[])

    # 3. Get Gemini client
    try:
        from google.genai import types
        client = _get_client()
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
        return SkillGapResult(gaps=[])

    # 4. Ask Gemini to find skill gaps (with retry)
    prompt = (
        "You are a technical recruitment scanner. Find skill gaps.\n\n"
        "Task: identify which Required Market Skills are MISSING from the Resume.\n"
        "Rules:\n"
        "- Output must be lowercase and sorted alphabetically.\n"
        "- Ignore soft skills, languages, certifications.\n"
        "- Be exact: if 'python' is in the resume, do NOT list it as a gap.\n"
        "- Return only a JSON object with key 'gaps' containing a list of strings.\n\n"
        f"Resume:\n{resume_text}\n\n"
        f"Required Market Skills:\n{json.dumps(market_skills)}"
    )

    result_obj: SkillGapResult | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=SkillGapResult,
                    temperature=0.0,  # determinism
                ),
            )

            if response.usage_metadata:
                total_tokens += response.usage_metadata.total_token_count or 0
            else:
                total_tokens += len(prompt.split()) * 4 + len(response.text.split()) * 4

            parsed = SkillGapResult.model_validate_json(response.text)
            # Enforce lowercase + sorted regardless of what model returned
            parsed.gaps = sorted(set(g.strip().lower() for g in parsed.gaps if g.strip()))
            result_obj = parsed
            break

        except Exception as e:
            print(f"Attempt {attempt} failed: {e}")
            if attempt < MAX_ATTEMPTS:
                print(f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)

    if result_obj is None:
        return SkillGapResult(gaps=[])

    # 5. Compute demand statistics for gap skills
    gap_demand = {g: skill_count.get(g, 0) for g in result_obj.gaps}
    top5 = sorted(gap_demand, key=lambda k: gap_demand[k], reverse=True)[:5]

    elapsed = (time.time() - start) * 1000
    result_obj.tokens_used  = total_tokens
    result_obj.elapsed_ms   = round(elapsed, 3)
    result_obj.skill_demand  = gap_demand
    result_obj.top_demanded  = top5

    return result_obj


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    resume_path = sys.argv[1] if len(sys.argv) > 1 else "data/resume.txt"
    db_path     = sys.argv[2] if len(sys.argv) > 2 else "data/jobs_d1.db"

    result = find_skill_gaps(resume_path, db_path)
    print(result)
    print(f"\ntime={result.elapsed_ms:.0f}ms tokens={result.tokens_used}")

    if result.top_demanded:
        print("\n📊 Top demanded skills you're missing:")
        for skill in result.top_demanded:
            print(f"  {skill:30s} — {result.skill_demand.get(skill, 0)} job(s)")