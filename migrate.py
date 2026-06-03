# migrate.py
"""
One-time migration script — adds missing columns to report_requests.
Safe to run multiple times (uses ADD COLUMN IF NOT EXISTS).
"""
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in .env")

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

migrations = [
    # language column — added when multilingual support was introduced
    """
    ALTER TABLE report_requests
    ADD COLUMN IF NOT EXISTS language VARCHAR(64) NOT NULL DEFAULT 'English';
    """,
    # error_type column — added with error handling improvements
    """
    ALTER TABLE report_requests
    ADD COLUMN IF NOT EXISTS error_type VARCHAR(64);
    """,
]

for sql in migrations:
    try:
        cur.execute(sql)
        print(f"OK: {sql.strip()[:60]}…")
    except Exception as e:
        print(f"SKIP: {e}")

cur.close()
conn.close()
print("Migration complete.")