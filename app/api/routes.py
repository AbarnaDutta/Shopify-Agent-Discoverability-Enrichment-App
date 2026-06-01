# app/api/routes.py
import re
from fastapi import APIRouter, HTTPException

from app.api.schemas import QueueResponse, ReportRequestCreate, ReportRequestResponse
from app.services.jobs import job_queue
from app.services.product_fetcher import InvalidStoreURLError, normalize_store_url


router = APIRouter()

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
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/")
def home() -> dict[str, str]:
    return {"status": "ok", "message": "Shopify enrichment API"}


@router.post("/report-requests", response_model=QueueResponse)
def create_report_request(payload: ReportRequestCreate) -> QueueResponse:
    _validate_email(payload.email)
    normalized_url = _validate_store_url(payload.store_url)

    job = job_queue.submit(payload.email, normalized_url)
    return QueueResponse(job_id=job.job_id, status="queued", message="Report request queued.")


@router.get("/report-requests/{job_id}", response_model=ReportRequestResponse)
def get_report_request(job_id: str) -> ReportRequestResponse:
    job = job_queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Report request not found.")
    return ReportRequestResponse(**job_queue.serialize(job))

