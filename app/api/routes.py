# app/api/routes.py

import datetime as dt
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.schemas import QueueResponse, ReportRequestCreate, ReportRequestResponse
from app.core.database import AuditIssue, Store, safe_db
from app.services.audit_repository import audit_repo
from app.services.fix_engine import FixEngine
from app.services.issue_registry import get_issue_definition
from app.services.jobs import job_queue
from app.services.product_fetcher import InvalidStoreURLError, normalize_store_url
from app.services.shopify_admin_fetcher import ShopifyAdminAPIError


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
    try:
        return normalize_store_url(store_url)
    except InvalidStoreURLError as error:
        print("Store URL validation error for store URL:", store_url)
        raise HTTPException(status_code=422, detail=str(error)) from error


# ---------------------------------------------------------------------
# report requests
# ---------------------------------------------------------------------


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
        raise HTTPException(status_code=422, detail="Shopify shop domain is required.")

    if not payload.access_token.strip():
        raise HTTPException(status_code=422, detail="Shopify access token is required.")

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


# ---------------------------------------------------------------------
# Audits
# ---------------------------------------------------------------------


@router.get("/audits/history")
def get_audit_history(
    shop_domain: str,
    page: int = 1,
    page_size: int = 5,
) -> dict:
    if page < 1:
        raise HTTPException(status_code=422, detail="Page must be 1 or greater.")

    if page_size < 1:
        raise HTTPException(status_code=422, detail="Page size must be greater than 0.")

    return audit_repo.list_audits(
        shop_domain=shop_domain.strip(),
        page=page,
        page_size=page_size,
    )


@router.get("/audits/latest")
def get_latest_audit(shop_domain: str) -> dict:
    if not shop_domain.strip():
        raise HTTPException(status_code=422, detail="Shop domain is required.")

    audit = audit_repo.get_latest_audit(shop_domain.strip())

    if audit is None:
        raise HTTPException(status_code=404, detail="No audit found for this Shopify store.")

    return audit


@router.get("/audits/{audit_id}/products")
def get_audit_products(audit_id: str) -> dict:
    products = audit_repo.get_audit_products(audit_id)

    return {
        "audit_id": audit_id,
        "products": products,
        "total": len(products),
    }


@router.get("/products")
def get_all_products(shop_domain: str) -> dict:
    if not shop_domain.strip():
        raise HTTPException(status_code=422, detail="Shop domain is required.")

    result = audit_repo.get_all_unique_products(shop_domain.strip())

    return {
        "shop_domain": shop_domain.strip(),
        "products": result["products"],
        "total": len(result["products"]),
        "audit_count": result["audit_count"],
    }


@router.get("/products/detail")
def get_product(
    product_id: str,
    shop_domain: str,
) -> dict:
    if not shop_domain.strip():
        raise HTTPException(status_code=422, detail="Shop domain is required.")

    if not product_id.strip():
        raise HTTPException(status_code=422, detail="Product ID is required.")

    product = audit_repo.get_unique_product(
        shop_domain=shop_domain.strip(),
        product_id=product_id.strip(),
    )

    if product is None:
        raise HTTPException(
            status_code=404,
            detail="Product has not been audited for this Shopify store.",
        )

    return {
        "shop_domain": shop_domain.strip(),
        "product": product,
    }


# ---------------------------------------------------------------------
# Product-level fixes
# ---------------------------------------------------------------------


class FixIssueRequest(BaseModel):
    shop_domain: str
    product_id: str
    issue_id: str | None = None
    check_id: str
    issue_type: str
    access_token: str

    merchant_approved: bool | None = None

    handle: str | None = None
    attributes: list[dict[str, str]] | None = None
    product_type: str | None = None
    description_html: str | None = None
    title: str | None = None
    image_url: str | None = None
    alt_text: str | None = None
    image_alts: dict[str, str] | None = None
    option_id: str | None = None
    new_name: str | None = None
    variant_id: str | None = None
    gtin: str | None = None
    mpn: str | None = None
    variants: list[dict[str, str]] | None = None


    variant_option_values: dict[str, dict[str, str]] | None = None

    minimum_age: int | None = None
    warning_text: str | None = None


def _mark_product_issue_applied(issue_id: str | None, product_id: str) -> None:
    if not issue_id:
        return

    with safe_db("record_fix") as db:
        if db is None:
            return

        issue = (
            db.query(AuditIssue)
            .filter(
                AuditIssue.id == issue_id,
                AuditIssue.product_id == product_id,
            )
            .one_or_none()
        )

        if issue is not None:
            issue.fix_status = "applied"
            issue.fixed_at = dt.datetime.now(dt.timezone.utc)
            db.commit()


@router.post("/products/fix")
def fix_product_issue(payload: FixIssueRequest) -> dict:
    shop_domain = payload.shop_domain.strip()
    product_id = payload.product_id.strip()

    if not shop_domain or not product_id:
        raise HTTPException(status_code=422, detail="shop_domain and product_id are required.")

    fix_kwargs = payload.dict(
        exclude={
            "shop_domain", "product_id", "issue_id", "check_id",
            "issue_type", "access_token",
        },
        exclude_none=True,
    )

    try:
        result = FixEngine().execute(
            check_id=payload.check_id,
            issue_type=payload.issue_type,
            product_id=product_id,
            shop_domain=shop_domain,
            access_token=payload.access_token,
            **fix_kwargs,
        )
    except ShopifyAdminAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    if result.get("success") is True:
        _mark_product_issue_applied(payload.issue_id, product_id)

    return result


class VariantOptionsStateRequest(BaseModel):
    shop_domain: str
    access_token: str
    product_id: str


@router.post("/products/variant-options-state")
def get_variant_options_state(payload: VariantOptionsStateRequest) -> dict:
    """Read-only: every variant (fully paginated) with its option values."""
    try:
        return FixEngine().get_variant_options_state(
            shop_domain=payload.shop_domain.strip(),
            access_token=payload.access_token,
            product_id=payload.product_id.strip(),
        )
    except ShopifyAdminAPIError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


# ---------------------------------------------------------------------
# Store-level fixes
# ---------------------------------------------------------------------


class StoreFixRequest(BaseModel):
    shop_domain: str = Field(min_length=1)
    access_token: str = Field(min_length=1)
    issue_id: str = Field(min_length=1)
    check_id: str = Field(min_length=1)
    issue_type: str = Field(min_length=1)
    changes: list[dict[str, Any]] = Field(min_length=1)

    merchant_approved: bool | None = None


@router.post("/store/fix")
def store_fix(body: StoreFixRequest):
    fix_engine = FixEngine()

    shop_domain = body.shop_domain.strip()

    if not shop_domain:
        raise HTTPException(status_code=422, detail="Shop domain is required.")

    try:

        with safe_db("validate_and_record_store_fix") as db:
            if db is None:
                raise HTTPException(
                    status_code=503,
                    detail="Database unavailable. No fix was executed.",
                )

            store = (
                db.query(Store)
                .filter(Store.shop_domain == shop_domain)
                .one_or_none()
            )

            if store is None:
                raise HTTPException(status_code=404, detail="Shopify store not found.")

            issue = (
                db.query(AuditIssue)
                .filter(
                    AuditIssue.id == body.issue_id,
                    AuditIssue.store_id == store.id,
                    AuditIssue.scope == "store",
                )
                .one_or_none()
            )

            if issue is None:
                raise HTTPException(
                    status_code=404,
                    detail="The selected store issue was not found.",
                )

            if issue.check_id != body.check_id or issue.issue_type != body.issue_type:
                raise HTTPException(
                    status_code=409,
                    detail="The submitted check does not match the selected issue.",
                )

            definition = get_issue_definition(issue.check_id, issue.issue_type)

            if definition is None:
                raise HTTPException(
                    status_code=422,
                    detail="No registered definition exists for this issue.",
                )

            if definition.get("scope") != "store":
                raise HTTPException(
                    status_code=422,
                    detail="This issue is not a store-level issue.",
                )

            if definition.get("fix_mode") == "unsupported":
                raise HTTPException(
                    status_code=422,
                    detail="This issue does not support automatic fixing.",
                )

            result = fix_engine.execute_store(
                shop_domain=shop_domain,
                access_token=body.access_token,
                check_id=issue.check_id,
                issue_type=issue.issue_type,
                changes=body.changes,
                issue_id=str(issue.id),
                merchant_approved=body.merchant_approved,
            )

            if result.get("success") is True:
                issue.fix_status = "applied"
                issue.fixed_at = dt.datetime.now(dt.timezone.utc)
            elif result.get("partial_success") is True:
                issue.fix_status = "partially_applied"
                issue.fixed_at = dt.datetime.now(dt.timezone.utc)
            else:
                issue.fix_status = "failed"
            db.commit()

            return JSONResponse(
                status_code=(
                    200 if result.get("success")
                    else 207 if result.get("partial_success")
                    else 422
                ),
                content={
                    **result,
                    "issue_id": str(issue.id),
                    "check_id": issue.check_id,
                    "issue_type": issue.issue_type,
                },
            )

    except HTTPException:
        raise

    except ShopifyAdminAPIError as exc:
        return JSONResponse(status_code=502, content={"success": False, "detail": str(exc)})

    except ValueError as exc:
        return JSONResponse(status_code=422, content={"success": False, "detail": str(exc)})

    except Exception:
        return JSONResponse(
            status_code=500,
            content={"success": False, "detail": "Store fix failed unexpectedly."},
        )