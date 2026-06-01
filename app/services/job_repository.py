# app/services/job_repository.py
from __future__ import annotations

import datetime as dt
from typing import Any

from app.core.database import get_db, is_db_available, ReportRequest


class JobRepository:
    """
    Wraps all DB reads and writes.
    Every method is a silent no-op when no database is configured,
    so the app runs fine locally with in-memory state only.
    """

    def create(self, job_id: str, email: str, store_url: str) -> None:
        if not is_db_available():
            return
        db = get_db()
        try:
            row = ReportRequest(
                job_id=job_id,
                email=email,
                store_url=store_url,
                status="queued",
            )
            db.add(row)
            db.commit()
        finally:
            db.close()

    def update(self, job_id: str, **changes: Any) -> None:
        if not is_db_available():
            return
        db = get_db()
        try:
            row = db.query(ReportRequest).filter_by(job_id=job_id).first()
            if row is None:
                return
            for key, value in changes.items():
                setattr(row, key, value)
            row.updated_at = dt.datetime.now(dt.timezone.utc)
            db.commit()
        finally:
            db.close()

    def get(self, job_id: str) -> ReportRequest | None:
        if not is_db_available():
            return None         # caller falls back to in-memory cache
        db = get_db()
        try:
            return db.query(ReportRequest).filter_by(job_id=job_id).first()
        finally:
            db.close()

    def all_by_email(self, email: str) -> list[ReportRequest]:
        if not is_db_available():
            return []
        db = get_db()
        try:
            return (
                db.query(ReportRequest)
                .filter_by(email=email)
                .order_by(ReportRequest.created_at.desc())
                .all()
            )
        finally:
            db.close()

    def recent(self, limit: int = 100) -> list[ReportRequest]:
        if not is_db_available():
            return []
        db = get_db()
        try:
            return (
                db.query(ReportRequest)
                .order_by(ReportRequest.created_at.desc())
                .limit(limit)
                .all()
            )
        finally:
            db.close()


job_repo = JobRepository()