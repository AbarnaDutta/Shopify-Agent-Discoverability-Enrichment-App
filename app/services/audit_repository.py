# app/services/audit_repository.py
from __future__ import annotations

import uuid
import datetime as dt
from typing import Any

from sqlalchemy.orm import selectinload

from app.core.database import (
    safe_db,
    Store,
    Audit,
    AuditProduct,
    AuditStoreRecommendation,
    AuditAgentDiscovery,
)


def _new_id() -> str:
    return str(uuid.uuid4())


class AuditRepository:

    def get_or_create_store(self, shop_domain: str, email: str | None = None) -> str | None:

        with safe_db("get_or_create_store") as db:
            if db is None:
                return None

            store = db.query(Store).filter(Store.shop_domain == shop_domain).one_or_none()
            if store:
                if email and not store.email:
                    store.email = email
                    db.commit()
                return store.id

            store = Store(id=_new_id(), shop_domain=shop_domain, email=email)
            db.add(store)
            db.commit()
            return store.id

    def record_audit(
        self,
        shop_domain: str,
        report: dict[str, Any],
        job_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        email: str | None = None,
    ) -> str | None:
        
        with safe_db("record_audit") as db:
            if db is None:
                return None

            store = db.query(Store).filter(Store.shop_domain == shop_domain).one_or_none()
            if store is None:
                store = Store(id=_new_id(), shop_domain=shop_domain, email=email)
                db.add(store)
            elif email and not store.email:
                store.email = email

            scores = report.get("readiness_scores") or {}
            products = report.get("products") or []
            store_recs = report.get("store_level_recommendations") or []
            agent_discovery = report.get("agent_discovery")

            issues_found = sum(len(p.get("missing_enrichments") or []) for p in products)

            audit = Audit(
                id=_new_id(),
                job_id=job_id,
                status="completed",
                overall_score=scores.get("overall"),
                dimension_scores=scores,
                products_scanned=len(products),
                issues_found=issues_found,
                provider=provider,
                model=model,
            )

            for p in products:
                enrichments = p.get("missing_enrichments") or []
                audit.products.append(AuditProduct(
                    id=_new_id(),
                    product_id=str(p.get("product_id") or p.get("id") or ""),
                    title=p.get("title"),
                    score=p.get("score"),
                    issue_count=len(enrichments),
                    high_priority_count=sum(1 for r in enrichments if r.get("priority") == "high"),
                    agent_summary=p.get("agent_summary"),
                    missing_enrichments=enrichments,
                ))

            for r in store_recs:
                audit.store_recommendations.append(AuditStoreRecommendation(
                    id=_new_id(),
                    enrichment=r.get("enrichment"),
                    priority=r.get("priority"),
                    why_it_matters_for_agents=r.get("why_it_matters_for_agents"),
                    example=r.get("example"),
                ))

            if agent_discovery:
                audit.agent_discovery = AuditAgentDiscovery(
                    summary=agent_discovery.get("summary"),
                    templates_customized=agent_discovery.get("templates_customized"),
                    templates_total=agent_discovery.get("templates_total"),
                    files=agent_discovery.get("files"),
                    recommendations=agent_discovery.get("recommendations"),
                )

            store.audits.append(audit)  
            store.last_audit_at = dt.datetime.now(dt.timezone.utc)

            db.add(store)
            db.commit()
            return audit.id


    def get_latest_audit(self, shop_domain: str) -> dict[str, Any] | None:

        with safe_db("get_latest_audit") as db:
            if db is None:
                return None
            store = db.query(Store).filter(Store.shop_domain == shop_domain).one_or_none()
            if store is None:
                return None
            audit = (
                db.query(Audit)
                .options(
                    selectinload(Audit.products),
                    selectinload(Audit.store_recommendations),
                    selectinload(Audit.agent_discovery),
                )
                .filter(Audit.store_id == store.id)
                .order_by(Audit.created_at.desc())
                .first()
            )
            return self._serialize_audit(audit, include_children=True) if audit else None

    def list_audits(self, shop_domain: str, limit: int = 20) -> list[dict[str, Any]]:
        with safe_db("list_audits") as db:
            if db is None:
                return []
            store = db.query(Store).filter(Store.shop_domain == shop_domain).one_or_none()
            if store is None:
                return []
            return [
                {
                    "id": a.id,
                    "created_at": a.created_at.isoformat(),
                    "overall_score": a.overall_score,
                    "products_scanned": a.products_scanned,
                    "issues_found": a.issues_found,
                }
                for a in store.audits[:limit]
            ]

    def get_audit_products(self, audit_id: str) -> list[dict[str, Any]]:
        with safe_db("get_audit_products") as db:
            if db is None:
                return []
            audit = (
                db.query(Audit)
                .options(selectinload(Audit.products))
                .filter(Audit.id == audit_id)
                .one_or_none()
            )
            if audit is None:
                return []
            return [self._serialize_product(p) for p in audit.products]

    def get_audit_product(self, audit_id: str, product_id: str) -> dict[str, Any] | None:
        with safe_db("get_audit_product") as db:
            if db is None:
                return None
            row = (
                db.query(AuditProduct)
                .filter(AuditProduct.audit_id == audit_id, AuditProduct.product_id == product_id)
                .one_or_none()
            )
            return self._serialize_product(row) if row else None

    def _serialize_audit(self, audit: Audit, include_children: bool = False) -> dict[str, Any]:
        data = {
            "id": audit.id,
            "status": audit.status,
            "overall_score": audit.overall_score,
            "dimension_scores": audit.dimension_scores,
            "products_scanned": audit.products_scanned,
            "issues_found": audit.issues_found,
            "provider": audit.provider,
            "model": audit.model,
            "created_at": audit.created_at.isoformat(),
        }
        if include_children:
            data["products"] = [self._serialize_product(p) for p in audit.products]
            data["store_level_recommendations"] = [
                {
                    "enrichment": r.enrichment,
                    "priority": r.priority,
                    "why_it_matters_for_agents": r.why_it_matters_for_agents,
                    "example": r.example,
                }
                for r in audit.store_recommendations
            ]
            if audit.agent_discovery:
                data["agent_discovery"] = {
                    "summary": audit.agent_discovery.summary,
                    "templates_customized": audit.agent_discovery.templates_customized,
                    "templates_total": audit.agent_discovery.templates_total,
                    "files": audit.agent_discovery.files,
                    "recommendations": audit.agent_discovery.recommendations,
                }
        return data

    def _serialize_product(self, p: AuditProduct) -> dict[str, Any]:
        return {
            "product_id": p.product_id,
            "title": p.title,
            "score": p.score,
            "issue_count": p.issue_count,
            "high_priority_count": p.high_priority_count,
            "agent_summary": p.agent_summary,
            "missing_enrichments": p.missing_enrichments,
        }


audit_repo = AuditRepository()