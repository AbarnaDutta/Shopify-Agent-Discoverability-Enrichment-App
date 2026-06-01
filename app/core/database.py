# app/core/database.py
from __future__ import annotations

import os
import datetime as dt
from typing import Any

from sqlalchemy import create_engine, Column, String, DateTime, Text, JSON
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


class ReportRequest(Base):
    __tablename__ = "report_requests"

    job_id     = Column(String(36),  primary_key=True)
    email      = Column(String(320), nullable=False, index=True)
    store_url  = Column(String(512), nullable=False)
    status     = Column(String(32),  nullable=False, default="queued", index=True)
    error      = Column(Text,        nullable=True)
    error_type = Column(String(64),  nullable=True)
    report     = Column(JSON,        nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: dt.datetime.now(dt.timezone.utc),
                        onupdate=lambda: dt.datetime.now(dt.timezone.utc))


def _build_database_url() -> str | None:
    """Return the DB URL, or None if no database is configured."""
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("DB_HOST")
    if not host:
        return None          # ← no DB configured at all
    port     = os.getenv("DB_PORT", "5432")
    name     = os.getenv("DB_NAME", "shopify_enrichment")
    user     = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "")
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"


# Module-level engine — None when no DB is configured
_db_url = _build_database_url()

if _db_url:
    engine = create_engine(
        _db_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
else:
    engine = None
    SessionLocal = None


def is_db_available() -> bool:
    return engine is not None


def init_db() -> None:
    """Create tables if a DB is configured. Silent no-op otherwise."""
    if not is_db_available():
        print("No DATABASE_URL set — running without database persistence.")
        return
    Base.metadata.create_all(bind=engine)
    print("Database initialised.")


def get_db() -> Session | None:
    """Return a new session, or None if no DB is configured."""
    if SessionLocal is None:
        return None
    return SessionLocal()