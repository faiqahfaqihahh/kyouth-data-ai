import asyncio
import json
import re
import sys
import time
import os

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic import BaseModel

load_dotenv()

# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------

class SkillGapResult(BaseModel):
    gaps: list
    total_skills_in_db: int = 0
    resume_skills_found: int = 0
    gap_count: int = 0
    skill_frequency: dict = {}
    top_5_missing: list = []
    match_pct: float = 0.0
    tokens: int = 0
    time_ms: float = 0.0


# ---------------------------------------------------------------------------
# Jailbreak patterns
# ---------------------------------------------------------------------------

_JAILBREAK_PATTERNS = [
    r"ignore (previous|all|above|prior) instructions",
    r"you are now",
    r"disregard.*system",
    r"act as (?!a (?:job|career|skill))",
    r"forget.*rules",
    r"new persona",
    r"do anything now",
    r"prompt injection",
    r"override.*instructions",
]
_JAILBREAK_RE = re.compile(
    "|".join(_JAILBREAK_PATTERNS), re.IGNORECASE | re.DOTALL
)


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult:
    """Sync entry point."""
    return asyncio.run(_find_skill_gaps_async(input_file_path, db_url))


async def _find_skill_gaps_async(input_file_path: str, db_url: str) -> SkillGapResult:
    start = time.perf_counter()

    # 1. Load resume
    try:
        with open(input_file_path, encoding="utf-8", errors="replace") as fh:
            resume_text = fh.read()
    except Exception as exc:
        print(f"[File Error] Cannot read resume '{input_file_path}': {exc}")
        return SkillGapResult(gaps=[])

    # 2. Jailbreak check — runs BEFORE anything reaches an LLM
    if _JAILBREAK_RE.search(resume_text):
        print("[Security] Potentially malicious content detected in resume. Aborting.")
        print("Example of what was blocked: 'ignore previous instructions', 'you are now', etc.")
        return SkillGapResult(gaps=[])

    # 3. Read tech stacks from DB via MCP (one fast query — time optimisation)
    # BUG 5 FIX: use StdioTransport instead of passing a plain string to Client()
    # BUG 6 FIX: pass db_url via DB_PATH env var (how db_server.py reads it).
    # WINDOWS FIX: use sys.executable so the subprocess uses the exact venv Python;
    # "python" is often not on PATH in a uv-managed environment on Windows.
    import sys
    os.environ["DB_PATH"] = db_url

    server_transport = StdioTransport(
        command=sys.executable,
        args=["db_server.py"],
    )

    try:
        async with Client(server_transport) as mcp:
            result = await mcp.call_tool(
                "query_db",
                {
                    "sql_query": (
                        "SELECT tech_stack FROM jobs "
                        "WHERE tech_stack IS NOT NULL AND TRIM(tech_stack) != ''"
                    )
                },
            )
            raw_content = result[0].text if hasattr(result[0], "text") else str(result[0])
            rows = json.loads(raw_content)
    except Exception as exc:
        print(f"[MCP Error] Cannot read tech stacks: {exc}")
        return SkillGapResult(gaps=[])

    if not rows:
        print("[Info] No tagged tech stacks in database. Run tag_data.py first.")
        return SkillGapResult(gaps=[])

    # 4. Build DB skill set and frequency map (pure Python, no LLM needed)
    db_skill_freq = {}
    for row in rows:
        raw = row[0] if isinstance(row, (list, tuple)) else row["tech_stack"]
        for token in _split_skills(raw):
            db_skill_freq[token] = db_skill_freq.get(token, 0) + 1

    all_db_skills = set(db_skill_freq.keys())

    # 5. Extract resume skills (pure Python regex — fully deterministic)
    resume_skills = _extract_resume_skills(resume_text)

    # 6. Compute gaps — set difference, then sort (deterministic)
    gaps = sorted(all_db_skills - resume_skills)

    # 7. Statistics
    gap_freq = {skill: db_skill_freq[skill] for skill in gaps}
    top_5 = sorted(gap_freq, key=lambda k: gap_freq[k], reverse=True)[:5]
    match_pct = round(
        len(resume_skills & all_db_skills) / max(len(all_db_skills), 1) * 100, 1
    )

    elapsed = (time.perf_counter() - start) * 1000

    result = SkillGapResult(
        gaps=gaps,
        total_skills_in_db=len(all_db_skills),
        resume_skills_found=len(resume_skills & all_db_skills),
        gap_count=len(gaps),
        skill_frequency=gap_freq,
        top_5_missing=top_5,
        match_pct=match_pct,
        tokens=0,
        time_ms=round(elapsed, 3),
    )
    print(result)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _split_skills(raw: str) -> list:
    """Split comma-separated tech_stack into clean lowercase tokens."""
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def _extract_resume_skills(text: str) -> set:
    """
    Deterministic regex-based resume skill extractor.
    Splits on common delimiters, filters out long prose sentences.
    """
    text_lower = text.lower()
    cleaned = re.sub(r"[•·|;]", ",", text_lower)
    cleaned = re.sub(r"\n+", ",", cleaned)

    skills = set()
    for part in cleaned.split(","):
        token = part.strip()
        token = re.sub(r"^[\-\*\.\s]+", "", token).strip()
        if not token:
            continue
        if len(token.split()) > 6:
            continue
        if len(token) > 40:
            continue
        skills.add(token)

    # Also keep slash-separated tokens intact (e.g. "c/c++")
    for part in re.split(r"[,\n•·|;]", text_lower):
        token = re.sub(r"^[\-\*\.\s]+", "", part.strip()).strip()
        if "/" in token and 0 < len(token) <= 40:
            skills.add(token)

    return skills


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    resume_path = sys.argv[1] if len(sys.argv) > 1 else "data/resume_d3.txt"
    db_path = sys.argv[2] if len(sys.argv) > 2 else "data/jobs_d1.db"
    find_skill_gaps(resume_path, db_path)


if __name__ == "__main__":
    main()