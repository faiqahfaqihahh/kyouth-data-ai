from pathlib import Path
import sqlite3
import json
import hashlib
import logging

def load_all_jsons(input_dir, output_dir): 
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "jobs.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_listings (
            source_id TEXT PRIMARY KEY,
            job_title TEXT,
            company TEXT,
            description TEXT,
            tech_stack TEXT,
            content_hash TEXT,
            quality TEXT
        )
    """)

    total, inserted, skipped = 0, 0, 0

    for json_file in input_dir.glob("*.json"):
        total += 1
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))

            hash_input = f"{data['job_title']}|{data['company']}|{data['description']}"
            content_hash = hashlib.sha256(hash_input.encode()).hexdigest()

            before_changes = conn.total_changes
            cursor.execute("""
                INSERT OR IGNORE INTO job_listings (source_id, job_title, company, description, tech_stack, content_hash, quality)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (data["source_id"], data["job_title"], data["company"], data["description"], None, content_hash, None))
            after_changes = conn.total_changes
            if after_changes > before_changes:
                print(f"✅ Inserted: {json_file.name}")
                logging.info(f"Inserted: {json_file.name}")
                inserted += 1
            else:
                print(f"⏭️ Skipped (duplicate): {json_file.name}")
                logging.warning(f"Skipped duplicate: {json_file.name}")
                skipped += 1

        except Exception as e:
            print(f"❌ Failed to insert {json_file.name}: {e}")
            logging.error(f"Failed to process {json_file.name}: {e}")
            skipped += 1
    conn.commit()
    conn.close()

    print("\n📊 Gold Summary:")
    print(f"Total: {total} | Inserted: {inserted} | Skipped: {skipped}")

    
    