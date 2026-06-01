# app/services/job_repository.py
from __future__ import annotations

import datetime as dt
from typing import Any

from app.core.database import ReportRequest, safe_db


class JobRepository:

    def create(self, job_id: str, email: str, store_url: str) -> None:
        with safe_db("create job") as db:
            if db is None:
                return
            row = ReportRequest(
                job_id=job_id,
                email=email,
                store_url=store_url,
                status="queued",
            )
            db.add(row)
            db.commit()

    def update(self, job_id: str, **changes: Any) -> None:
        with safe_db("update job") as db:
            if db is None:
                return
            row = db.query(ReportRequest).filter_by(job_id=job_id).first()
            if row is None:
                return
            for key, value in changes.items():
                setattr(row, key, value)
            row.updated_at = dt.datetime.now(dt.timezone.utc)
            db.commit()

    def get(self, job_id: str) -> ReportRequest | None:
        with safe_db("get job") as db:
            if db is None:
                return None
            return db.query(ReportRequest).filter_by(job_id=job_id).first()

    def all_by_email(self, email: str) -> list[ReportRequest]:
        with safe_db("list jobs by email") as db:
            if db is None:
                return []
            return (
                db.query(ReportRequest)
                .filter_by(email=email)
                .order_by(ReportRequest.created_at.desc())
                .all()
            )

    def recent(self, limit: int = 100) -> list[ReportRequest]:
        with safe_db("list recent jobs") as db:
            if db is None:
                return []
            return (
                db.query(ReportRequest)
                .order_by(ReportRequest.created_at.desc())
                .limit(limit)
                .all()
            )


job_repo = JobRepository()