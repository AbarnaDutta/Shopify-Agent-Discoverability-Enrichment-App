# app/services/jobs.py
from __future__ import annotations

import datetime as dt
import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from app.services.report_builder import run_store_analysis
from app.services.product_fetcher import normalize_store_url
from app.services.email_service import EmailService
from app.integrations.email_clients.hostinger_mail import HostingerMail
from app.services.job_repository import job_repo          

from dotenv import load_dotenv

load_dotenv()
import os

email_service = EmailService(email_client=HostingerMail(os.getenv("SENDER_EMAIL"), os.getenv("EMAIL_PASSWORD")))  # Initialize with appropriate values

@dataclass
class ReportJob:
    job_id: str
    email: str
    store_url: str
    status: str = "queued"
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat() + "Z")
    error: str | None = None
    report: dict[str, Any] | None = None


class JobQueue:
    def __init__(self) -> None:
        self._queue: queue.Queue[str] = queue.Queue()
        self._jobs: dict[str, ReportJob] = {}
        self._lock = threading.Lock()
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        worker = threading.Thread(target=self._worker_loop, daemon=True)
        worker.start()

    def submit(self, email: str, store_url: str) -> ReportJob:
        normalized_store_url = normalize_store_url(store_url)
        job = ReportJob(job_id=str(uuid.uuid4()), email=email.strip(), store_url=normalized_store_url)
        with self._lock:
            self._jobs[job.job_id] = job
        self._queue.put(job.job_id)
        return job

    def get(self, job_id: str) -> ReportJob | None:
        with self._lock:
            cached = self._jobs.get(job_id)
        if cached:
            return cached

        row = job_repo.get(job_id)
        if row is None:
            return None

        job = ReportJob(
            job_id=row.job_id,
            email=row.email,
            store_url=row.store_url,
            status=row.status,
            created_at=row.created_at.isoformat() + "Z",
            updated_at=row.updated_at.isoformat() + "Z",
            error=row.error,
            report=row.report,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def serialize(self, job: ReportJob) -> dict[str, Any]:
        return asdict(job)

    def _worker_loop(self) -> None:
        while True:
            job_id = self._queue.get()
            try:
                self._process_job(job_id)
            finally:
                self._queue.task_done()

    def _process_job(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None:
            return

        self._update_job(job_id, status="processing", error=None)
        try:
            result = run_store_analysis(job.store_url)
            report = result["report"]
            if report is None:
                raise RuntimeError("No report was generated for this store.")
            self._update_job(job_id, report=report)
            email_service.send_report_email(job.email, report, result["products"], job.store_url)
            self._update_job(job_id, status="completed")
        except Exception as error:
            try:
                email_service.send_failure_email(job.email, job.store_url, error)
            except Exception:
                pass
            self._update_job(job_id, status="failed", error=str(error))

    def _update_job(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for key, value in changes.items():
                    setattr(job, key, value)
                job.updated_at = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
        job_repo.update(job_id, **changes)


job_queue = JobQueue()
