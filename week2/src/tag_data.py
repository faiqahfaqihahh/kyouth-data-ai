"""
tag_data.py  (MCP edition)

Populates the tech_stack column of untagged jobs using Gemini + FastMCP.
Instead of running SQL directly, this script talks to db_server.py via
the MCP protocol — Gemini decides which SQL tool to call and when.
"""

import asyncio
import json
import sys
import time
import os

from dotenv import load_dotenv
from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from pydantic import BaseModel, Field

load_dotenv()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = "gemini-2.5-flash"
BATCH_SIZE = 5          # rows per Gemini request  (5 RPM -> 1 req/12 s)
RETRY_DELAY_S = 12      # seconds between batches
MAX_RETRIES = 3

# ---------------------------------------------------------------------------
# Structured Output Schemas (Fixes JSON parsing errors and speeds up generation)
# ---------------------------------------------------------------------------

class JobTag(BaseModel):
    index: int = Field(description="The index matching the job description order.")
    tech_stack: str = Field(description="Comma-separated strings of the technical stack. Exclude soft skills.")

class BatchResponse(BaseModel):
    jobs: list[JobTag]

# ---------------------------------------------------------------------------
# Quality measurement
# ---------------------------------------------------------------------------

def measure_quality(all_stacks: list) -> dict:
    if not all_stacks:
        return {}

    skill_lists = [
        [s.strip().lower() for s in ts.split(",") if s.strip()]
        for ts in all_stacks if ts
    ]
    flat = [s for sl in skill_lists for s in sl]
    freq = {}
    for s in flat:
        freq[s] = freq.get(s, 0) + 1

    duplicates = sum(1 for v in freq.values() if v > 1)
    coverage = sum(1 for sl in skill_lists if sl) / max(len(all_stacks), 1) * 100

    return {
        "avg_stack_size": round(len(flat) / max(len(skill_lists), 1), 1),
        "unique_skill_count": len(freq),
        "duplicate_rate_pct": round(duplicates / max(len(freq), 1) * 100, 1),
        "coverage_pct": round(coverage, 1),
    }

# ---------------------------------------------------------------------------
# Main async function
# ---------------------------------------------------------------------------

async def tag_data_async(db_url: str) -> tuple:
    start = time.perf_counter()
    total_tokens = 0
    gemini = genai.Client()

    # Safely pass DB_PATH to the background MCP server
    mcp_env = os.environ.copy()
    mcp_env["DB_PATH"] = db_url

    # Force the background server to use your current virtual environment
    server_transport = StdioTransport(
        command=sys.executable,
        args=["db_server.py"],
        env=mcp_env
    )

    async with Client(server_transport) as mcp:
        # 1. Fetch untagged rows via MCP
        try:
            result = await mcp.call_tool(
                "query_db",
                {"sql_query": "SELECT source_id, description FROM jobs WHERE tech_stack IS NULL OR TRIM(tech_stack) = ''"}
            )
            raw_content = result[0].text if hasattr(result[0], "text") else str(result[0])
            rows = json.loads(raw_content)
        except Exception as exc:
            print(f"[MCP Error] Could not fetch jobs: {exc}")
            elapsed = (time.perf_counter() - start) * 1000
            print(f"Total tokens used: 0, took {elapsed:.3f}ms")
            return 0, elapsed

        if not rows:
            elapsed = (time.perf_counter() - start) * 1000
            print("No data to tag")
            print(f"Total tokens used: 0, took {elapsed:.3f}ms")
            return 0, elapsed

        written_ids = set()
        all_tagged_stacks = []

        # 2. Process in batches
        for batch_start in range(0, len(rows), BATCH_SIZE):
            batch = rows[batch_start: batch_start + BATCH_SIZE]
            tokens, results = await _process_batch(gemini, batch_start, batch)
            total_tokens += tokens

            for source_id, tech_stack in results:
                if source_id in written_ids:
                    continue
                try:
                    await mcp.call_tool(
                        "execute_db",
                        {
                            "sql_query": "UPDATE jobs SET tech_stack = ? WHERE source_id = ?",
                            "params": [tech_stack, source_id],
                        },
                    )
                    written_ids.add(source_id)
                    all_tagged_stacks.append(tech_stack)
                    print(f"Analyzed Job {source_id}: {tech_stack}")
                except Exception as exc:
                    print(f"[MCP Error] Failed to update job {source_id}: {exc}")

            # Keep requests paced within 5 RPM limits
            if batch_start + BATCH_SIZE < len(rows):
                await asyncio.sleep(RETRY_DELAY_S)

        # 3. Quality report
        quality = measure_quality(all_tagged_stacks)
        if quality:
            print("\n--- Tagging Quality Report ---")
            print(f"  Coverage           : {quality['coverage_pct']}% of jobs tagged")
            print(f"  Avg skills/job     : {quality['avg_stack_size']}")
            print(f"  Unique skills      : {quality['unique_skill_count']}")
            print(f"  Duplicate rate     : {quality['duplicate_rate_pct']}%")

    elapsed = (time.perf_counter() - start) * 1000
    print(f"\nTotal tokens used: {total_tokens}, took {elapsed:.3f}ms")
    return total_tokens, elapsed


# ---------------------------------------------------------------------------
# Batch processor
# ---------------------------------------------------------------------------

async def _process_batch(client, batch_idx: int, batch: list) -> tuple:
    prompt_lines = []
    for i, row in enumerate(batch):
        source_id = row[0] if isinstance(row, (list, tuple)) else row["source_id"]
        description = row[1] if isinstance(row, (list, tuple)) else row["description"]
        prompt_lines.append(f"[{i}] Job {source_id}:\n{description}\n")

    prompt = "\n".join(prompt_lines)
    instruction = "Extract engineering skills, platforms, or tools from descriptions."
    
    current_delay = RETRY_DELAY_S

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=BatchResponse,
                ),
            )

            parsed_data = response.parsed
            if not parsed_data or len(parsed_data.jobs) != len(batch):
                raise ValueError(f"Mismatch: batch={len(batch)} vs response structure.")

            results = []
            for item in parsed_data.jobs:
                row = batch[item.index]
                source_id = row[0] if isinstance(row, (list, tuple)) else row["source_id"]
                results.append((source_id, item.tech_stack))

            tokens = 0
            if response.usage_metadata:
                tokens = (
                    (response.usage_metadata.prompt_token_count or 0)
                    + (response.usage_metadata.candidates_token_count or 0)
                )

            return tokens, results

        except Exception as exc:
            print(f"[Batch {batch_idx}] Attempt {attempt} failed: {exc}")
            if attempt < MAX_RETRIES:
                # Exponential backoff to safely clear Gemini 503 limits
                print(f"Retrying in {current_delay}s...")
                await asyncio.sleep(current_delay)
                current_delay *= 2

    print(f"[Batch {batch_idx}] All {MAX_RETRIES} attempts failed. Skipping.")
    return 0, []


# ---------------------------------------------------------------------------
# Sync wrapper + entry point
# ---------------------------------------------------------------------------

def tag_data(db_url: str) -> tuple:
    return asyncio.run(tag_data_async(db_url))

def main() -> None:
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/jobs_d1.db"
    tag_data(db_path)

if __name__ == "__main__":
    main()