# app/services/scoring_rubric.py

from __future__ import annotations
from typing import Literal
from app.services.deterministic_checks import (
    PRODUCT_DETERMINISTIC_CHECKS,
    STORE_DETERMINISTIC_CHECKS,
)

DETERMINISTIC_CHECK_IDS = set(PRODUCT_DETERMINISTIC_CHECKS) | set(STORE_DETERMINISTIC_CHECKS)


def llm_product_check_ids() -> list[str]:
    """Only the product checks that still need AI judgment"""
    return list(dict.fromkeys(
        c["id"]
        for checks in CHECKS.values()
        for c in checks
        if c["level"] == "product"
        and c["id"] not in DETERMINISTIC_CHECK_IDS
    ))


def llm_store_check_ids() -> list[str]:
    """Only the store checks that still need AI judgment."""
    return list(dict.fromkeys(
        c["id"]
        for checks in CHECKS.values()
        for c in checks
        if c["level"] == "store"
        and c["id"] not in DETERMINISTIC_CHECK_IDS
        and c["id"] != "consistency"
    ))

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
        {"id": "contact_brand", "level": "store", "desc": "Contact details (email/phone) or brand/about content discoverable via shop metafields/metaobjects ONLY. Do NOT factor in policy-document text or placeholders — those are covered separately by policy_semantics and legal_pages."},
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

VERDICT_POINTS = {"pass": 1.0, "partial": 0.5, "fail": 0.0} 


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
                s = score_store_level_check(
                    store_verdicts.get(check["id"], "na")
                )
            else:
                per_product = [
                    product_verdicts.get(pid, {}).get(
                        check["id"],
                        "fail",
                    )
                    for pid in product_verdicts
                ]
                s = score_product_level_check(per_product)

            if s is not None:
                check_scores.append(s)

        if check_scores:
            scores[category] = round(
                sum(check_scores) / len(check_scores)
            )

    category_scores = list(scores.values())

    if category_scores:
        scores["overall"] = round(
            sum(category_scores) / len(category_scores)
        )

    return scores

def display_check_name(check_id: str) -> str:
    names = {
        "stable_ids_urls": "Stable IDs & URLs",
        "variant_selection": "Variant Selection",
        "pricing_clarity": "Pricing Clarity",
        "availability_signals": "Availability Signals",
        "variant_hygiene": "Variant Hygiene",
        "identifiers": "Identifiers",
        "product_guardrails": "Product Guardrails",
        "legal_pages": "Legal Pages",
        "store_guardrails": "Store Guardrails",
        "consistency": "Catalog Consistency",
    }

    return names.get(
        check_id,
        check_id.replace("_", " ").title(),
    )

def build_product_recommendations(
    verdicts: dict[str, Verdict],
    texts: dict[str, dict],
    issues: list[dict],
) -> list[dict]:

    recs = []

    # Group actual existing issues by check_id.
    issues_by_check: dict[str, list[dict]] = {}

    for issue in issues:
        if issue.get("status") != "existing":
            continue

        check_id = issue.get("check_id")

        if not check_id:
            continue

        issues_by_check.setdefault(check_id, []).append(issue)

    for check_id, verdict in verdicts.items():

        priority = priority_for(check_id, verdict)

        if priority is None:
            continue

        t = texts.get(check_id, {})

        # ---------------------------------------------------------
        # DETERMINISTIC PRODUCT CHECK
        # ---------------------------------------------------------
        # ---------------------------------------------------------
        if check_id in DETERMINISTIC_CHECK_IDS:

            check_issues = issues_by_check.get(check_id, [])

            if not check_issues:
                continue

            descriptions = []

            for issue in check_issues:
                description = issue.get("description")

                if description and description not in descriptions:
                    descriptions.append(description)

            why_it_matters = (
                "Resolving this issue helps agents reliably understand "
                "and act on this product without relying on missing "
                "or incomplete product data."
            )

            example = " ".join(descriptions)

            recs.append({
                "check_id": check_id,
                "priority": priority,
                "enrichment": display_check_name(check_id),
                "why_it_matters_for_agents": why_it_matters,
                "example": example,
            })

            continue

        # ---------------------------------------------------------
        # LLM PRODUCT CHECK
        # ---------------------------------------------------------
        # Keep the actual text generated by the LLM.
        # Never fall back to the rubric description.
        # ---------------------------------------------------------

        if (
            not t.get("enrichment")
            and not t.get("why_it_matters_for_agents")
            and not t.get("example")
        ):
            continue

        recs.append({
            "check_id": check_id,
            "priority": priority,
            "enrichment": t.get("enrichment", ""),
            "why_it_matters_for_agents": t.get(
                "why_it_matters_for_agents",
                "",
            ),
            "example": t.get("example", ""),
        })

    return recs


def build_store_recommendations(
    store_verdicts: dict[str, Verdict],
    store_texts: dict[str, dict],
    product_verdicts: dict[str, dict[str, Verdict]],
    product_texts: dict[str, dict],
    store_issues: list[dict],
) -> list[dict]:

    from collections import defaultdict

    recs = []

    # ---------------------------------------------------------
    # 1. GROUP ACTUAL STORE ISSUES BY CHECK
    # ---------------------------------------------------------

    issues_by_check: dict[str, list[dict]] = defaultdict(list)

    for issue in store_issues:
        if issue.get("status") != "existing":
            continue

        check_id = issue.get("check_id")

        if check_id:
            issues_by_check[check_id].append(issue)

    # ---------------------------------------------------------
    # 2. STORE-LEVEL RECOMMENDATIONS
    #    ONE recommendation per failed/partial check
    # ---------------------------------------------------------

    for check_id, verdict in store_verdicts.items():

        priority = priority_for(check_id, verdict)

        if priority is None:
            continue

        # Consistency has its own issue-driven recommendation
        # below because it is derived from catalog-wide issues.
        if check_id == "consistency":
            continue

        t = store_texts.get(check_id, {})

        # -----------------------------------------------------
        # DETERMINISTIC STORE CHECK
        # -----------------------------------------------------

        if check_id in DETERMINISTIC_CHECK_IDS:

            check_issues = issues_by_check.get(check_id, [])

            if not check_issues:
                continue

            descriptions = []

            for issue in check_issues:

                description = issue.get("description")

                if description and description not in descriptions:
                    descriptions.append(description)

            why_it_matters = (
                "Resolving these issues helps agents reliably "
                "understand the store's information and answer "
                "customer questions without relying on missing "
                "or incomplete data."
            )

            example = " ".join(descriptions)

            recs.append({
                "check_id": check_id,
                "priority": priority,
                "enrichment": display_check_name(check_id),
                "why_it_matters_for_agents": why_it_matters,
                "example": example,
                "affected_product_ids": [],
            })

            continue

        # -----------------------------------------------------
        # LLM STORE CHECK
        # -----------------------------------------------------
        # Keep the actual text generated by the LLM.
        # Never fall back to the rubric description.
        # -----------------------------------------------------

        if (
            not t.get("enrichment")
            and not t.get("why_it_matters_for_agents")
            and not t.get("example")
        ):
            continue

        recs.append({
            "check_id": check_id,
            "priority": priority,
            "enrichment": t.get("enrichment", ""),
            "why_it_matters_for_agents": t.get(
                "why_it_matters_for_agents",
                "",
            ),
            "example": t.get("example", ""),
            "affected_product_ids": [],
        })

    # ---------------------------------------------------------
    # 3. CROSS-PRODUCT RECOMMENDATIONS
    #    ONE recommendation per check affecting multiple products
    # ---------------------------------------------------------

    by_check: dict[str, list[str]] = defaultdict(list)

    for pid, verdicts in product_verdicts.items():

        for check_id, verdict in verdicts.items():

            if verdict in ("fail", "partial"):
                by_check[check_id].append(pid)

    for check_id, ids in by_check.items():

        if len(ids) <= 1:
            continue

        priority = priority_for(check_id, "fail")

        if priority is None:
            continue

        sample_text = {}

        for pid in ids:

            candidate = (
                product_texts
                .get(pid, {})
                .get(check_id, {})
            )

            if candidate.get("enrichment"):
                sample_text = candidate
                break

        # If this is a deterministic product check,
        # product_texts may intentionally be empty.
        # In that case the individual product recommendations
        # already contain the actual issue-derived information.

        if not sample_text:
            continue

        recs.append({
            "check_id": check_id,
            "priority": priority,
            "enrichment": sample_text.get(
                "enrichment",
                "",
            ),
            "why_it_matters_for_agents": sample_text.get(
                "why_it_matters_for_agents",
                "",
            ),
            "example": (
                f"{len(ids)} products affected — "
                "see each product's own missing_enrichments "
                "for specifics."
            ),
            "affected_product_ids": ids,
        })

    # ---------------------------------------------------------
    # 4. CONSISTENCY RECOMMENDATIONS
    #    Issue-driven and generated separately.
    # ---------------------------------------------------------

    consistency_issues = [
        issue
        for issue in store_issues
        if issue.get("check_id") == "consistency"
        and issue.get("status") == "existing"
    ]

    if consistency_issues:

        fields = []
        descriptions = []
        affected_product_ids = []

        for issue in consistency_issues:

            field = issue.get("field")
            description = issue.get("description")


            if field and field not in fields:
                fields.append(field)

            if description and description not in descriptions:
                descriptions.append(description)

            for pid in issue.get(
                "affected_product_ids",
                [],
            ):
                if pid not in affected_product_ids:
                    affected_product_ids.append(pid)

        priority = priority_for(
            "consistency",
            store_verdicts.get("consistency"),
        )

        if priority is not None:

            if fields:
                field_text = ", ".join(fields)

                why_it_matters = (
                    f"Keeping {field_text} consistent across "
                    "products helps agents interpret catalog "
                    "information reliably and compare products "
                    "without conflicting representations."
                )

            else:
                why_it_matters = (
                    "Keeping catalog data consistent across "
                    "products helps agents interpret and compare "
                    "products reliably."
                )

            recs.append({
                "check_id": "consistency",
                "priority": priority,
                "enrichment": display_check_name("consistency"),
                "why_it_matters_for_agents": why_it_matters,
                "example": " ".join(descriptions),
                "affected_product_ids": affected_product_ids,
            })

    return recs