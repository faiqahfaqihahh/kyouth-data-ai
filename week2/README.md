# Week 2 – LLM Tooling

## Project Overview

This project explores working with AI language models for real-world data tasks:

1. **Part 1 – `prompt_model.py`**: A unified interface to call either local Ollama models or cloud Google Gemini models.
2. **Day 1-2 – `tag_data.py`**: Reads job descriptions from a SQLite database and uses an LLM to extract the technical stack for each role.
3. **Day 3-4 – `find_skill_gaps.py`**: Compares a candidate's resume against the tagged job market to identify missing technical skills.

---

## Setup Instructions

### Prerequisites

- Python 3.11+
- [`uv`](https://astral.sh/uv) package manager
- [Ollama](https://ollama.com/) installed and running locally
- A [Google AI Studio](https://aistudio.google.com/) API key (free)

### 1. Install `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone / enter the project and install dependencies

```bash
cd week_2
uv sync          # installs all packages from pyproject.toml
```

### 3. Install Ollama models

```bash
ollama pull llama3.1
ollama pull phi3
ollama pull deepseek-r1:1.5b
```

Verify Ollama is running:

```bash
curl 127.0.0.1:11434   # should print "Ollama is running"
```

### 4. Configure your API key

Create a `.env` file in the `week_2/` directory:

```
GOOGLE_API_KEY=your_key_here
```

⚠️ **Never commit `.env` to git.** It is already listed in `.gitignore`.

### 5. Place data files

```
week_2/
└── data/
    ├── jobs_d1.db      ← from resources.zip
    └── resume.txt      ← from resources.zip (resume_d3.txt renamed)
```

---

## Usage

### Prompt a model

```bash
uv run prompt_model.py llama3.1 "tell me one Malaysian joke"
uv run prompt_model.py gemini-2.5-flash "tell me one Malaysian joke"
```

### Tag job data

```bash
uv run tag_data.py                     # uses data/jobs_d1.db by default
uv run tag_data.py data/jobs_d1.db    # explicit path
```

### Find skill gaps

```bash
uv run find_skill_gaps.py                            # uses defaults
uv run find_skill_gaps.py data/resume.txt data/jobs_d1.db
```

### View rate limits

```bash
cat rate_limits.txt
```

---

## API / Function Reference

### `prompt_model(model, prompt) -> str`

| Parameter | Type | Description |
|-----------|------|-------------|
| `model`   | str  | Model name: `llama3.1`, `phi3`, `deepseek-r1:1.5b`, `gemini-2.5-flash`, etc. |
| `prompt`  | str  | The text prompt |

Returns the model's text response. Never raises — errors are returned as strings.

---

### `tag_data(db_url) -> (int, float)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `db_url`  | str  | Path to the SQLite database |

Returns `(total_tokens_used, elapsed_ms)`. Updates `tech_stack` column in the `jobs` table in batches of 5.

---

### `find_skill_gaps(input_file_path, db_url) -> SkillGapResult`

| Parameter | Type | Description |
|-----------|------|-------------|
| `input_file_path` | str | Path to resume `.txt` file |
| `db_url`          | str | Path to the SQLite database |

Returns a `SkillGapResult` Pydantic model:

```python
class SkillGapResult(BaseModel):
    gaps: List[str]          # sorted, lowercase skill gaps
    tokens_used: int
    elapsed_ms: float
    skill_demand: dict       # {skill: job_count}
    top_demanded: List[str]  # top 5 gap skills by demand
```

---

## Data / Assumptions

- **Database schema**: single `jobs` table with columns `source_id`, `job_title`, `company`, `description`, `tech_stack`.
- `tech_stack` is NULL for untagged rows; `tag_data.py` populates it.
- **Resume format**: plain text (`.txt`). The parser handles noisy real-world formatting.
- **Batch size**: 5 jobs per AI request — balances token usage vs. latency and stays well within Gemini free-tier rate limits.
- **Retry logic**: up to 3 attempts with 2-second delay between retries for `tag_data`, 1-second for `find_skill_gaps`.

---

## Testing

Run the scripts against the provided sample data:

```bash
# 1. Tag the database (should process all rows)
uv run tag_data.py

# 2. Run again (should print "No data to tag")
uv run tag_data.py

# 3. Find skill gaps
uv run find_skill_gaps.py

# 4. Run again — output should be identical (determinism check)
uv run find_skill_gaps.py
```

Determinism is enforced by:
- Setting `temperature=0` on the Gemini API call in `find_skill_gaps.py`
- Sorting and lowercasing all output
- Using exact string matching (no fuzzy logic)

---

## Limitations

- Gemini free tier rate limits may cause temporary 503 errors under heavy use; the retry logic handles this but won't succeed if the quota is exhausted for the day.
- The tagging accuracy depends on the model and how descriptive the job posting is. Slight variations are acceptable per the spec.
- `find_skill_gaps.py` may not perfectly normalise skill aliases (e.g. "ML" vs "machine learning") — exact match is used intentionally per the spec's direct-match requirement.
- Ollama models run locally and may be slow on CPU-only machines without a GPU.

---

## Architecture Reflection

### Design Choices

- **Model routing in `prompt_model.py`** is done via simple set membership — easy to extend and test without extra dependencies.
- **Batch processing in `tag_data.py`** avoids hitting context limits and respects rate limits while keeping total API calls manageable.
- **Determinism in `find_skill_gaps.py`** is achieved through `temperature=0`, sorted output, and a fixed comparison algorithm rather than relying on the model to be consistent.
- **Jailbreak prevention** uses regex pattern matching against known prompt injection phrases before any user input reaches the model.

### Trade-offs

- Simplicity was prioritised over scalability. For a production system, a proper task queue (Celery, etc.) would replace the simple batch loop.
- Using `temperature=0` maximises determinism but reduces creative paraphrasing — acceptable here since we only need structured JSON output.

### Improvements

- Add async/parallel batch processing to speed up `tag_data.py` significantly.
- Use embeddings (vector similarity) instead of exact matching for more robust skill gap detection.
- Store token usage per-run in the database for long-term optimisation analysis.
- Add a proper test suite with `pytest` and mocked API responses.