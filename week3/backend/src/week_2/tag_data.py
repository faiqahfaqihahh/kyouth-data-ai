import asyncio
import time
import os
from dotenv import load_dotenv
from fastmcp import Client
from google import genai
import ast

BATCH_SIZE = 5          # rows sent to the model per request
MAX_RETRIES = 5         # attempts before giving up on a batch
RETRY_DELAY = 2.0       # seconds to wait between retries

def count_tokens_fallback(text: str) -> int:
    """Fallback: 4 tokens per word, used only when the API gives no count."""
    return len(text.split()) * 4


def escape_sql(value: str) -> str:
    """Escape single quotes so UPDATE statements don't break."""
    return value.replace("'", "''")


def evaluate_quality(tech_stacks: list[str]) -> None:
    """Print a simple quality report for the tagged stacks."""
    if not tech_stacks:
        return
    unique = set(tech_stacks)
    duplicates = len(tech_stacks) - len(unique)
    match_pct = (len(unique) / len(tech_stacks)) * 100
    print(f"Quality — unique stacks: {len(unique)}, "
          f"duplicates: {duplicates}, "
          f"direct match %: {match_pct:.2f}%")


def build_prompt(batch: list[tuple]) -> str:
    lines = "\n\n".join(
        f"Job {job[0]}: {job[1][:800]}"   # cap each description at 800 chars
        for job in batch
    )
    return (
        "List only the technical stack for each job. "
        "Output format — one line per job, nothing else:\n"
        "JobID: tech1, tech2, tech3\n\n"
        + lines
    )


def parse_response(response_text: str, batch: list[tuple]) -> dict[str, str]:
    #Parse the model's response into {source_id: tech_stack}.
    #Returns an empty dict if the line count doesn't match the batch size.
    expected_ids = {str(job[0]) for job in batch}
    results: dict[str, str] = {}

    for line in response_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            continue
        left, right = line.split(":", 1)
        # accept "Job 123" or bare "123"
        job_id = left.strip().replace("Job", "").strip()
        if job_id in expected_ids:
            results[job_id] = right.strip()

    return results


async def tag_data(db_url: str):
    #Read untagged rows from the jobs table at db_url, call the Gemini API
    #in batches to extract the tech stack, and write results back.
    #Returns (total_tokens, elapsed_ms).
   
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    gemini = genai.Client(api_key=api_key)

    os.environ["DB_PATH"] = db_url
    mcp_client = Client("db_server.py")

    total_tokens = 0
    start_time = time.time()
    all_stacks: list[str] = []

    async with mcp_client:
        # 1. Fetch rows that still need tagging
        try:
            result = await mcp_client.call_tool(
                "query_db",
                {"sql_query": "SELECT source_id, description FROM jobs WHERE tech_stack IS NULL OR tech_stack = ''"}
            )
            jobs = ast.literal_eval(result.content[0].text)
        except Exception as exc:
            print(f"Failed to fetch jobs: {exc}")
            return 0, 0

        if not jobs:
            print("No data to tag")
            elapsed = (time.time() - start_time) * 1000
            print(f"Total tokens used: 0, took {elapsed:.3f}ms")
            return 0, elapsed

        # 2. Process in batches with retry
        for batch_idx in range(0, len(jobs), BATCH_SIZE):
            batch = jobs[batch_idx: batch_idx + BATCH_SIZE]
            batch_num = batch_idx // BATCH_SIZE
            prompt = build_prompt(batch)
            input_tokens = 0
            output_tokens = 0
            success = False

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    response = await gemini.aio.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=prompt,
                    )
                    response_text = response.text.strip()

                    # --- token counting (prefer API values) ---
                    if hasattr(response, "usage_metadata") and response.usage_metadata:
                        input_tokens = response.usage_metadata.prompt_token_count or 0
                        output_tokens = response.usage_metadata.candidates_token_count or 0
                    else:
                        input_tokens = count_tokens_fallback(prompt)
                        output_tokens = count_tokens_fallback(response_text)

                    # --- validate that we got one result per job ---
                    results = parse_response(response_text, batch)
                    if len(results) != len(batch):
                        raise ValueError(
                            f"Mismatch between batch size ({len(batch)}) "
                            f"and response ({len(results)} parsed)"
                        )

                    # --- write results back via MCP ---
                    for job_id, tech_stack in results.items():
                        if "not specified" in tech_stack.lower():
                            print(f"Skipping Job {job_id}: no tech stack found in description")
                            continue
                        safe_stack = escape_sql(tech_stack)
                        try:
                            await mcp_client.call_tool(
                                "query_db",
                                {"sql_query": f"UPDATE jobs SET tech_stack='{safe_stack}' WHERE source_id='{job_id}'"}
                            )
                            print(f"Analyzed Job {job_id}: {tech_stack}")
                            all_stacks.append(tech_stack)
                        except Exception as write_exc:
                            print(f"[Batch {batch_num}] Write failed for "
                                  f"job {job_id}: {write_exc}")

                    total_tokens += input_tokens + output_tokens
                    success = True
                    break  # move on to the next batch

                except ValueError as ve:
                    # Mismatch — retry
                    print(f"[Batch {batch_num}] Attempt {attempt} failed: {ve}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)

                except Exception as exc:
                    # Network / API error — retry
                    print(f"[Batch {batch_num}] Attempt {attempt} error: {exc}")
                    if attempt < MAX_RETRIES:
                        await asyncio.sleep(RETRY_DELAY)

                except Exception as exc:
                    error_str = str(exc)
                    print(f"[Batch {batch_num}] Attempt {attempt} error: {exc}")
                    
                    if attempt < MAX_RETRIES:
                        import re
                        match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_str, re.IGNORECASE)
                        wait_time = float(match.group(1)) + 2 if match else RETRY_DELAY
                        print(f"[Batch {batch_num}] Waiting {wait_time:.1f}s before retry...")
                        await asyncio.sleep(wait_time)

            if not success:
                print(f"[Batch {batch_num}] Giving up after {MAX_RETRIES} attempts.")

            await asyncio.sleep(5)

    elapsed = (time.time() - start_time) * 1000
    print(f"Total tokens used: {total_tokens}, took {elapsed:.3f}ms")
    evaluate_quality(all_stacks)
    return total_tokens, elapsed


if __name__ == "__main__":
    asyncio.run(tag_data("resources/jobs_d1.db"))