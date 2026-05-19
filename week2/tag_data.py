"""
tag_data.py

Reads untagged job rows from a SQLite database and uses Google Gemini to
populate the tech_stack column with comma-separated technical skills.

Usage:
    uv run tag_data.py
    uv run tag_data.py data/jobs_d1.db
"""

import os
import sys
import time
import sqlite3
import json
from typing import List
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


# ── Pydantic models ───────────────────────────────────────────────────────────

class JobTag(BaseModel):
    source_id: str
    tech_stack: str


class BatchTagResult(BaseModel):
    jobs: List[JobTag]


# ── configuration ─────────────────────────────────────────────────────────────

BATCH_SIZE   = 5     # jobs per API call
MAX_ATTEMPTS = 3     # retries per batch
RETRY_DELAY  = 2     # seconds between retries
MODEL        = "gemini-2.5-flash"


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_client():
    """Return a Gemini client, or raise RuntimeError with a clean message."""
    from google import genai
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "API key not found. Set GOOGLE_API_KEY in your .env file."
        )
    return genai.Client(api_key=api_key)


def _build_prompt(batch_data: list[dict]) -> str:
    """Compact prompt – key token-saving choices:
    - one-sentence role description
    - data inlined as JSON (no per-job repetition of instructions)
    - output schema stated once by example
    """
    return (
        "Extract technical stack for each job. "
        "Return ONLY valid JSON: {\"jobs\":[{\"source_id\":\"...\",\"tech_stack\":\"skill1, skill2\"},...]}. "
        "No markdown, no explanation.\n\n"
        f"Jobs: {json.dumps(batch_data)}"
    )


# ── main function ─────────────────────────────────────────────────────────────

def tag_data(db_url: str) -> tuple[int, float]:
    """
    Populate the tech_stack column for all untagged jobs.

    Parameters
    ----------
    db_url : str  – path to the SQLite database file

    Returns (total_tokens_used, elapsed_ms)
    """
    start = time.time()
    total_tokens = 0

    # ── connect to DB ─────────────────────────────────────────────────────────
    try:
        if not os.path.exists(db_url):
            print(f"[Error] Database file not found: '{db_url}'", file=sys.stderr)
            return 0, 0.0
        conn = sqlite3.connect(db_url)
        cursor = conn.cursor()
    except Exception as e:
        print(f"[DB Error] Cannot open '{db_url}': {e}", file=sys.stderr)
        return 0, 0.0

    # ── fetch untagged rows ───────────────────────────────────────────────────
    try:
        cursor.execute(
            "SELECT source_id, description FROM jobs "
            "WHERE tech_stack IS NULL OR tech_stack = ''"
        )
        untagged = cursor.fetchall()
    except Exception as e:
        print(f"[DB Error] Cannot query jobs: {e}", file=sys.stderr)
        conn.close()
        return 0, 0.0

    if not untagged:
        elapsed = (time.time() - start) * 1000
        print("No data to tag")
        print(f"Total tokens used: 0, took {elapsed:.3f}ms")
        conn.close()
        return 0, elapsed

    # ── get Gemini client (once, fail fast with clean message) ────────────────
    try:
        from google.genai import types
        client = _get_client()
    except Exception as e:
        print(f"[Error] {e}", file=sys.stderr)
        conn.close()
        return 0, 0.0

    # ── process in batches ────────────────────────────────────────────────────
    for batch_idx in range(0, len(untagged), BATCH_SIZE):
        batch = untagged[batch_idx: batch_idx + BATCH_SIZE]
        batch_data = [{"source_id": row[0], "description": row[1][:900]} for row in batch]
        prompt = _build_prompt(batch_data)

        result: BatchTagResult | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=BatchTagResult,
                        temperature=0.0,
                    ),
                )

                # Token counting
                if response.usage_metadata:
                    total_tokens += response.usage_metadata.total_token_count or 0
                else:
                    total_tokens += len(prompt.split()) * 4 + len(response.text.split()) * 4

                parsed = BatchTagResult.model_validate_json(response.text)

                if len(parsed.jobs) != len(batch):
                    raise ValueError(
                        f"Mismatch between batch size ({len(batch)}) and response ({len(parsed.jobs)})"
                    )

                result = parsed
                break  # success

            except Exception as e:
                print(f"[Batch {batch_idx // BATCH_SIZE}] Attempt {attempt} failed: {e}")
                if attempt < MAX_ATTEMPTS:
                    time.sleep(RETRY_DELAY)

        if result is None:
            print(f"[Batch {batch_idx // BATCH_SIZE}] Skipping after {MAX_ATTEMPTS} failed attempts")
            continue

        # Write to DB
        for tagged in result.jobs:
            if tagged.tech_stack:
                cursor.execute(
                    "UPDATE jobs SET tech_stack = ? WHERE source_id = ?",
                    (tagged.tech_stack, tagged.source_id),
                )
                print(f"Analyzed Job {tagged.source_id}: {tagged.tech_stack}")

        conn.commit()

    conn.close()
    elapsed = (time.time() - start) * 1000
    print(f"\nTotal tokens used: {total_tokens}, took {elapsed:.3f}ms")
    return total_tokens, elapsed


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/jobs_d1.db"
    tag_data(db_path)