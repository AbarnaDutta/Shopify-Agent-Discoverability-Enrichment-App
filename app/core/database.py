# app/core/database.py
from __future__ import annotations

import logging
import os
import datetime as dt
from contextlib import contextmanager
from typing import Any, Generator

from sqlalchemy import create_engine, Column, String, DateTime, Text, JSON
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class ReportRequest(Base):
    __tablename__ = "report_requests"

    job_id     = Column(String(36),  primary_key=True)
    email      = Column(String(320), nullable=False, index=True)
    store_url  = Column(String(512), nullable=False)
    language   = Column(String(64),  nullable=False, server_default="English")
    status     = Column(String(32),  nullable=False, default="queued", index=True)
    error      = Column(Text,        nullable=True)
    error_type = Column(String(64),  nullable=True)
    report     = Column(JSON,        nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: dt.datetime.now(dt.timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        default=lambda: dt.datetime.now(dt.timezone.utc),
                        onupdate=lambda: dt.datetime.now(dt.timezone.utc))

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.getenv("DATABASE_URL")
        if url:
            try:
                _engine = create_engine(
                    url,
                    pool_pre_ping=True,
                    pool_size=5,
                    max_overflow=10,
                    echo=False,
                )
                _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
            except Exception as e:
                log.error("Failed to initialize database engine configuration: %s", e)
                return None
    return _engine


def is_db_available() -> bool:
    return get_engine() is not None


def init_db() -> None:
    engine = get_engine()
    if not engine:
        print("No DATABASE_URL set — running without database persistence.")
        return
    try:
        Base.metadata.create_all(bind=engine)
        print("Database initialised.")
    except OperationalError as e:
        log.warning("Database is configured but could not be reached at startup: %s", e)
        print("Warning: database unreachable at startup — running without persistence.")


def get_db() -> Session | None:
    get_engine()  
    if _SessionLocal is None:
        return None
    return _SessionLocal()


@contextmanager
def safe_db(operation: str) -> Generator[Session | None, None, None]:
    if not is_db_available():
        yield None
        return

    db = get_db()
    try:
        yield db
    except OperationalError as e:
        log.error("DB connection error during '%s': %s", operation, e)
        if db:
            try: db.rollback()
            except Exception: pass
    except SQLAlchemyError as e:
        log.error("DB error during '%s': %s", operation, e)
        if db:
            try: db.rollback()
            except Exception: pass
    except Exception as e:
        log.error("Unexpected DB error during '%s': %s", operation, e)
        if db:
            try: db.rollback()
            except Exception: pass
    finally:
        if db:
            try: db.close()
            except Exception: pass