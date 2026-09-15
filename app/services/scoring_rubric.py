# app/services/scoring_rubric.py
"""
Single source of truth for the audit rubric. The LLM only ever classifies
against these fixed check_ids — it cannot invent a new issue, a new
category weight, or a new priority. All scoring math is pure Python.
"""
from __future__ import annotations
from typing import Literal

Verdict = Literal["pass", "partial", "fail", "na"]

CHECKS: dict[str, list[dict]] = {
    "ucp_commerce_flows": [
        {"id": "stable_ids_urls",      "level": "product", "desc": "Product has a stable id and a resolvable URL/handle."},
        {"id": "variant_selection",    "level": "product", "desc": "Variants/options let an agent pick the exact SKU: option names meaningful, selectedOptions complete and consistent."},
        {"id": "pricing_clarity",      "level": "product", "desc": "Every variant has a real, non-zero, non-placeholder price."},
        {"id": "availability_signals", "level": "product", "desc": "Inventory/status fields exist and are usable to determine buyable-now."},
        {"id": "fulfillment_context",  "level":  "store",  "desc": "Operational fulfillment information is present and actionable, such as delivery speed, shipping methods, pickup availability, and domestic vs international coverage; a shipping-policy page alone is not sufficient."},
    ],
    "mcp_knowledge": [
        {"id": "product_understanding", "level": "product", "desc": "title + descriptionHtml + attributes clearly answer what the product is, who it's for, and what's included/excluded."},
        {"id": "comparable_attributes", "level": "product", "desc": "productType/tags/options/metafields are structured enough to filter, sort, and compare against similar products."},
        {"id": "policy_semantics", "level": "store", "desc": "Policy text is specific enough that an agent can answer edge cases (deadlines, exceptions, regions) without guessing."},
        {"id": "faq_or_guidance",       "level": "store",   "desc": "FAQ content, metaobjects, or shopping-guidance text exists."},
        {"id": "product_clarity", "level": "product",  "desc": "Description clearly states what/included/how-to-use, no unclarified medical/financial claims."},
    ],
    "catalog_enrichment": [
        {"id": "identifiers",     "level": "product", "desc": "Variant sku present and non-empty; barcode/GTIN/MPN present where applicable."},
        {"id": "rich_attributes", "level": "product", "desc": "Metafields encode material/dimensions/capacity/usage/audience or other domain-specific specs."},
        {"id": "variant_hygiene", "level": "product", "desc": "Options have meaningful names (Size/Color, not Option1/Custom1); not all variants 'Default Title' when real variation exists."},
        {"id": "consistency",     "level": "store",   "desc": "Similar products share similar metafield keys and consistent units/formats across the catalog."},
    ],
    "safety_policies": [
        {"id": "product_guardrails", "level": "product", "desc": "IF this product is in a risky category (age-restricted, medical, weapons, financial, children's safety-critical), it carries matching guardrail metafields (age limit, warnings, human-review flag). Mark 'na' if not a risky category."},
        {"id": "store_guardrails",   "level": "store",   "desc": "Store-level guardrail metafields or policy text exist (age gating, region limits, manual-approval categories)."},
        {"id": "legal_pages",     "level": "store",   "desc": "All four policy bodies (privacy, refund, shipping, terms) present and non-placeholder."},
        {"id": "contact_brand",   "level": "store",   "desc": "Contact details or brand/about content discoverable via shop metafields/metaobjects."},
        {"id": "fulfillment_context",  "level":  "store",  "desc": "Operational fulfillment information is present and actionable, such as delivery speed, shipping methods, pickup availability, and domestic vs international coverage; a shipping-policy page alone is not sufficient."},
        {"id": "policy_semantics", "level": "store", "desc": "Policy text is specific enough that an agent can answer edge cases (deadlines, exceptions, regions) without guessing."},
        {"id": "faq_or_guidance",       "level": "store",   "desc": "FAQ content, metaobjects, or shopping-guidance text exists."},
        
    ],
}

ALL_CHECK_IDS: list[str] = [c["id"] for checks in CHECKS.values() for c in checks]
CHECK_BY_ID: dict[str, dict] = {c["id"]: {**c, "category": cat} for cat, checks in CHECKS.items() for c in checks}

_CATEGORY_SEVERITY = {
    "ucp_commerce_flows": "critical",
    "safety_policies":    "critical",
    "mcp_knowledge":       "high",
    "catalog_enrichment":  "moderate",
}

_SEVERITY_RULES = {
    "critical": {"fail": "high",   "partial": "high"},
    "high":     {"fail": "high",   "partial": "medium"},
    "moderate": {"fail": "medium", "partial": "low"},
}

VERDICT_POINTS = {"pass": 1.0, "partial": 0.5, "fail": 0.0}  # na excluded from denominator


def priority_for(check_id: str, verdict: Verdict) -> str | None:
    """Deterministic. Returns None for pass/na (= no recommendation at all)."""
    if verdict in ("pass", "na"):
        return None
    severity = _CATEGORY_SEVERITY[CHECK_BY_ID[check_id]["category"]]
    return _SEVERITY_RULES[severity][verdict]


def score_product_level_check(verdicts: list[Verdict]) -> float | None:
    scored = [v for v in verdicts if v != "na"]
    if not scored:
        return None
    return 100 * sum(VERDICT_POINTS[v] for v in scored) / len(scored)


def score_store_level_check(verdict: Verdict) -> float | None:
    return None if verdict == "na" else 100 * VERDICT_POINTS[verdict]


def compute_scores(
    product_verdicts: dict[str, dict[str, Verdict]],
    store_verdicts: dict[str, Verdict],
) -> dict[str, int]:
    scores: dict[str, int] = {}
    for category in (
        "ucp_commerce_flows",
        "mcp_knowledge",
        "catalog_enrichment",
        "safety_policies",
    ):
        check_scores = []
        for check in CHECKS[category]:
            if check["level"] == "store":
                s = score_store_level_check(store_verdicts.get(check["id"], "na"))
            else:
                per_product = [product_verdicts.get(pid, {}).get(check["id"], "fail") for pid in product_verdicts]
                s = score_product_level_check(per_product)
            if s is not None:
                check_scores.append(s)
        scores[category] = round(sum(check_scores) / len(check_scores)) if check_scores else 0
    scores["overall"] = round(sum(scores.values()) / len(scores))
    return scores


def build_product_recommendations(verdicts: dict[str, Verdict], texts: dict[str, dict]) -> list[dict]:
    recs = []
    for check_id, verdict in verdicts.items():
        priority = priority_for(check_id, verdict)
        if priority is None:
            continue
        t = texts.get(check_id, {})
        recs.append({
            "check_id": check_id,
            "priority": priority,
            "enrichment": t.get("enrichment") or CHECK_BY_ID[check_id]["desc"],
            "why_it_matters_for_agents": t.get("why_it_matters_for_agents") or CHECK_BY_ID[check_id]["desc"],
            "example": t.get("example", ""),
        })
    return recs


def build_store_recommendations(
    store_verdicts: dict[str, Verdict],
    store_texts: dict[str, dict],
    product_verdicts: dict[str, dict[str, Verdict]],
    product_texts: dict[str, dict],
) -> list[dict]:
    from collections import defaultdict
    recs = []

    for check_id, verdict in store_verdicts.items():
        priority = priority_for(check_id, verdict)
        if priority is None:
            continue
        t = store_texts.get(check_id, {})
        recs.append({
            "check_id": check_id,
            "priority": priority,
            "enrichment": t.get("enrichment") or CHECK_BY_ID[check_id]["desc"],
            "why_it_matters_for_agents": t.get("why_it_matters_for_agents") or CHECK_BY_ID[check_id]["desc"],
            "example": t.get("example", ""),
            "affected_product_ids": [],
        })

    by_check: dict[str, list[str]] = defaultdict(list)
    for pid, verdicts in product_verdicts.items():
        for check_id, verdict in verdicts.items():
            if verdict in ("fail", "partial"):
                by_check[check_id].append(pid)

    for check_id, ids in by_check.items():
        if len(ids) > 1:  
            recs.append({
                "check_id": check_id,
                "priority": priority_for(check_id, "fail"),
                "enrichment": f"{CHECK_BY_ID[check_id]['desc']}",
                "why_it_matters_for_agents": CHECK_BY_ID[check_id]["desc"],
                "example": f"{len(ids)} products affected — see each product's own missing_enrichments for specifics.",
                "affected_product_ids": ids,
            })

    return recs