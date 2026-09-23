# app/services/deterministic_checks.py

from __future__ import annotations
import re
from typing import Any

_PLACEHOLDER_PATTERNS = [
    re.compile(r"\[INSERT[^\]]*\]", re.I),
    re.compile(r"\{\{\s*[\w.]+\s*\}\}"),
    re.compile(r"\.\.\.\s*$"),
    re.compile(r"\bLINK\b", re.I),
    re.compile(r"\blorem ipsum\b", re.I),
    re.compile(r"goes here", re.I),
]

_GENERIC_OPTION_NAMES = {"title", "option1", "option2", "option3", "custom1", "custom2", "custom3"}

_RISKY_KEYWORDS = (
    "supplement", "vitamin", "medic", "cbd", "knife", "blade", "weapon", "firearm",
    "alcohol", "tobacco", "vape", "e-liquid", "adult", "lingerie", "baby", "infant",
    "child", "kids", "loan", "insurance", "financial",
)


def has_placeholder(text: str | None) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in _PLACEHOLDER_PATTERNS)


def _make_verdict(verdict: str, evidence: str, issue_type: str | None = None) -> dict[str, Any]:
    result = {"verdict": verdict, "evidence": evidence, "issues": []}
    if issue_type and verdict in ("partial", "fail"):
        result["issues"] = [{
            "issue_type": issue_type,
            "status": "existing",
            "description": evidence,
        }]
    return result


# ── PRODUCT-LEVEL DETERMINISTIC CHECKS ──────────────────────────────────

def check_stable_ids_urls(product: dict) -> dict:
    pid = product.get("id") or product.get("product_id")
    url = product.get("url") or product.get("handle")
    if not pid:
        return _make_verdict("fail", "Product has no id.", "missing_product_id")
    if not url:
        return _make_verdict("fail", f"Product {pid} has no URL/handle.", "missing_product_url")
    return _make_verdict("pass", f"Product has id '{pid}' and url '{url}'.")

def check_variant_selection(product: dict) -> dict:
    """Check whether variants expose enough option information for exact selection."""
    options = product.get("options") or []
    variants = product.get("variants") or []

    if not options or not variants:
        return {
            "verdict": "na",
            "evidence": "No options/variants to evaluate.",
            "issues": [],
        }

    option_names = [
        (option.get("name") or "").strip().lower()
        for option in options
    ]

    missing_option_names = [
        index
        for index, name in enumerate(option_names)
        if not name
    ]

    if missing_option_names:
        return _make_verdict(
            "fail",
            f"Option name(s) missing at position(s): {missing_option_names}.",
            "missing_option_name",
        )

    generic_names = [
        name
        for name in option_names
        if name in _GENERIC_OPTION_NAMES
    ]

    if generic_names:
        return _make_verdict(
            "partial",
            f"Generic option name(s) found: {generic_names}.",
            "generic_option_name",
        )

    expected_option_names = set(option_names)

    incomplete_variants = []

    for variant in variants:
        selected_options = variant.get("selectedOptions") or []

        selected_names = {
            (item.get("name") or "").strip().lower()
            for item in selected_options
            if item.get("name")
        }

        if selected_names != expected_option_names:
            incomplete_variants.append(
                variant.get("id")
                or variant.get("variant_id")
                or variant.get("title")
                or "unknown"
            )

    if incomplete_variants:
        return _make_verdict(
            "partial",
            (
                "Some variants do not contain a complete set of "
                f"selected options: {incomplete_variants}."
            ),
            "incomplete_selected_options",
        )

    option_value_sets: dict[str, set[str]] = {
        name: set()
        for name in expected_option_names
    }

    inconsistent_variants = []

    for variant in variants:
        selected_options = variant.get("selectedOptions") or []

        seen_names = set()

        for item in selected_options:
            name = (item.get("name") or "").strip().lower()
            value = (item.get("value") or "").strip()

            if not name:
                continue

            if name in seen_names:
                inconsistent_variants.append(
                    variant.get("id")
                    or variant.get("variant_id")
                    or variant.get("title")
                    or "unknown"
                )
                continue

            seen_names.add(name)

            if value:
                option_value_sets.setdefault(name, set()).add(value)

    if inconsistent_variants:
        return _make_verdict(
            "partial",
            (
                "Some variants contain inconsistent selected-option "
                f"structure: {inconsistent_variants}."
            ),
            "inconsistent_variant_options",
        )

    return _make_verdict(
        "pass",
        "Option names are meaningful and variants contain complete, consistent selected options.",
    )

def check_variant_hygiene(product: dict) -> dict:
    """Used for BOTH variant_selection and variant_hygiene — same underlying fact."""
    options = product.get("options") or []
    variants = product.get("variants") or []

    if not options or not variants:
        return {"verdict": "na", "evidence": "No options/variants to evaluate.", "issues": []}

    option_names = [(o.get("name") or "").strip().lower() for o in options]
    has_generic_option = any(name in _GENERIC_OPTION_NAMES for name in option_names)

    variant_titles = [(v.get("title") or "").strip().lower() for v in variants]
    all_default_title = bool(variant_titles) and all(t == "default title" for t in variant_titles)

    single_option = len(options) <= 1

    if has_generic_option and all_default_title and single_option:
        return _make_verdict(
            "fail",
            f"Option name(s) {[o.get('name') for o in options]}; every variant titled 'Default Title'; no real variant structure exists.",
            "generic_option_name",
        )
    if has_generic_option or all_default_title:
        return _make_verdict(
            "partial",
            f"Option name(s) {[o.get('name') for o in options]}; some generic naming or default-title variants present.",
            "generic_option_name",
        )
    return _make_verdict("pass", f"Option names {[o.get('name') for o in options]} are descriptive; variant titles are specific.")


def check_identifiers(product: dict) -> dict:
    variants = product.get("variants") or []
    if not variants:
        return {"verdict": "na", "evidence": "No variants to evaluate.", "issues": []}

    missing_sku = [v for v in variants if not v.get("sku")]
    missing_barcode = [v for v in variants if not v.get("barcode")]

    if len(missing_sku) == len(variants):
        return _make_verdict("fail", f"All {len(variants)} variant(s) have no SKU.", "missing_sku")
    if missing_sku:
        return _make_verdict("partial", f"{len(missing_sku)}/{len(variants)} variant(s) missing SKU.", "missing_sku")
    if missing_barcode:
        return _make_verdict("partial", f"{len(missing_barcode)}/{len(variants)} variant(s) missing barcode/GTIN.", "missing_gtin")
    return _make_verdict("pass", f"All {len(variants)} variant(s) have SKU and barcode.")


def check_pricing_clarity(product: dict) -> dict:
    variants = product.get("variants") or []
    if not variants:
        return {"verdict": "na", "evidence": "No variants to evaluate.", "issues": []}

    def is_zero(v):
        try:
            return float(v.get("price") or 0) == 0
        except (TypeError, ValueError):
            return True

    zero_priced = [v for v in variants if is_zero(v)]
    if len(zero_priced) == len(variants):
        return _make_verdict("fail", f"All {len(variants)} variant(s) priced 0.00 or missing.", "zero_price")
    if zero_priced:
        return _make_verdict("partial", f"{len(zero_priced)}/{len(variants)} variant(s) priced 0.00 or missing.", "zero_price")
    return _make_verdict("pass", f"All {len(variants)} variant(s) have a real, non-zero price.")


def check_availability_signals(product: dict) -> dict:
    variants = product.get("variants") or []
    if not variants:
        return {"verdict": "na", "evidence": "No variants to evaluate.", "issues": []}

    def is_unavailable(v):
        return not v.get("available") or (v.get("inventory_quantity") or 0) <= 0

    unavailable = [v for v in variants if is_unavailable(v)]
    if len(unavailable) == len(variants):
        return _make_verdict("fail", f"All {len(variants)} variant(s) unavailable / zero inventory.", "ambiguous_buyability")
    if unavailable:
        return _make_verdict("partial", f"{len(unavailable)}/{len(variants)} variant(s) unavailable / zero inventory.", "ambiguous_buyability")
    return _make_verdict("pass", f"All {len(variants)} variant(s) available with positive inventory.")


def _product_is_risky(product: dict) -> bool:
    haystack = " ".join([
        str(product.get("product_type") or ""),
        str(product.get("title") or ""),
        " ".join(product.get("tags") or []),
    ]).lower()
    return any(kw in haystack for kw in _RISKY_KEYWORDS)


def check_product_guardrails(product: dict) -> dict:
    if not _product_is_risky(product):
        return {
            "verdict": "na",
            "evidence": f"Product '{product.get('title')}' does not match any risky-category keyword.",
            "issues": [],
        }
    metafields = product.get("metafields") or {}
    guardrail_keys = [k for k in metafields.keys() if any(w in k.lower() for w in ("guardrail", "age", "warning", "not_suitable"))]
    if not guardrail_keys:
        return _make_verdict(
            "fail",
            f"Product '{product.get('title')}' matches a risky-category keyword but has no guardrail metafields.",
            "missing_warning",
        )
    return _make_verdict("pass", f"Guardrail metafield(s) present: {guardrail_keys}.")

def check_description_presence(product: dict) -> dict | None:
    """Deterministic: is description empty/whitespace-only? Returns None if
    a real description exists (defer to LLM for quality judgment)."""
    import re
    desc = (product.get("description") or "").strip()
    text_only = re.sub(r"<[^>]+>", "", desc).strip()
    if not text_only:
        return _make_verdict("fail", "Product description is empty.", "insufficient_product_description")
    return None


def check_product_type_presence(product: dict) -> dict | None:
    """Deterministic: is product_type empty? Returns None if present."""
    ptype = (product.get("product_type") or "").strip()
    if not ptype:
        return _make_verdict("partial", "product_type field is empty.", "missing_product_type")
    return None


# ── STORE-LEVEL DETERMINISTIC CHECKS ────────────────────────────────────

def check_legal_pages(store_context: dict | None) -> dict:
    if not store_context:
        return {"verdict": "na", "evidence": "No store context available (no Admin API connection).", "issues": []}

    shop = store_context.get("shop") or {}
    policies = {
        "privacy": (shop.get("privacyPolicy") or {}).get("body"),
        "refund": (shop.get("refundPolicy") or {}).get("body"),
        "shipping": (shop.get("shippingPolicy") or {}).get("body"),
        "terms": (shop.get("termsOfService") or {}).get("body"),
    }

    missing = [k for k, v in policies.items() if not v or len(v.strip()) < 20]
    if missing:
        return {
            "verdict": "fail",
            "evidence": f"Missing or empty policies: {missing}.",
            "issues": [
                {"issue_type": f"missing_{name}_policy", "status": "existing", "description": f"The {name} policy is missing or effectively empty."}
                for name in missing
            ],
        }

    placeholder = [k for k, v in policies.items() if has_placeholder(v)]
    if placeholder:
        return {
            "verdict": "partial",
            "evidence": f"Policies present but contain placeholder text: {placeholder}.",
            "issues": [
                {"issue_type": f"placeholder_{name}_policy", "status": "existing", "description": f"The {name} policy contains unfilled placeholder text."}
                for name in placeholder
            ],
        }

    return {"verdict": "pass", "evidence": "All four policies present with no placeholder text detected.", "issues": []}


def check_store_guardrails(store_context: dict | None) -> dict:
    if not store_context:
        return {"verdict": "na", "evidence": "No store context available (no Admin API connection).", "issues": []}

    shop = store_context.get("shop") or {}
    raw_metafields = (shop.get("metafields") or {}).get("edges") or []
    metafields = {
        f"{(e.get('node') or {}).get('namespace')}.{(e.get('node') or {}).get('key')}":
            (e.get('node') or {}).get('value')
        for e in raw_metafields
    }

    guardrail_fields = {
        k: v for k, v in metafields.items()
        if any(w in k.lower() for w in ("age_restrict", "restricted_region", "region_restrict", "age_gate"))
    }

    if not guardrail_fields:
        return {
            "verdict": "fail",
            "evidence": "No guardrail metafields (age restriction, restricted regions) found on the shop.",
            "issues": [{"issue_type": "missing_age_gating", "status": "existing", "description": "No shop-level guardrail metafields exist."}],
        }

    placeholder_fields = [k for k, v in guardrail_fields.items() if has_placeholder(v)]
    if placeholder_fields:
        return {
            "verdict": "partial",
            "evidence": f"Guardrail metafield(s) present but contain placeholder text: {placeholder_fields}.",
            "issues": [
                {"issue_type": "missing_region_restriction", "status": "existing", "description": f"Metafield '{k}' contains unfilled placeholder text."}
                for k in placeholder_fields
            ],
        }

    return {"verdict": "pass", "evidence": f"Guardrail metafield(s) present and specific: {list(guardrail_fields.keys())}.", "issues": []}


# ── DISPATCH TABLES ──────────────────────────────────────────────────────

PRODUCT_DETERMINISTIC_CHECKS = {
    "stable_ids_urls": check_stable_ids_urls,
    "variant_selection": check_variant_selection,
    "variant_hygiene": check_variant_hygiene,
    "identifiers": check_identifiers,
    "pricing_clarity": check_pricing_clarity,
    "availability_signals": check_availability_signals,
    "product_guardrails": check_product_guardrails,
}

STORE_DETERMINISTIC_CHECKS = {
    "legal_pages": check_legal_pages,
    "store_guardrails": check_store_guardrails,
}


def run_product_deterministic_checks(product: dict) -> dict[str, dict]:
    return {check_id: fn(product) for check_id, fn in PRODUCT_DETERMINISTIC_CHECKS.items()}


def run_store_deterministic_checks(store_context: dict | None) -> dict[str, dict]:
    return {check_id: fn(store_context) for check_id, fn in STORE_DETERMINISTIC_CHECKS.items()}

def check_catalog_consistency(
    products: list[dict],
    measurement_observations: list[dict] | None = None,
) -> dict:
    """
    Deterministic, store-agnostic catalog consistency check.

    It discovers structure from the actual catalog and only compares
    products that have enough shared catalog characteristics to be
    reasonably comparable.
    """

    if not products:
        return {
            "verdict": "na",
            "evidence": "No products available for consistency evaluation.",
            "issues": [],
            "affected_product_ids": [],
        }

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------

    def product_id(product: dict) -> str:
        return str(
            product.get("id")
            or product.get("product_id")
            or ""
        ).strip()

    def normalize(value: Any) -> str:
        return str(value or "").strip().lower()

    def get_product_type(product: dict) -> str:
        return normalize(product.get("product_type"))

    def get_option_names(product: dict) -> set[str]:
        names = set()

        for option in product.get("options") or []:
            name = normalize(option.get("name"))
            if name:
                names.add(name)

        return names

    def get_metafield_keys(product: dict) -> set[str]:
        metafields = product.get("metafields") or {}

        if isinstance(metafields, dict):
            return {
                str(key).strip()
                for key in metafields.keys()
                if str(key).strip()
            }

        if isinstance(metafields, list):
            keys = set()

            for item in metafields:
                node = item.get("node") or item

                namespace = str(
                    node.get("namespace") or ""
                ).strip()

                key = str(
                    node.get("key") or ""
                ).strip()

                if namespace and key:
                    keys.add(f"{namespace}.{key}")
                elif key:
                    keys.add(key)

            return keys

        return set()

    def get_metafield_values(product: dict) -> dict[str, Any]:
        metafields = product.get("metafields") or {}

        if isinstance(metafields, dict):
            return {
                str(key).strip(): value
                for key, value in metafields.items()
                if str(key).strip()
            }

        if isinstance(metafields, list):
            result = {}

            for item in metafields:
                node = item.get("node") or item

                namespace = str(
                    node.get("namespace") or ""
                ).strip()

                key = str(
                    node.get("key") or ""
                ).strip()

                if namespace and key:
                    result[f"{namespace}.{key}"] = node.get("value")
                elif key:
                    result[key] = node.get("value")

            return result

        return {}


    valid_products = [
        product
        for product in products
        if product_id(product)
    ]

    if len(valid_products) < 2:
        return {
            "verdict": "na",
            "evidence": "Fewer than two identifiable products are available for consistency evaluation.",
            "issues": [],
            "affected_product_ids": [],
        }


    groups: dict[str, list[dict]] = {}

    for product in valid_products:
        pid = product_id(product)

        product_type = get_product_type(product)
        option_names = get_option_names(product)

        if product_type and product_type not in {
            "default",
            "general",
            "other",
        }:
            group_key = f"type:{product_type}"

        elif option_names:
            group_key = (
                "options:"
                + "|".join(sorted(option_names))
            )

        else:
            continue

        groups.setdefault(group_key, []).append(product)

    comparable_groups = [
        group
        for group in groups.values()
        if len(group) >= 2
    ]

    if not comparable_groups:
        return {
            "verdict": "pass",
            "evidence": (
                "No sufficiently comparable product groups were "
                "found, so no catalog inconsistency was identified."
            ),
            "issues": [],
            "affected_product_ids": [],
        }

    issues = []
    affected_product_ids: set[str] = set()

    # ---------------------------------------------------------
    # 1. Compare option structures inside comparable groups
    # ---------------------------------------------------------

    for group in comparable_groups:

        option_sets: dict[str, set[str]] = {}

        for product in group:
            pid = product_id(product)
            option_sets[pid] = get_option_names(product)

        all_options = set()

        for options in option_sets.values():
            all_options.update(options)

        for option_name in sorted(all_options):

            present_ids = {
                pid
                for pid, options in option_sets.items()
                if option_name in options
            }

            missing_ids = {
                pid
                for pid, options in option_sets.items()
                if option_name not in options
            }

            if (
                present_ids
                and missing_ids
                and len(present_ids) > len(group) / 2
            ):
                affected_product_ids.update(missing_ids)

                issues.append({
                    "issue_type": "inconsistent_option_structure",
                    "status": "existing",
                    "description": (
                        f"Comparable products do not share the "
                        f"same option structure. Option "
                        f"'{option_name}' is present on "
                        f"{len(present_ids)}/{len(group)} "
                        f"comparable products."
                    ),
                    "field": "options.name",
                    "affected_product_ids": sorted(missing_ids),
                })

    # ---------------------------------------------------------
    # 2. Compare dynamically discovered metafield structure
    # ---------------------------------------------------------

    for group in comparable_groups:

        metafields_by_product: dict[str, set[str]] = {}

        for product in group:
            pid = product_id(product)
            metafields_by_product[pid] = get_metafield_keys(product)

        all_keys = set()

        for keys in metafields_by_product.values():
            all_keys.update(keys)

        for key in sorted(all_keys):

            present_ids = {
                pid
                for pid, keys in metafields_by_product.items()
                if key in keys
            }

            missing_ids = {
                pid
                for pid, keys in metafields_by_product.items()
                if key not in keys
            }

            if (
                present_ids
                and missing_ids
                and len(present_ids) > len(group) / 2
            ):
                affected_product_ids.update(missing_ids)

                issues.append({
                    "issue_type": "inconsistent_metafield_structure",
                    "status": "existing",
                    "description": (
                        f"Metafield '{key}' is used by "
                        f"{len(present_ids)}/{len(group)} "
                        f"comparable products but is missing from "
                        f"{len(missing_ids)}."
                    ),
                    "field": key,
                    "affected_product_ids": sorted(missing_ids),
                })


    for group in comparable_groups:

        values_by_field: dict[str, list[tuple[str, Any]]] = {}

        for product in group:
            pid = product_id(product)

            for key, value in get_metafield_values(product).items():
                if value in (None, ""):
                    continue

                values_by_field.setdefault(key, []).append(
                    (pid, value)
                )

        for field, entries in values_by_field.items():

            if len(entries) < 2:
                continue

            def value_shape(value: Any) -> str:
                if isinstance(value, bool):
                    return "boolean"

                if isinstance(value, int):
                    return "integer"

                if isinstance(value, float):
                    return "decimal"

                if isinstance(value, list):
                    return "list"

                if isinstance(value, dict):
                    return "object"

                return "text"

            shapes: dict[str, list[str]] = {}

            for pid, value in entries:
                shape = value_shape(value)
                shapes.setdefault(shape, []).append(pid)

            if len(shapes) <= 1:
                continue

            affected = set()

            for ids in shapes.values():
                affected.update(ids)

            affected_product_ids.update(affected)

            issues.append({
                "issue_type": "inconsistent_attribute_format",
                "status": "existing",
                "description": (
                    f"Comparable products use different data "
                    f"formats for metafield '{field}': "
                    f"{sorted(shapes.keys())}."
                ),
                "field": field,
                "affected_product_ids": sorted(affected),
            })
            
    # ---------------------------------------------------------
    # 4. Compare measurement dimensions inside comparable groups
    # ---------------------------------------------------------

    measurement_observations = measurement_observations or []

    product_group_by_id: dict[str, int] = {}

    for group_index, group in enumerate(comparable_groups):
        for product in group:
            pid = product_id(product)
            if pid:
                product_group_by_id[pid] = group_index

    measurements_by_group_field: dict[
        tuple[int, str],
        list[dict],
    ] = {}

    for observation in measurement_observations:
        if not isinstance(observation, dict):
            continue

        pid = str(observation.get("product_id") or "").strip()
        field = normalize(observation.get("field"))
        dimension = normalize(observation.get("dimension"))

        if not pid or not field or not dimension:
            continue

        group_index = product_group_by_id.get(pid)

        if group_index is None:
            continue

        measurements_by_group_field.setdefault(
            (group_index, field),
            [],
        ).append({
            "product_id": pid,
            "raw_value": str(
                observation.get("raw_value") or ""
            ).strip(),
            "unit": str(
                observation.get("unit") or ""
            ).strip(),
            "dimension": dimension,
        })

    for (group_index, field), observations in (
        measurements_by_group_field.items()
    ):
        dimensions = {
            observation["dimension"]
            for observation in observations
            if observation.get("dimension")
        }

        if len(dimensions) <= 1:
            continue

        affected = {
            observation["product_id"]
            for observation in observations
        }

        if not affected:
            continue

        affected_product_ids.update(affected)

        issues.append({
            "issue_type": "inconsistent_attribute_units",
            "status": "existing",
            "description": (
                f"Comparable products use measurements with "
                f"different physical dimensions for '{field}': "
                f"{sorted(dimensions)}."
            ),
            "field": field,
            "affected_product_ids": sorted(affected),
        })
    # ---------------------------------------------------------
    # Final deterministic verdict
    # ---------------------------------------------------------

    total_count = len(valid_products)
    affected_count = len(affected_product_ids)

    if affected_count == 0:
        verdict = "pass"
    else:
        ratio = affected_count / total_count

        if ratio >= 0.9:
            verdict = "fail"
        else:
            verdict = "partial"

    return {
        "verdict": verdict,
        "evidence": (
            f"{affected_count}/{total_count} identifiable product(s) "
            f"were affected by deterministic catalog consistency checks."
        ),
        "issues": issues,
        "affected_product_ids": sorted(affected_product_ids),
    }
