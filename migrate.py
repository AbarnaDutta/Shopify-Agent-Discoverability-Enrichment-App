# migrate.py
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit("DATABASE_URL not set in .env")

# --- Step 1: create all tables from the current ORM models ---
from app.core.database import Base, get_engine  # noqa: E402

engine = get_engine()
if engine is None:
    raise SystemExit("Could not create a DB engine — check DATABASE_URL")

Base.metadata.create_all(bind=engine)
print(
    "OK: ensured tables exist — report_requests, stores, audits, "
    "audit_products, audit_store_recommendations, audit_agent_discovery"
)

# --- Step 2: legacy column backfill (no-op on a fresh database) ---
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

migrations = [
    # language column
    """
    ALTER TABLE report_requests
    ADD COLUMN IF NOT EXISTS language VARCHAR(64) NOT NULL DEFAULT 'English';
    """,

    # error_type column
    """
    ALTER TABLE report_requests
    ADD COLUMN IF NOT EXISTS error_type VARCHAR(64);
    """,

    # store recommendation affected products
    """
    ALTER TABLE audit_store_recommendations
    ADD COLUMN IF NOT EXISTS affected_product_ids JSON NOT NULL DEFAULT '[]'::json;
    """,

    # audit issue field
    """
    ALTER TABLE audit_issues
    ADD COLUMN IF NOT EXISTS field VARCHAR(255);
    """,

    # audit issue affected products
    """
    ALTER TABLE audit_issues
    ADD COLUMN IF NOT EXISTS affected_product_ids JSON NOT NULL DEFAULT '[]'::json;
    """,
    
    """
    ALTER TABLE audit_issues
    ADD COLUMN IF NOT EXISTS fix_status VARCHAR(32) NOT NULL DEFAULT 'not_fixed';
    """,
    
    """
    ALTER TABLE audit_issues
    ADD COLUMN IF NOT EXISTS fixed_at TIMESTAMPTZ;
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