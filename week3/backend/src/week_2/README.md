# Job Skill Analyser

## Project Overview

This project is a two-stage AI-powered pipeline that helps candidates identify skill gaps between their resume and the current job market.

**Stage 1 — Data Tagging (`tag_data.py`):** Reads raw job descriptions from a SQLite database and uses the Gemini API to extract and tag the technical stack required for each job, populating the `tech_stack` column in the database.

**Stage 2 — Skill Gap Analysis (`find_skill_gaps.py`):** Reads a candidate's resume, extracts their technical skills via Gemini, then compares them against all tagged job tech stacks in the database to produce a sorted list of skill gaps along with demand statistics.

Both stages communicate with the SQLite database indirectly through an MCP (Model Context Protocol) server (`db_server.py`), keeping database access modular and decoupled from business logic.

---

## Setup Instructions

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.12 (recommended) or higher |
| uv | Latest |
| Ollama (optional) | Any Model |

### 1. Install uv

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone the repository and navigate to the project folder

```bash
git clone <your-repo-url>
cd week_2
```

### 3. Pin Python version and create virtual environment

```bash
uv python pin 3.12
uv venv
```

Activate the virtual environment:

```bash
# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 4. Install dependencies

```bash
uv sync
```

Or manually:

```bash
pip install fastmcp google-genai python-dotenv pydantic
```

### 5. Configure environment variables

Create a `.env` file in the root of the project:

```
GOOGLE_API_KEY=your_google_api_key_here
```

> **Never commit your `.env` file.** Add it to `.gitignore`.

To obtain a Google API key, visit [Google AI Studio](https://aistudio.google.com/app/apikey).

### 6. Prepare the database

Ensure `resources/jobs_d1.db` exists and contains a `jobs` table with at least `source_id`, `description`, and `tech_stack` columns. This is provided as part of the project resources.

---

## Usage

### Step 1 — Tag job descriptions

Reads all untagged rows in the `jobs` table and populates their `tech_stack` column using Gemini model.

```bash
uv run tag_data.py
```

Expected output:

```
Analyzed Job 91397216: Python, SQL, machine learning, data visualization
Analyzed Job 91347112: Java, Spring Boot, REST APIs, microservices
...
Total tokens used: 2044, took 19305.595ms
Quality — unique stacks: 38, duplicates: 1, direct match %: 97.44%
```

If all rows are already tagged:

```
No data to tag
Total tokens used: 0, took 16.676ms
```

### Step 2 — Find skill gaps

Reads the resume and compares it against all tagged jobs in the database.

```bash
uv run find_skill_gaps.py
```

Expected output:

```
Candidate skills: ['c/c++', 'azure', 'python', 'powershell', 'mysql']

gaps=['ai/ml', 'aws', 'ci/cd', 'docker', 'java', 'sql', ...] time=95601 tokens=753
Most wanted skill you're missing: sql
Demand range: sql (6 jobs) vs web automation (1 job)

--- Skill Gap Statistics ---
Skill                           Jobs   % of Jobs  Demand
------------------------------------------------------------
sql                                6       75.0%  High
docker                             3       37.5%  Medium
web automation                     1       12.5%  Low
```

### Utility — Test a model prompt directly

```bash
uv run prompt_model.py gemini-2.0-flash "What is Python used for?"
uv run prompt_model.py llama3.1 "What is Python used for?"
```

---

## API / Function Reference

### `db_server.py` — MCP Server

Exposes the SQLite database as an MCP tool server. Launched automatically as a subprocess by client scripts.

**Environment variable:**

| Variable | Description | Default |
|---|---|---|
| `DB_PATH` | Path to the SQLite database | `resources/jobs_d1.db` |

**Tools exposed:**

| Tool | Parameters | Returns | Description |
|---|---|---|---|
| `query_db` | `sql_query: str` | `list[tuple]` | Executes any SQL query and returns all results |
| `get_tech_stacks` | none | `list[str]` | Returns all non-empty `tech_stack` values from the jobs table |

---

### `tag_data.py`

```python
async def tag_data(db_url: str) -> tuple[int, float]
```

| | |
|---|---|
| **Purpose** | Tags all untagged job rows with their extracted technical stack |
| **Input** | `db_url` — path to the SQLite database |
| **Output** | `(total_tokens, elapsed_ms)` — token usage and time taken |

Internally batches job descriptions (batch size: 5), sends them to Gemini, parses the response, validates batch size matches, and writes results back via MCP. Retries on failure with API-suggested wait times.

---

### `find_skill_gaps.py`

```python
def find_skill_gaps(input_file_path: str, db_url: str) -> SkillGapResult
```

| | |
|---|---|
| **Purpose** | Identifies skill gaps between a candidate resume and job market requirements |
| **Input** | `input_file_path` — path to resume `.txt` file; `db_url` — path to SQLite database |
| **Output** | `SkillGapResult` Pydantic model (see below) |

**`SkillGapResult` schema:**

```python
class SkillStats(BaseModel):
    skill: str
    job_count: int       # number of jobs requiring this skill
    demand_pct: float    # percentage of jobs requiring this skill
    demand_level: str    # "High", "Medium", or "Low"

class SkillGapResult(BaseModel):
    gaps: List[str]              # sorted lowercase list of missing skills
    tokens: int                  # total tokens used
    time_ms: float               # total time in milliseconds
    skill_demand: dict           # {skill: job_count} for gap skills
    statistics: List[SkillStats] # rich demand statistics per gap skill
    most_wanted: str             # single highest-demand gap skill
    demand_range: str            # human-readable demand spread summary
```

---

### Module Interaction

```
resume.txt ──► find_skill_gaps.py ──► Gemini API (extract candidate skills)
                      │
                      ▼
              db_server.py (MCP) ──► jobs_d1.db (read tech_stacks)
                      │
                      ▼
              set subtraction ──► SkillGapResult
```

```
tag_data.py ──► db_server.py (MCP) ──► jobs_d1.db (read untagged rows)
      │
      ▼
  Gemini API (extract tech stack per batch)
      │
      ▼
  db_server.py (MCP) ──► jobs_d1.db (write tech_stack)
```

---

## Data / Assumptions

### Database Schema

The pipeline reads from and writes to a SQLite database with the following relevant columns in the `jobs` table:

| Column | Type | Description |
|---|---|---|
| `source_id` | INTEGER | Unique job identifier |
| `description` | TEXT | Raw job description text |
| `tech_stack` | TEXT | Comma-separated technical skills (populated by `tag_data.py`) |

### Input File

`resume.txt` must be a plain text file containing the candidate's resume. No specific formatting is required, but the more structured the resume the more accurately skills are extracted.

### Assumptions

- Job descriptions are in English.
- The `tech_stack` column is `NULL` or empty for untagged rows.
- A `GOOGLE_API_KEY` with sufficient quota is available.
- Skills in the resume that are certifications (e.g. CCNA) or non-technical (e.g. leadership, cooking) are intentionally excluded.
- Compound skill names like `C/C++` or `node.js` are treated as single atomic skills and are not split.
- Values like `"not specified"` written by the model when no skills are found are filtered out and not counted as real skills.
- Determinism is achieved via exact set subtraction after lowercasing, not via LLM judgement.

### Data Flow

```
jobs_d1.db
  └─ description (raw)
       └─► Gemini (batch tagging)
             └─► tech_stack (comma-separated, written back to DB)
                   └─► build_demand_map() (aggregated skill counts)
                         └─► set subtraction with candidate skills
                               └─► SkillGapResult (gaps + statistics)
```

---

## Testing

### Manual Test Cases

| Scenario | How to reproduce | Expected result |
|---|---|---|
| All rows already tagged | Run `tag_data.py` after a full run | Prints `No data to tag` |
| Resume with no skills | Pass a plain text file with only a name | `gaps` equals all job skills |
| Jailbreak in resume | Add `"ignore all instructions"` to resume | Prints warning and returns empty result |
| `not specified` in DB | Leave some jobs with no tech stack description | Filtered out from gap results |
| Re-run after clearing | Run `clear_tech_stack.py` then `tag_data.py` | All rows re-tagged fresh |

### Validation Methods

**Tagging quality** is measured after each run:
- Duplicate stack count — how many jobs got identical tech stacks
- Direct match percentage — ratio of unique stacks to total tagged

**Skill gap determinism** is verified by running `find_skill_gaps.py` twice on the same database and confirming identical `gaps` output. Since the final result uses pure set subtraction (not LLM judgement), output is deterministic regardless of model temperature.

**Batch mismatch detection** in `tag_data.py` validates that the number of parsed results equals the number of jobs sent per batch, triggering a retry if not.

---

## Limitations

- **Free tier quota:** The Gemini free tier has low RPM and daily limits. Large databases will hit rate limits and require waiting between runs or a paid API key.
- **`C/C++` splitting:** Despite prompt instructions, Gemini occasionally splits compound skill names. This causes false positives in skill gap results (e.g. reporting `c` as a gap when the candidate has `c/c++`).
- **`not specified` pollution:** If `tag_data.py` runs on jobs with vague descriptions, the model may write `"not specified"` as the tech stack. A filter exists in `find_skill_gaps.py` but the DB still contains dirty data.
- **No deduplication of skills across jobs:** The same skill appearing twice in one job's `tech_stack` string would be counted twice in the demand map.
- **MCP subprocess overhead:** Spawning `db_server.py` as a subprocess on every run adds latency. For large datasets this adds up.
- **English only:** Resumes or job descriptions in other languages are not supported.
- **No persistent retry state:** If the script crashes mid-run, there is no checkpoint. It will re-process only rows where `tech_stack` is still empty, which is a partial safeguard but not a full recovery mechanism.

---

## Architecture Reflection

### Design Choices

The project is split into three clearly separated concerns: the MCP server handles all database access, `tag_data.py` handles batch AI tagging, and `find_skill_gaps.py` handles analysis. This separation means each component can be tested, replaced, or extended independently — for example, swapping the database backend only requires changes to `db_server.py`.

The MCP pattern was chosen over direct SQLite calls in the analysis scripts because it mirrors a real service-oriented architecture where data access is mediated through a defined interface rather than direct coupling. It also makes the DB path configurable without changing analysis code.

Determinism in skill gap analysis was a deliberate design priority. Rather than asking the LLM to decide what the gaps are (which would vary between runs), the LLM is only used for normalisation and extraction — the actual gap computation is pure set subtraction. This guarantees identical output for the same inputs.

### Trade-offs

**Simplicity vs robustness:** Batch size of 5 and a fixed sleep between batches is simple but not optimal. A proper token-budget-aware batcher would be more robust but significantly more complex to implement.

**Speed vs accuracy:** Descriptions are capped at 800 characters per job to reduce token usage. This risks missing skills mentioned later in long descriptions, trading completeness for cost and speed.

**Determinism vs flexibility:** Fixing the gap computation to exact string matching means the system won't catch near-matches (e.g. `"postgres"` vs `"postgresql"`). A fuzzy matching approach would be more flexible but harder to make deterministic.

### Improvements

Given more time, the following would be prioritised:

- **Fuzzy skill normalisation:** Build a canonical skill dictionary (e.g. `postgres → postgresql`, `k8s → kubernetes`) applied before set subtraction, removing the dependency on LLM normalisation for this step.
- **Checkpointing:** Save progress to a state file so interrupted runs can resume from the last successful batch rather than starting over.
- **Async parallelism:** Use `asyncio.gather()` to process multiple batches concurrently (with a semaphore to respect rate limits), significantly reducing total runtime.
- **Richer resume parsing:** Use a structured resume parser to distinguish between skill sections, work experience, and education before passing to the LLM, improving extraction accuracy.
- **Web dashboard:** Expose `SkillGapResult` through a simple FastAPI endpoint and render the statistics as a visual chart for easier interpretation during demos.