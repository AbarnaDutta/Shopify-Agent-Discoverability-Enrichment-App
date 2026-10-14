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
        {"id": "stable_ids_urls", "level": "product",
         "desc": "Product has an id and a valid handle/URL."},
        {"id": "variant_selection", "level": "product",
         "desc": "Every option is named and every variant has a complete, unique option combination. N/A for a single default variant."},
        {"id": "pricing_clarity", "level": "product",
         "desc": "Every variant has a numeric price greater than 0."},
        {"id": "availability_signals", "level": "product",
         "desc": "Every variant exposes an available/availableForSale value. Sold out is NOT a defect."},
        {"id": "published_to_sales_channel", "level": "product",
         "desc": "Product is ACTIVE, published to at least one sales channel and has an Online Store URL. N/A when channel data is unavailable."},
        {"id": "fulfillment_context", "level": "store",
         "desc": "At least one active shipping method or pickup location AND at least one destination zone/country. N/A for digital-only catalogs or when store context is unavailable."},
    ],
    "mcp_knowledge": [
        {"id": "product_understanding", "level": "product",
         "desc": (
             "Judge the title and description with these questions. "
             "(1) CORE: does the title or description state what kind of product this is? "
             "If not -> issue_type insufficient_product_description. "
             "(2) Does the text state who the product is for OR what it is used for / the occasion? "
             "If not -> missing_target_audience. "
             "(3) ONLY if the product is a multi-piece set, kit or bundle: does the text list what is included? "
             "If not -> missing_included_items. For a single item this question does not apply: do NOT penalise it. "
             "Do NOT require a list of excluded items. "
             "Verdict: pass when every applicable question is answered yes; partial when (1) is yes but (2) or (3) is no; "
             "fail only when (1) is no."
         )},
        {"id": "product_clarity", "level": "product",
         "desc": (
             "Judge the product text with these questions. "
             "(1) Does the text contain at least ONE of: usage instructions, size/fit information, care/maintenance, "
             "ingredients or technical specifications? If not -> unclear_product_usage. "
             "(2) Does the text make a medical or health-efficacy claim WITHOUT any disclaimer or qualification? "
             "If yes -> unclarified_medical_claim. "
             "(3) Does the text promise financial returns or savings WITHOUT any disclaimer or qualification? "
             "If yes -> unclarified_financial_claim. "
             "A product that makes no such claims passes (2) and (3). "
             "Verdict: pass when (1) is yes and (2),(3) are clean; partial when exactly one question is a problem; "
             "fail only when the text has no usable content for (1) AND also carries an unqualified claim."
         )},
        {"id": "comparable_attributes", "level": "product",
         "desc": "Taxonomy category is assigned (when available in the data) and product_type is non-empty."},
        {"id": "policy_semantics", "level": "store",
         "desc": (
             "Evaluated ONCE for the whole store from the policy texts in Store Context (policies list: type + body). "
             "(1) Does the refund/return policy state a time window (a number of days or an explicit deadline)? "
             "If not -> missing_policy_deadline. Answer 'na' for this question when there is no refund policy "
             "(legal_pages owns a missing policy). "
             "(2) Does the refund/return policy state at least one exception or non-returnable condition? "
             "If not -> missing_policy_exception. "
             "(3) Does the shipping policy state which regions/countries are covered? If not -> missing_policy_region. "
             "Answer 'na' for this question when there is no shipping policy. "
             "Verdict: pass when every applicable question is yes; partial when some are no; "
             "fail only when (1) and (2) are both no. Return 'na' for the whole check if Store Context has no policy text."
         )},
        {"id": "faq_or_guidance", "level": "store",
         "desc": "A FAQ/help page, menu entry, or FAQ metaobject with entries exists."},
    ],
    "catalog_enrichment": [
        {"id": "identifiers", "level": "product",
         "desc": "Every variant has a unique SKU; any barcode present is a valid GTIN; barcodes are not mixed present/absent."},
        {"id": "rich_attributes", "level": "product",
         "desc": (
             "Is every concrete spec stated in the description (material, dimensions, capacity, power...) ALSO present "
             "in the product's metafields? If a spec has no matching metafield -> issue_type unstructured_product_attribute, "
             "and quote the spec text that has no metafield in the description of the issue. "
             "Return 'na' when the description states no concrete specs, or when the product payload has no "
             "'metafields' field at all (the data source did not supply them). "
             "Verdict: pass when every stated spec has a metafield; partial when some do; fail when none do."
         )},
        {"id": "variant_hygiene", "level": "product",
         "desc": "No generic option names (Title/Option1/Custom1...) or placeholder values when there is more than one variant. N/A for a single default variant."},
        {"id": "media_quality", "level": "product",
         "desc": "At least one image, and every image has alt text."},
        {"id": "consistency", "level": "store",
         "desc": "Within a taxonomy category/product type: shared metafield keys, same metafield types, same units."},
    ],
    "safety_policies": [
        {"id": "product_guardrails", "level": "product",
         "desc": "N/A unless the product is in a risky category (age-restricted, medical, weapons, financial, children's safety-critical); then a guardrail metafield (age limit, warning, human-review flag) exists."},
        {"id": "store_guardrails", "level": "store",
         "desc": "Only when risky products exist: a store-level age/region guardrail metafield or policy text. N/A otherwise."},
        {"id": "legal_pages", "level": "store",
         "desc": "Privacy, refund, terms (and shipping if shippable) policies each have enough text and no placeholder text."},
        {"id": "contact_brand", "level": "store",
         "desc": "A public contact channel and brand/about content are discoverable (pages, menus, contact policy, shop brand)."},
         {"id": "fulfillment_context", "level": "store",
          "desc": "At least one active shipping method or pickup location AND at least one destination zone/country. N/A for digital-only catalogs or when store context is unavailable."},
          {"id": "policy_semantics", "level": "store",
                   "desc": (
                       "Evaluated ONCE for the whole store from the policy texts in Store Context (policies list: type + body). "
                       "(1) Does the refund/return policy state a time window (a number of days or an explicit deadline)? "
                       "If not -> missing_policy_deadline. Answer 'na' for this question when there is no refund policy "
                       "(legal_pages owns a missing policy). "
                       "(2) Does the refund/return policy state at least one exception or non-returnable condition? "
                       "If not -> missing_policy_exception. "
                       "(3) Does the shipping policy state which regions/countries are covered? If not -> missing_policy_region. "
                       "Answer 'na' for this question when there is no shipping policy. "
                       "Verdict: pass when every applicable question is yes; partial when some are no; "
                       "fail only when (1) and (2) are both no. Return 'na' for the whole check if Store Context has no policy text."
                   )},
            {"id": "faq_or_guidance", "level": "store",
         "desc": "A FAQ/help page, menu entry, or FAQ metaobject with entries exists."},
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
                        "na",
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
        "published_to_sales_channel": "Sales Channel Publication",
        "variant_hygiene": "Variant Hygiene",
        "identifiers": "Identifiers",
        "product_guardrails": "Product Guardrails",
        "legal_pages": "Legal Pages",
        "store_guardrails": "Store Guardrails",
        "consistency": "Catalog Consistency",
        "comparable_attributes": "Product Category & Type",
        "media_quality": "Product Images",
        "fulfillment_context": "Shipping & Fulfillment",
        "contact_brand": "Contact & Brand Information",
        "faq_or_guidance": "FAQ & Help Content",
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

    # 1. GROUP ACTUAL STORE ISSUES BY CHECK
    issues_by_check: dict[str, list[dict]] = defaultdict(list)

    for issue in store_issues:
        if issue.get("status") != "existing":
            continue

        check_id = issue.get("check_id")

        if check_id:
            issues_by_check[check_id].append(issue)

    # 2. STORE-LEVEL RECOMMENDATIONS 
    for check_id, verdict in store_verdicts.items():

        priority = priority_for(check_id, verdict)

        if priority is None:
            continue

        if check_id == "consistency":
            continue

        t = store_texts.get(check_id, {})

        # DETERMINISTIC STORE CHECK
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

        # LLM STORE CHECK
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

    # 3. CROSS-PRODUCT RECOMMENDATIONS
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

    # 4. CONSISTENCY RECOMMENDATIONS 
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