# app/services/jobs.py
from __future__ import annotations

import datetime as dt
import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any
import traceback

from app.services.report_builder import (
    run_store_analysis,
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMResponseError,
    LLMAuthError, 
)
from app.services.product_fetcher import (
    InvalidStoreURLError,
    NonShopifyStoreError,
    StoreUnreachableError,
)
from app.services.email_service import EmailService
from app.integrations.email_clients.hostinger_mail import HostingerMail
from app.services.job_repository import job_repo          

from dotenv import load_dotenv

load_dotenv()
import os

email_service = EmailService(email_client=HostingerMail(os.getenv("SENDER_EMAIL"), os.getenv("EMAIL_PASSWORD")))  

@dataclass
class ReportJob:
    job_id: str
    email: str
    store_url: str
    language: str = "English"
    status: str = "queued"
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat() + "Z")
    updated_at: str = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat() + "Z")
    error: str | None = None
    error_type: str | None = None         
    report: dict[str, Any] | None = None


_ERROR_CATALOGUE: list[tuple[type, str, str]] = [
    (
        InvalidStoreURLError,
        "invalid_store_url",
        "The store URL you entered doesn't look valid. "
        "Please check it and try again (e.g. https://your-store.myshopify.com).",
    ),
    (
        NonShopifyStoreError,
        "non_shopify_store",
        "We couldn't find a Shopify product catalogue at that URL. "
        "Make sure the store is live and built on Shopify.",
    ),
    (
        StoreUnreachableError,
        "store_unreachable",
        "We couldn't reach that store URL. "
        "Please check that the address is correct and the store is online.",
    ),
    (
        LLMQuotaExceededError,
        "llm_quota_exceeded",
        "The AI analysis couldn't be completed because the provider's quota or token limit "
        "has been reached. Please try again later or contact support.",
    ),
    (
        LLMRateLimitError,
        "llm_rate_limited",
        "The AI provider is currently rate-limiting requests. "
        "Please wait a few minutes and try again.",
    ),
    (
        LLMResponseError,
        "llm_response_error",
        "The AI provider returned an unexpected response. "
        "Please try again — if the problem persists, contact support.",
    ),
    (
        LLMAuthError,
        "llm_auth_error",
        "There was an authentication issue with the AI provider. "
        "Please try again later — this is not an issue with your store URL.",
    ),
]


def _classify_exception(error: Exception) -> tuple[str, str]:
    """Return (error_type, user_message) for any exception."""
    for exc_class, error_type, user_message in _ERROR_CATALOGUE:
        if isinstance(error, exc_class):
            return error_type, user_message
    return "internal_error", (
        "An unexpected error occurred while processing your request. "
        "Our team has been notified. Please try again later."
    )


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

    def submit(self, email: str, store_url: str, language: str = "English") -> ReportJob:
        job = ReportJob(
            job_id=str(uuid.uuid4()),
            email=email.strip(),
            store_url=store_url,
            language=language,
        )
        job_repo.create(job.job_id, job.email, job.store_url, job.language)
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

        self._update_job(job_id, status="processing", error=None, error_type=None)
        try:
            result = run_store_analysis(job.store_url, language=job.language)
            report = result["report"]
            if report is None:
                raise RuntimeError("No report was generated for this store.")
            self._update_job(job_id, report=report)
            email_service.send_report_email(job.email, report, result["products"], job.store_url, language=job.language)
            self._update_job(job_id, status="completed")
        except Exception as error:
            error_type, user_message = _classify_exception(error)
            self._update_job(job_id, status="failed", error=user_message, error_type=error_type)
            try:
                email_service.send_failure_email(
                    job.email,
                    job.store_url,
                    user_message=user_message,
                    error_type=error_type,
                    language=job.language,    
                )
            except Exception:
                pass
    def _update_job(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for key, value in changes.items():
                    setattr(job, key, value)
                job.updated_at = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
        job_repo.update(job_id, **changes)


job_queue = JobQueue()
