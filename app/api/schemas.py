# app/api/schemas.py
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


SUPPORTED_LANGUAGES = Literal[
    "English",
    "German",
    "French",
    "Spanish",
    "Japanese",
]

class ReportRequestCreate(BaseModel):
    email: str = Field(min_length=3)
    store_url: str = Field(min_length=1)
    language: str = Field(default="English")


class ReportRequestResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    email: str
    store_url: str
    language: str = "English"                  
    created_at: str
    updated_at: str
    error: str | None = None
    error_type: str | None = None
    report: dict[str, Any] | None = None


class QueueResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    message: str