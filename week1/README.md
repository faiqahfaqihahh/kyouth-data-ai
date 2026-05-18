# Week 1 — Job Listings ETL Pipeline

A local **Medallion Architecture** pipeline that ingests Jobstreet `.mhtml` files, cleans and structures the data, loads it into a SQLite database, and profiles data quality.

---

## Project Description

This project builds a four-stage data pipeline modelled after real-world data engineering practices:

| Layer | Folder | Description |
|---|---|---|
| **Source** | `data/0_source/` | Raw `.mhtml` web archives from Jobstreet |
| **Bronze** | `data/1_bronze/` | Decoded `.html` files (raw, unmodified content) |
| **Silver** | `data/2_silver/` | Cleaned, structured `.json` files (validated fields) |
| **Gold** | `data/3_gold/jobs.db` | SQLite database — query-ready, deduplicated |

---

## Setup Instructions

### Prerequisites

- Python **3.10+**
- `pip` (bundled with Python)

### Install Dependencies

```bash
pip install beautifulsoup4
```

> **Note:** `pydantic` is not required — a lightweight custom `JobListing` class replicates the same data contract validation.

### Environment Variables

No API keys or environment variables are required for this project.

### Directory Setup

Place all `.mhtml` source files inside `data/0_source/` before running the pipeline.
All other directories (`data/1_bronze/`, `data/2_silver/`, `data/3_gold/`) are created automatically.

---

## Usage

Run all commands from the project root directory.

### Run the full pipeline (recommended)

```bash
python main.py all
```

### Run each stage individually

```bash
python main.py ingest    # Extract .mhtml → data/1_bronze/*.html
python main.py process   # Clean HTML   → data/2_silver/*.json
python main.py load      # Load JSON    → data/3_gold/jobs.db
python main.py profile   # Print data quality report
```

### Show available commands

```bash
python main.py
# Usage: python main.py [ingest|process|load|profile|all]
```

### Expected Results

```
📊 Bronze Summary:
Total: 100 | Extracted: 100 | Failed: 0

📊 Silver Summary:
Total: 100 | Processed: 87 | Skipped: 13

📊 Gold Summary:
Total: 87 | Inserted: 87 | Skipped: 0

--- 🔍 DATA QUALITY REPORT ---
📈 Total Records: 87
❓ Missing Values -> job_title: 0, company: 0, description: 0
📝 Avg Description Length: 2694 chars
⚠️  Shortest Description: 32 chars
   ↳ source_id: 91647393 | job_title: Software Engineer
🚨 Longest Description: 6781 chars
   ↳ source_id: 91731564 | job_title: Automation Engineer
```

---

## Project Structure

```
week1/
├── main.py               # CLI orchestrator
├── src/
│   ├── ingestor.py       # Module 1 — Bronze layer
│   ├── processor.py      # Module 2 — Silver layer
│   ├── loader.py         # Module 3 — Gold layer
│   └── profiler.py       # Module 4 — Data quality report
└── data/
    ├── 0_source/         # Input: raw .mhtml files
    ├── 1_bronze/         # Output: decoded .html files
    ├── 2_silver/         # Output: structured .json files
    └── 3_gold/
        └── jobs.db       # Output: SQLite database
```

---

## Technical Reflections

### Module 1: The Extractor (Medallion & Lakehouses)
Why is it useful to keep the original raw HTML files instead of directly inserting processed data into the database? What problems become easier to debug or recover from?

- **Answer**: Keeping the raw `.mhtml` files in the Bronze layer means you always have a source of truth to re-process from. If a parsing bug is discovered later (e.g. the wrong HTML selector was used for `company`), you can fix the processor and re-run from Bronze without having to re-scrape the website. This is the core value of a Data Lake: cheap, durable raw storage that decouples ingestion from transformation. Debugging also becomes far easier — you can open the raw file, inspect what the HTML actually contains, and compare it to what your parser produced. Without raw storage, a corrupted or incorrectly processed record is simply lost.

### Module 2: Treatment Plant (ETL vs ELT & Scale)
Why do cloud systems prefer loading raw data first before cleaning it (ELT)? What problems happen when processing files sequentially, and how does distributed processing help?

- **Answer**: Cloud platforms like Snowflake and BigQuery have virtually unlimited compute available on demand, so it is cheaper and faster to dump raw data into storage first (Load), then run transformations inside the warehouse using SQL (Transform). The raw data is preserved for reprocessing, and multiple teams can define different transformations on the same raw data without stepping on each other. Sequential processing (as in this pipeline) becomes a bottleneck at scale — if one file takes 10 seconds and there are 1 million files, that is 115 days of single-threaded work. Distributed systems like Apache Spark split the work across hundreds of nodes, processing thousands of files simultaneously and reducing runtime to minutes.

### Module 3: The Blueprint & The Vault (Storage & Contracts)
What should happen if an important field like `job_title` disappears? Why fail early instead of silently inserting `nulls` into DB? How does `INSERT OR IGNORE` help prevent duplicate records?

- **Answer**: If `job_title` disappears from the HTML, the pipeline should detect it immediately and skip that record with a clear warning (`⚠️ Missing job_title in: ...`), rather than inserting a `NULL` row. Silently inserting nulls poisons downstream analytics — dashboards show "null" job titles, aggregations are skewed, and the problem is only discovered much later when it is expensive to fix. Failing early (the "fail fast" principle) makes problems visible at the source stage where they are cheapest to debug. `INSERT OR IGNORE` handles re-runs gracefully: if the pipeline crashes halfway and is restarted, records already in the database are skipped instead of raising a primary key conflict error, making the entire pipeline idempotent (safe to run multiple times with the same result).

### Module 4: The QA Inspector & Orchestrator (Orchestration & DAGs)
What happens if `processor.py` crashes halfway? How are automated orchestration tools more reliable than manual retries with Python scripts?

- **Answer**: If `processor.py` crashes halfway, only the files processed before the crash will have JSON outputs in Silver. Re-running `python main.py process` will re-process all files from scratch (idempotent by design — it overwrites outputs), but there is no record of which step failed, no automatic retry, and no alerting. A human must notice the failure and manually intervene. Tools like Apache Airflow model pipelines as Directed Acyclic Graphs (DAGs) with individual task-level state tracking: each task (ingest, process, load, profile) can be retried independently, scheduled on a cron, and configured to send alerts on failure. Airflow also handles dependencies — `process` will only run after `ingest` succeeds — and provides a visual UI to see exactly where and why a pipeline failed without reading through logs.
