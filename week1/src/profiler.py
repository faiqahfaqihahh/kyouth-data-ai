import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def _load_sql(query_name: str) -> str:
    """Load a raw SQL statement from queries/<name>.sql."""
    sql_path = Path("queries") / f"{query_name}.sql"
    with open(sql_path, "r", encoding="utf-8") as fh:
        return fh.read()


def run_data_profile(db_path: str) -> None:
    """Run data quality checks against the Gold SQLite database and print a report."""
    path = Path(db_path)

    if not path.exists():
        print(f"❌ Database not found at {db_path}")
        logger.error("Database not found at %s", db_path)
        return

    connection = sqlite3.connect(db_path)
    cursor     = connection.cursor()

    # ── Quality labelling (Bonus) ──────────────────────────────────────────────
    cursor.executescript(_load_sql("label_quality"))
    connection.commit()

    # Move LOW quality records to quarantine table
    cursor.executescript(_load_sql("quarantine_low_quality"))
    cursor.executescript(_load_sql("delete_low_quality"))
    connection.commit()
    logger.info("Quality labelling and quarantine complete")

    # ── Metrics ───────────────────────────────────────────────────────────────
    cursor.execute(_load_sql("count_jobs"))
    total = cursor.fetchone()[0]

    cursor.execute(_load_sql("null_counts"))
    null_title, null_company, null_desc = cursor.fetchone()

    cursor.execute(_load_sql("avg_description_length"))
    avg_row = cursor.fetchone()[0]
    avg_len = int(avg_row) if avg_row else 0

    cursor.execute(_load_sql("shortest_description"))
    shortest = cursor.fetchone()

    cursor.execute(_load_sql("longest_description"))
    longest = cursor.fetchone()

    # ── Quality distribution ───────────────────────────────────────────────────
    cursor.execute(_load_sql("count_by_quality"))
    quality_dist = dict(cursor.fetchall())

    connection.close()

    # ── Report ────────────────────────────────────────────────────────────────
    print("\n--- 🔍 DATA QUALITY REPORT ---")
    print(f"📈 Total Records: {total}")
    print(f"❓ Missing Values -> job_title: {null_title or 0}, company: {null_company or 0}, description: {null_desc or 0}")
    print(f"📝 Avg Description Length: {avg_len} chars")

    if shortest:
        print(f"⚠️  Shortest Description: {shortest[2]} chars")
        print(f"   ↳ source_id: {shortest[0]} | job_title: {shortest[1]}")

    if longest:
        print(f"🚨 Longest Description: {longest[2]} chars")
        print(f"   ↳ source_id: {longest[0]} | job_title: {longest[1]}")

    high = quality_dist.get("HIGH", 0)
    low  = quality_dist.get("LOW", 0)
    print(f"\n🏷️  Quality Labels -> HIGH: {high} | LOW: {low} (quarantined)")
    logger.info("Data profile complete | Total: %d | HIGH: %d | LOW: %d", total, high, low)