"""
tag_data.py

Reads job rows from a SQLite database and uses an AI model to populate the
tech_stack column with comma-separated technical skills extracted from the
job description.  Processes rows in batches for efficiency.

Usage:
    uv run tag_data.py
    uv run tag_data.py data/jobs_d1.db          # custom DB path
"""

import sys
import time
import json
import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

# ── configuration ─────────────────────────────────────────────────────────────
DEFAULT_DB = "data/resources/jobs_d1.db"
BATCH_SIZE  = 5          # number of jobs sent to the model in one request
RETRY_LIMIT = 3          # how many times to retry a failed batch
RETRY_DELAY = 2          # seconds to wait between retries

# We use gemini-2.5-flash-lite (free, low latency) for tagging.
# Change to any model from prompt_model.py if you prefer.
TAGGING_MODEL = "gemini-2.5-flash-lite"

# ── helpers ───────────────────────────────────────────────────────────────────

def _get_gemini_client():
    from google import genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set in environment / .env file")
    return genai.Client(api_key=api_key)


def _build_prompt(batch: list[dict]) -> str:
    """
    Build a compact prompt asking the model to extract tech stacks.
    Returns a JSON array so we can parse it reliably.
    """
    jobs_text = "\n\n".join(
        f"JOB_ID: {row['source_id']}\nDESCRIPTION: {row['description'][:1200]}"
        for row in batch
    )
    return (
        "You are a technical recruiter assistant. "
        "For each job below, list ONLY the technical skills / technologies mentioned "
        "(programming languages, frameworks, tools, cloud platforms, databases, etc.). "
        "Do NOT include soft skills, certifications, or job titles. "
        "Return ONLY a valid JSON array of objects with keys 'job_id' and 'tech_stack' "
        "(tech_stack is a comma-separated string). No markdown, no explanation.\n\n"
        + jobs_text
    )


def _parse_response(text: str, batch: list[dict]) -> dict[str, str]:
    """Parse the model JSON response into {job_id: tech_stack} mapping."""
    # Strip possible markdown fences
    clean = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    parsed = json.loads(clean)          # raises json.JSONDecodeError on bad JSON
    result = {}
    for item in parsed:
        jid  = str(item.get("job_id", "")).strip()
        tech = str(item.get("tech_stack", "")).strip()
        if jid:
            result[jid] = tech
    # Validate we got an entry for every job in the batch
    if len(result) != len(batch):
        raise ValueError(
            f"Mismatch between batch size ({len(batch)}) and response ({len(result)})"
        )
    return result


def _call_model(prompt: str) -> tuple[str, int, int]:
    """
    Call the Gemini model.  Returns (response_text, input_tokens, output_tokens).
    """
    from google import genai
    client = _get_gemini_client()
    response = client.models.generate_content(
        model=TAGGING_MODEL,
        contents=prompt,
    )
    text = response.text or ""
    # Token counts (Gemini returns these in usage_metadata)
    try:
        in_tok  = response.usage_metadata.prompt_token_count     or 0
        out_tok = response.usage_metadata.candidates_token_count or 0
    except Exception:
        # Fallback: estimate 4 tokens per word
        in_tok  = len(prompt.split()) * 4
        out_tok = len(text.split())   * 4
    return text, in_tok, out_tok


# ── main function ─────────────────────────────────────────────────────────────

def tag_data(db_url: str) -> tuple[int, float]:
    """
    Populate the tech_stack column for all jobs that currently have NULL / empty
    tech_stack values.

    Parameters
    ----------
    db_url : str  – path to the SQLite database file

    Returns
    -------
    (total_tokens_used, elapsed_ms) – bonus return values
    """
    start_ms = time.time()
    total_tokens = 0

    try:
        if not os.path.exists(db_url):
            print(f"[DB Error] Database file not found: '{db_url}'", file=sys.stderr)
            print("  → Make sure jobs_d1.db is in the data/ folder.", file=sys.stderr)
            return 0, 0.0
        conn = sqlite3.connect(db_url)
        conn.row_factory = sqlite3.Row
    except Exception as e:
        print(f"[DB Error] Cannot open database '{db_url}': {e}", file=sys.stderr)
        return 0, 0.0

    try:
        cur = conn.cursor()
        # Fetch all rows that still need tagging
        cur.execute(
            "SELECT source_id, description FROM jobs "
            "WHERE tech_stack IS NULL OR tech_stack = ''"
        )
        rows = [dict(r) for r in cur.fetchall()]

        if not rows:
            elapsed = (time.time() - start_ms) * 1000
            print("No data to tag")
            print(f"Total tokens used: 0, took {elapsed:.3f}ms")
            conn.close()
            return 0, elapsed

        # Process in batches
        for batch_idx in range(0, len(rows), BATCH_SIZE):
            batch = rows[batch_idx: batch_idx + BATCH_SIZE]
            prompt = _build_prompt(batch)

            result_map = None
            for attempt in range(1, RETRY_LIMIT + 1):
                try:
                    text, in_tok, out_tok = _call_model(prompt)
                    total_tokens += in_tok + out_tok
                    result_map = _parse_response(text, batch)
                    break   # success
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"[Batch {batch_idx // BATCH_SIZE}] Attempt {attempt} failed: {e}")
                    if attempt < RETRY_LIMIT:
                        time.sleep(RETRY_DELAY)
                except Exception as e:
                    print(f"[Batch {batch_idx // BATCH_SIZE}] Attempt {attempt} error: {e}")
                    if attempt < RETRY_LIMIT:
                        time.sleep(RETRY_DELAY)

            if result_map is None:
                print(f"[Batch {batch_idx // BATCH_SIZE}] Skipping after {RETRY_LIMIT} failed attempts")
                continue

            # Write results to DB
            for job in batch:
                jid  = str(job["source_id"])
                tech = result_map.get(jid, "")
                if tech:
                    cur.execute(
                        "UPDATE jobs SET tech_stack = ? WHERE source_id = ?",
                        (tech, jid),
                    )
                    print(f"Analyzed Job {jid}: {tech}")

            conn.commit()

    except Exception as e:
        print(f"[Unexpected Error] {e}", file=sys.stderr)
    finally:
        conn.close()

    elapsed = (time.time() - start_ms) * 1000
    print(f"\nTotal tokens used: {total_tokens}, took {elapsed:.3f}ms")
    return total_tokens, elapsed


# ── entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    tag_data(db_path)