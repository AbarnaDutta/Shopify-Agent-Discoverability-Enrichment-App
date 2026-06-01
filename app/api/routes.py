from fastapi import APIRouter, HTTPException

from app.api.schemas import QueueResponse, ReportRequestCreate, ReportRequestResponse
from app.services.jobs import job_queue


router = APIRouter()


@router.get("/")
def home() -> dict[str, str]:
    return {"status": "ok", "message": "Shopify enrichment API"}


@router.post("/report-requests", response_model=QueueResponse)
def create_report_request(payload: ReportRequestCreate) -> QueueResponse:
    if "@" not in payload.email or "." not in payload.email.split("@")[-1]:
        raise HTTPException(status_code=422, detail="A valid email address is required.")

    job = job_queue.submit(payload.email, payload.store_url)
    return QueueResponse(job_id=job.job_id, status="queued", message="Report request queued.")


@router.get("/report-requests/{job_id}", response_model=ReportRequestResponse)
def get_report_request(job_id: str) -> ReportRequestResponse:
    job = job_queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Report request not found.")
    return ReportRequestResponse(**job_queue.serialize(job))

