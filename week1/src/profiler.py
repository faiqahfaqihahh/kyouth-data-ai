import sqlite3
import os
import re

def run_data_profile(db_path): 
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT source_id, job_title, company, description FROM job_listings")
    rows = cursor.fetchall()
    for source_id, job_title, company, description in rows:
        quality = "HIGH"
        if not job_title or not company or not description:
            quality = "LOW"
        elif len(description) < 100:
            quality = "LOW"
        elif re.search(r"[!#]{4,}", description): 
            quality = "LOW"

        cursor.execute("UPDATE job_listings SET quality = ? WHERE source_id = ?", (quality, source_id))

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs_quarantine AS
        SELECT * FROM job_listings WHERE 0
    """)
    cursor.execute("INSERT INTO jobs_quarantine SELECT * FROM job_listings WHERE quality = 'LOW'")
    cursor.execute("DELETE FROM job_listings WHERE quality = 'LOW'")

    cursor.execute("SELECT COUNT(*) FROM job_listings")
    total_records = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM job_listings WHERE job_title IS NULL OR job_title = ''")
    missing_titles = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM job_listings WHERE company IS NULL OR company = ''")
    missing_companies = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM job_listings WHERE description IS NULL OR description = ''")
    missing_descriptions = cursor.fetchone()[0]

    cursor.execute("SELECT AVG(LENGTH(description)) FROM job_listings")
    avg_desc_length = cursor.fetchone()[0]
    cursor.execute("SELECT source_id, job_title, LENGTH(description) FROM job_listings ORDER BY LENGTH(description) ASC LIMIT 1")
    shortest_desc = cursor.fetchone()
    cursor.execute("SELECT source_id, job_title, LENGTH(description) FROM job_listings ORDER BY LENGTH(description) DESC LIMIT 1")
    longest_desc = cursor.fetchone()

    conn.commit()
    conn.close()

    print("\n--- 🔍 DATA QUALITY REPORT ---")
    print(f"📈 Total Records: {total_records}")
    print(f"❓ Missing Values -> job_title: {missing_titles}, company: {missing_companies}, description: {missing_descriptions}")
    print(f"📝 Avg Description Length: {int(avg_desc_length)} chars")
    print(f"⚠️ Shortest Description: {shortest_desc[2]} chars")
    print(f"   ↳ source_id: {shortest_desc[0]} | job_title: {shortest_desc[1]}")
    print(f"🚨 Longest Description: {longest_desc[2]} chars")
    print(f"   ↳ source_id: {longest_desc[0]} | job_title: {longest_desc[1]}")