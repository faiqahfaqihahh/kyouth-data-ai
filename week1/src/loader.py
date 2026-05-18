import json
import logging
import sqlite3
from hashlib import sha256
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_sql(query_name: str) -> str:
    """Load a raw SQL statement from queries/<name>.sql."""
    sql_path = Path("queries") / f"{query_name}.sql"
    with open(sql_path, "r", encoding="utf-8") as fh:
        return fh.read()


def _content_hash(job_title: str, company: str, description: str) -> str:
    """SHA-256 hash of normalised content to detect silent changes."""
    raw = f"{job_title.strip().lower()}|{company.strip().lower()}|{description.strip().lower()}"
    return sha256(raw.encode("utf-8")).hexdigest()


def _quality_label(job_title: str, company: str, description: str) -> str:
    """Return 'LOW' or 'HIGH' based on data quality rules."""
    if not job_title or not company or not description:
        return "LOW"
    if len(description) < 100:
        return "LOW"
    special_chars = description.count("!") + description.count("#")
    if special_chars > 10:
        return "LOW"
    return "HIGH"


def load_all_jsons(input_dir: str, output_dir: str) -> None:
    """Load Silver JSON files into the Gold SQLite database."""
    input_path  = Path(input_dir)
    output_path = Path(output_dir)

    print("🥇 Gold:...")

    output_path.mkdir(parents=True, exist_ok=True)

    if not input_path.exists() or not any(input_path.iterdir()):
        logger.warning("Silver directory is empty or does not exist: %s", input_dir)
        print("📊 Gold Summary:")
        print("Total: 0 | Inserted: 0 | Skipped: 0")
        return

    db_path    = output_path / "jobs.db"
    connection = sqlite3.connect(db_path)
    cursor     = connection.cursor()

    # Schema – loaded from .sql files (Bonus: SQL queries separated)
    cursor.executescript(_load_sql("create_jobs_table"))
    cursor.executescript(_load_sql("create_jobs_quarantine_table"))
    connection.commit()

    json_files = sorted(input_path.glob("*.json"))
    total    = len(json_files)
    inserted = 0
    skipped  = 0

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)

            new_hash = _content_hash(data["job_title"], data["company"], data["description"])
            quality  = _quality_label(data["job_title"], data["company"], data["description"])

            # Check for existing record (content hashing – Bonus)
            cursor.execute(_load_sql("select_existing_job"), (data["source_id"],))
            row = cursor.fetchone()

            if row:
                existing_hash = row[1]
                if existing_hash == new_hash:
                    logger.info("Skipped (duplicate): %s", json_file.name)
                    print(f"⏭️  Skipped (duplicate): {json_file.name}")
                    skipped += 1
                else:
                    # Content changed – update record
                    cursor.execute(
                        _load_sql("update_job_hash"),
                        (data["job_title"], data["company"], data["description"], new_hash, data["source_id"]),
                    )
                    connection.commit()
                    logger.info("Updated (content changed): %s", json_file.name)
                    print(f"🔄 Updated (content changed): {json_file.name}")
                    inserted += 1
            else:
                cursor.execute(
                    _load_sql("insert_job"),
                    (data["source_id"], data["job_title"], data["company"],
                     data["description"], None, new_hash, quality),
                )
                connection.commit()
                logger.info("Inserted: %s", json_file.name)
                print(f"✅ Inserted: {json_file.name}")
                inserted += 1

        except Exception as exc:
            logger.error("Error loading %s | Reason: %s", json_file.name, exc)
            print(f"❌ Error: {json_file.name}")
            skipped += 1

    connection.close()
    print("📊 Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Skipped: {skipped}")