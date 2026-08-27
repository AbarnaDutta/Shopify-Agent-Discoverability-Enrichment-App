# app/api/routes.py
import re
from fastapi import APIRouter, HTTPException

from app.api.schemas import QueueResponse, ReportRequestCreate, ReportRequestResponse
from app.services.jobs import job_queue
from app.services.product_fetcher import InvalidStoreURLError, normalize_store_url
from pydantic import BaseModel


router = APIRouter()

class ShopifyAppReportRequest(BaseModel):
    email: str
    shop_domain: str
    access_token: str
    language: str = "English"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(email: str) -> None:
    if not _EMAIL_RE.match(email.strip()):
        raise HTTPException(
            status_code=422,
            detail="Please enter a valid email address (e.g. you@example.com).",
        )


def _validate_store_url(store_url: str) -> str:
    """Normalize and do a cheap structural check before the job even enters the queue."""
    try:
        return normalize_store_url(store_url)
    except InvalidStoreURLError as error:
        print("Store URL validation error for store URL:", store_url)
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/")
def home() -> dict[str, str]:
    return {"status": "ok", "message": "Shopify enrichment API"}


@router.post("/report-requests", response_model=QueueResponse)
def create_report_request(payload: ReportRequestCreate) -> QueueResponse:
    print("RAW STORE URL:", repr(payload.store_url))
    _validate_email(payload.email)
    normalized_url = _validate_store_url(payload.store_url)
    print("NORMALIZED URL:", normalized_url)
    language = payload.language or "English"
    job = job_queue.submit(payload.email, normalized_url, language)
    return QueueResponse(job_id=job.job_id, status="queued", message="Report request queued.")

@router.post("/shopify-app/report-requests", response_model=QueueResponse)
def create_shopify_app_report_request(
    payload: ShopifyAppReportRequest,
) -> QueueResponse:

    _validate_email(payload.email)

    if not payload.shop_domain.strip():
        raise HTTPException(
            status_code=422,
            detail="Shopify shop domain is required.",
        )

    if not payload.access_token.strip():
        raise HTTPException(
            status_code=422,
            detail="Shopify access token is required.",
        )

    store_url = f"https://{payload.shop_domain.strip()}"

    job = job_queue.submit(
        email=payload.email,
        store_url=store_url,
        language=payload.language or "English",
        source="shopify_app",
        shop_domain=payload.shop_domain.strip(),
        access_token=payload.access_token.strip(),
    )

    return QueueResponse(
        job_id=job.job_id,
        status="queued",
        message="Shopify app report request queued.",
    )


@router.get("/report-requests/{job_id}", response_model=ReportRequestResponse)
def get_report_request(job_id: str) -> ReportRequestResponse:
    job = job_queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Report request not found.")
    return ReportRequestResponse(**job_queue.serialize(job))

