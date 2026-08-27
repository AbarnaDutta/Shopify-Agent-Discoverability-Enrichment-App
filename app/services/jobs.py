# app/services/jobs.py
from __future__ import annotations

import datetime as dt
import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any
import traceback
import os
import time

from app.core.config import get_app_settings
from app.services.product_fetcher import (
    InvalidStoreURLError,
    NonShopifyStoreError,
    StoreUnreachableError,
    EmptyStoreError,
    fetch_products_public,
    compact_product,
    normalize_store_url,
)
from app.services.shopify_admin_fetcher import (
    ShopifyAdminAPIError,
    fetch_products_admin,
)
import contextlib
from app.services.report_builder import (
    LLMQuotaExceededError,
    LLMRateLimitError,
    LLMResponseError,
    LLMAuthError,
    get_llm_adapter,
    get_bedrock_adapter,
    check_agent_discovery_readiness,
)
from app.services.email_service import EmailService
from app.integrations.email_clients.ses_mail import SESMail
from app.services.job_repository import job_repo
from dotenv import load_dotenv
from app.services.audit_engine import audit_products

load_dotenv()

email_service = EmailService(
    email_client=SESMail(
        sender_email  = os.getenv("SENDER_EMAIL"),
        smtp_username = os.getenv("SES_SMTP_USERNAME"),
        smtp_password = os.getenv("SES_SMTP_PASSWORD"),
    )
)

@dataclass
class ReportJob:
    job_id: str
    email: str
    store_url: str
    language: str = "English"
    source: str = "website"
    shop_domain: str | None = None
    access_token: str | None = None
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
        "The store URL you entered doesn't look valid. Please check it and try again (e.g. https://your-store.myshopify.com).",
    ),
    (
        NonShopifyStoreError,
        "non_shopify_store",
        "We couldn't find a Shopify product catalogue at that URL. Make sure the store is live and built on Shopify.",
    ),
    (
        StoreUnreachableError,
        "store_unreachable",
        "We couldn't reach that store URL. Please check that the address is correct and the store is online.",
    ),
    (
        LLMQuotaExceededError,
        "llm_quota_exceeded",
        "The AI analysis couldn't be completed because the provider's quota or token limit has been reached. Please try again later or contact support.",
    ),
    (
        LLMRateLimitError,
        "llm_rate_limited",
        "The AI provider is currently rate-limiting requests. Please wait a few minutes and try again.",
    ),
    (
        LLMResponseError,
        "llm_response_error",
        "The AI provider returned an unexpected response. Please try again — if the problem persists, contact support.",
    ),
    (
        LLMAuthError,
        "llm_auth_error",
        "There was an authentication issue with the AI provider. Please try again later — this is not an issue with your store URL.",
    ),
    (
        EmptyStoreError,
        "empty_store",
        "Your store was found but has no publicly visible products. This usually means the catalogue is password-protected, products are set to draft, or the store hasn't launched yet.",
    ),
]

def _classify_exception(error: Exception) -> tuple[str, str]:
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
        self._gemini_gate = threading.Semaphore(1)   
        self._bedrock_gate = threading.Semaphore(2)  
        self._provider_lock = threading.Lock()
        self._active_gemini = 0
        self._active_bedrock = 0

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        num_workers = int(os.getenv("JOB_WORKERS", "3"))
        for i in range(num_workers):
            worker = threading.Thread(target=self._worker_loop, daemon=True, name=f"worker-{i}")
            worker.start()
        print(f"[JobQueue] Started {num_workers} workers")

    def submit(self, email: str, store_url: str, language: str = "English", source: str = "website", shop_domain: str | None = None, access_token: str | None = None,) -> ReportJob:
        job = ReportJob(
            job_id=str(uuid.uuid4()),
            email=email.strip(),
            store_url=store_url,
            language=language,
            source=source,
            shop_domain=shop_domain,
            access_token=access_token,
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
            language=getattr(row, "language", "English"),
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

    def _pick_provider(self, default_provider: str, model: str):
        bedrock_enabled = os.getenv("BEDROCK_FALLBACK_ENABLED", "true").lower() == "true"

        if default_provider != "gemini" or not bedrock_enabled:
            adapter = get_llm_adapter(default_provider, model)
            gate = self._gemini_gate if default_provider == "gemini" else contextlib.nullcontext()
            return adapter, gate, default_provider

        with self._provider_lock:
            gemini_free = self._active_gemini == 0
            if gemini_free:
                self._active_gemini += 1
                return get_llm_adapter("gemini", model), None, "gemini"
            else:
                self._active_bedrock += 1
                return get_bedrock_adapter(), None, "bedrock"

    def _release_provider(self, provider_label: str) -> None:
        if provider_label in ("gemini", "bedrock"):
            with self._provider_lock:
                if provider_label == "gemini":
                    self._active_gemini = max(0, self._active_gemini - 1)
                else:
                    self._active_bedrock = max(0, self._active_bedrock - 1)

    def _process_job(self, job_id: str) -> None:
        print("=" * 80)
        print(f"[JOB {job_id}] PROCESS START")
        print("=" * 80)
        job = self.get(job_id)
        if job is None:
            return

        self._update_job(job_id, status="processing", error=None, error_type=None)
        effective_provider = None
        try:
            print(f"[JOB {job_id}] Starting store fetch")
            print(f"[JOB {job_id}] Store: {job.store_url}")
            print(f"[JOB {job_id}] Language: {job.language}")
            settings = get_app_settings()
            if job.source == "shopify_app":
                if not job.shop_domain:
                    raise ValueError("Shopify shop domain is missing.")

                if not job.access_token:
                    raise ValueError("Shopify access token is missing.")

                print(
                    f"[JOB {job_id}] Fetching products through Shopify Admin API"
                )

                products = fetch_products_admin(
                    shop_domain=job.shop_domain,
                    access_token=job.access_token,
                    max_products=10,
                    api_version="2026-07",
                )

                if not products:
                    raise EmptyStoreError(
                        f"'{job.shop_domain}' has no products available through "
                        "the Shopify Admin API."
                    )

                store_url = f"https://{job.shop_domain}"

            else:
                print(
                    f"[JOB {job_id}] Fetching products through public storefront"
                )

                store_url = normalize_store_url(job.store_url)

                raw_products = fetch_products_public(
                    store_url,
                    settings["max_products"],
                )

                if not raw_products:
                    raise EmptyStoreError(
                        f"'{store_url}' has no publicly visible products."
                    )

                products = [
                    compact_product(p, store_url)
                    for p in raw_products
                ]
            print(f"[JOB {job_id}] Fetched {len(products)} products")

            print(f"[JOB {job_id}] Checking agent discovery files")
            try:
                agent_discovery = check_agent_discovery_readiness(store_url)
                print(f"[JOB {job_id}] Agent discovery: {agent_discovery.get('summary')}")
            except Exception as discovery_error:
                print(f"[JOB {job_id}] Agent discovery check failed: {discovery_error}")
                traceback.print_exc()
                agent_discovery = None

            provider = settings["provider"]
            model = settings["model"]
            adapter, _, effective_provider = self._pick_provider(provider, model)
            print(f"[JOB {job_id}] Routed → {effective_provider}")
            start_time = time.time()
            report = audit_products(
                products=products,
                store_url=store_url,
                language=job.language,
                analyzer=adapter,
            )

            print(f"[JOB {job_id}] Analysis done in {time.time() - start_time:.2f}s")

            report.setdefault("provider", effective_provider)
            report.setdefault("model", model)
            report.setdefault("store_url", store_url)
            report["agent_discovery"] = agent_discovery

            self._update_job(job_id, report=report)
            try:
                print(f"[JOB {job_id}] Sending email")
                email_service.send_report_email(
                    job.email, report, products, store_url, language=job.language
                )
                print(f"[JOB {job_id}] Email sent")
            except Exception as email_error:
                print(f"[JOB {job_id}] Email failed (report still complete): {email_error}")

            self._update_job(job_id, status="completed")

        except Exception as error:
            print(f"[JOB {job_id}] FAILED: {type(error).__name__}: {error}")
            traceback.print_exc()
            error_type, user_message = _classify_exception(error)
            self._update_job(job_id, status="failed", error=user_message, error_type=error_type)

        finally:
            if effective_provider:
                self._release_provider(effective_provider)

        print(f"[JOB {job_id}] PROCESS COMPLETED")
        print("=" * 80)  
    def _update_job(self, job_id: str, **changes: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                for key, value in changes.items():
                    setattr(job, key, value)
                job.updated_at = dt.datetime.now(dt.timezone.utc).isoformat() + "Z"
        job_repo.update(job_id, **changes)

job_queue = JobQueue()