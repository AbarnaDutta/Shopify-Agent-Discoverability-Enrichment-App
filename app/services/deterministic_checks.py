# app/services/deterministic_checks.py
from __future__ import annotations

import html
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse


def _uniq(ids) -> list[str]:
    return list(dict.fromkeys(str(i) for i in ids if i))


# ── config ──
MIN_POLICY_WORDS = 10
MIN_FAQ_WORDS = 30
CONSISTENCY_MAJORITY = 0.5      
CONSISTENCY_FAIL_RATIO = 0.9   

GENERIC_OPTION_NAMES = {"title", "option", "option1", "option2", "option3",
                        "custom", "custom1", "custom2", "custom3", "variant", "default"}
GENERIC_OPTION_VALUES = {"default title", "default", "option1", "option2", "option3",
                         "custom", "undefined", "null"}
GENERIC_PRODUCT_TYPES = {"shop", "general", "default", "products", "product", "other", "others",
                         "uncategorized", "uncategorised", "misc", "miscellaneous", "all", "item", "items"}
CONTACT_TOKENS = {"contact", "kontakt", "contacto", "contato", "contatto"}
ABOUT_TOKENS = {"about", "uber", "ueber", "propos", "acerca", "sobre", "chi", "story"}
FAQ_TOKENS = {"faq", "faqs", "help", "questions", "fragen", "preguntas", "perguntas", "domande", "aide"}
AGE_TAXONOMY_SEGMENTS = {"alcoholic beverages", "tobacco products", "weapons", "mature"}
WARNING_TAXONOMY_SEGMENTS = {"vitamins & supplements"}
_AGE_RE = re.compile(
    r"\b(?:alcohol(?![\s-]*free)|tobacco|cigars?|cigarettes?|vapes?|vaping|e-liquids?|cannabis|cbd|"
    r"knife|knives|firearms?|ammunition|weapons?|lingerie)\b", re.I)
_WARNING_RE = re.compile(
    r"\b(?:supplements?|vitamins?|medicin(?:e|al)|pharmaceuticals?|infant|loans?|insurance)\b", re.I)

AGE_GUARD_TOKENS = {"age", "restriction", "restrictions"}
WARNING_GUARD_TOKENS = {"warning", "warnings", "hazard", "hazards", "allergen", "allergens",
                        "safety", "disclaimer"}
GENERIC_GUARD_TOKENS = {"guardrail", "guardrails"}

_PLACEHOLDER_PATTERNS = [
    re.compile(r"\[\s*(?:insert|your|add|company|store|business)[^\]]*\]", re.I),
    re.compile(r"\{\{\s*[\w.]+\s*\}\}"),
    re.compile(r"\blorem ipsum\b", re.I),
    re.compile(r"\bgoes here\b", re.I),
    re.compile(r"\b(?:TODO|TBD)\b"),
    re.compile(r"\byour (?:company|store|business) name\b", re.I),
]

_STORE_GUARD_TOKENS = {"age", "restriction", "restrictions", "region", "regions", "gate"}
_STORE_GUARD_TEXT_RE = re.compile(
    r"\b(?:age\s+(?:restriction|limit|verification|gate)|(?:18|21)\s*(?:\+|years?|or older)|"
    r"restricted\s+(?:regions?|countries)|do(?:es)? not ship to)\b", re.I)

_DELIVERY_TIME_RE = re.compile(
    r"\b\d+\s*(?:[-–]|to|bis|à|a)?\s*(?:\d+\s*)?"
    r"(?:business\s+days?|working\s+days?|days?|weeks?|hours?|werktage?n?|tage?n?|wochen|"
    r"jours?|semaines?|d[ií]as?|semanas?)\b"
    r"|\b(?:same[- ]day|next[- ]day|overnight)\b", re.I)

# Store checks that need Admin store context. Without usable context they are NA, never a defect.
STORE_CONTEXT_REQUIRED_CHECKS = {
    "fulfillment_context", "policy_semantics", "faq_or_guidance",
    "store_guardrails", "legal_pages", "contact_brand",
}

NA_UNKNOWN_REASONS = {"no_store_context", "fetch_failed", "incomplete_data"}


# ── helpers ──────────────────────────────────────────────────────────────

def strip_html(text: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def _words(text: str | None) -> list[str]:
    return re.findall(r"\w+", text or "", flags=re.UNICODE)


def _tokens(text: str | None) -> set[str]:
    """Unicode-aware (accented / non-Latin words are kept)."""
    return {t for t in re.split(r"[\W_]+", (text or "").lower()) if t}


def has_placeholder(text: str | None) -> bool:
    return any(p.search(strip_html(text)) for p in _PLACEHOLDER_PATTERNS)


def _vid(v: dict) -> str | None:
    x = v.get("id") or v.get("variant_id")
    return str(x) if x else None


def _oid(o: dict) -> str | None:
    x = o.get("id") or o.get("option_id")
    return str(x) if x else None


def _issue(issue_type: str, description: str, variant_ids=None, option_ids=None, **extra) -> dict:
    return {"issue_type": issue_type, "status": "existing", "description": description,
            "affected_variant_ids": _uniq(variant_ids or []),
            "affected_option_ids": _uniq(option_ids or []), **extra}


def _verdict(verdict: str, evidence: str, issues=None) -> dict:
    return {"verdict": verdict, "evidence": evidence, "issues": issues or []}


def _na(evidence: str, reason: str = "not_applicable") -> dict:
    """reason: not_applicable | no_store_context | fetch_failed | incomplete_data | nothing_to_compare"""
    return {"verdict": "na", "evidence": evidence, "issues": [], "na_reason": reason}


def _graded(evidence_ok: str, issues: list[dict], checked: int, failed: int, *,
            fail_if_core: bool = False) -> dict:
    """pass when no issues; fail when a core requirement is unmet or everything failed; else partial.
    checked=0 disables the 'everything failed' rule (only fail_if_core can produce fail)."""
    if not issues:
        return _verdict("pass", evidence_ok)
    verdict = "fail" if (fail_if_core or (checked and failed >= checked)) else "partial"
    return _verdict(verdict, " ".join(i["description"] for i in issues), issues)


def store_context_usable(ctx: dict | None) -> bool:
    """Single definition of 'usable store context'. Use it everywhere (report_builder too)."""
    return bool(ctx) and "sections" in ctx


def is_default_variant_product(product: dict) -> bool:
    """Shopify's auto-created single variant (option 'Title' / value 'Default Title')."""
    variants = product.get("variants") or []
    options = product.get("options") or []
    if len(variants) != 1:
        return False
    if product.get("has_only_default_variant") is True:
        return True
    return (len(options) == 1 and (options[0].get("name") or "").strip().lower() == "title"
            and (variants[0].get("title") or "").strip().lower() == "default title")


def _valid_https_url(url: str) -> bool:
    u = str(url).strip()
    if re.search(r"\s", u):
        return False
    if u.startswith("/"):                     
        return True
    try:
        p = urlparse(u)
    except ValueError:
        return False
    return p.scheme == "https" and bool(p.netloc)


# ── PRODUCT: identity / publication ──────────────────────────────────────

def check_stable_ids_urls(product: dict) -> dict:
    pid, handle = product.get("id"), product.get("handle")
    url = product.get("online_store_url") or product.get("url")
    issues = []
    if not pid:
        issues.append(_issue("missing_product_id", "Product has no id."))
    if not handle:
        issues.append(_issue("missing_product_url", f"Product {pid} has no handle."))
    elif not re.fullmatch(r"[^\s/?#]+", str(handle)):
        issues.append(_issue("invalid_product_url", f"Handle '{handle}' is not a valid URL slug."))
    if url and not _valid_https_url(url):
        issues.append(_issue("invalid_product_url", f"Product URL '{url}' is not a valid https URL."))
    return _graded(f"Product has id and valid handle '{handle}'.", issues, 3, len(issues),
                   fail_if_core=any(i["issue_type"] == "missing_product_id" for i in issues))


def check_published_to_sales_channel(product: dict) -> dict:
    if "published_channels" not in product:
        return _na("Sales-channel publication is only known for Admin-API audits.", "incomplete_data")
    channels = product.get("published_channels") or []
    if product.get("status") not in (None, "ACTIVE"):
        msg = f"Product status is {product.get('status')}, so it is not sellable."
        return _verdict("fail", msg, [_issue("not_published_to_any_channel", msg)])
    if not channels:
        msg = "Product is not published to any sales channel."
        return _verdict("fail", msg, [_issue("not_published_to_any_channel", msg)])
    if not product.get("online_store_url"):
        msg = f"Published to {channels} but has no Online Store URL."
        return _verdict("partial", msg, [_issue("not_published_online_store", msg)])
    return _verdict("pass", f"Published to {channels}.")


# ── PRODUCT: variants ────────────────────────────────────────────────────

def _selected_name_list(variant: dict) -> list[str]:
    return [(s.get("name") or "").strip().lower()
            for s in (variant.get("selectedOptions") or []) if (s.get("name") or "").strip()]


def check_variant_selection(product: dict) -> dict:
    options = product.get("options") or []
    variants = product.get("variants") or []
    if is_default_variant_product(product):
        return _na("Single default variant: nothing for an agent to select.")
    if not variants:
        return _na("No variants were collected for this product (incomplete data); selection cannot be evaluated.",
                   "incomplete_data")
    if not options:
        if len(variants) == 1:
            return _na("Single variant without options: nothing to select.")
        return _graded("", [_issue("incomplete_selected_options",
                                   f"{len(variants)} variants exist but the product defines no options, so an agent cannot choose between them.",
                                   variant_ids=[_vid(v) for v in variants])],
                       len(variants), len(variants), fail_if_core=True)

    issues = []
    names = [(o.get("name") or "").strip() for o in options]
    missing = [o for o, n in zip(options, names) if not n]
    if missing:
        issues.append(_issue("missing_option_name", f"{len(missing)} option(s) have no name.",
                             option_ids=[_oid(o) for o in missing]))

    lowered = [n.lower() for n in names if n]
    dup_names = {n for n in lowered if lowered.count(n) > 1}
    if dup_names:
        issues.append(_issue("inconsistent_variant_options", f"Duplicate option name(s): {sorted(dup_names)}.",
                             option_ids=[_oid(o) for o, n in zip(options, names) if n.lower() in dup_names]))

    expected = set(lowered)
    incomplete = [v for v in variants if set(_selected_name_list(v)) != expected]
    incomplete_ids = {id(v) for v in incomplete}
    if incomplete:
        issues.append(_issue("incomplete_selected_options",
                             f"{len(incomplete)}/{len(variants)} variants lack a complete set of selected options.",
                             variant_ids=[_vid(v) for v in incomplete]))

    dup_in_variant = [v for v in variants
                      if id(v) not in incomplete_ids
                      and len(_selected_name_list(v)) != len(set(_selected_name_list(v)))]
    combos: dict[tuple, list[dict]] = {}
    for v in variants:
        if id(v) in incomplete_ids:
            continue
        key = tuple(sorted(((s.get("name") or "").strip().lower(), (s.get("value") or "").strip().lower())
                           for s in (v.get("selectedOptions") or [])))
        combos.setdefault(key, []).append(v)
    dupes = [v for g in combos.values() if len(g) > 1 for v in g]
    bad = list({id(v): v for v in dupes + dup_in_variant}.values())
    if bad:
        issues.append(_issue("inconsistent_variant_options",
                             f"{len(bad)} variants repeat an option or share an identical option combination "
                             f"(possible ambiguity; an agent can still select by variant id).",
                             variant_ids=[_vid(v) for v in bad]))

    failed = len(missing) + len(dup_names) + len(incomplete) + len(bad)
    return _graded("Options are named and every variant has a unique, complete option combination.",
                   issues, len(options) + len(variants), failed)


def check_variant_hygiene(product: dict) -> dict:
    options = product.get("options") or []
    variants = product.get("variants") or []
    if is_default_variant_product(product):
        return _na("Single default variant: no variant structure to evaluate.")
    if not variants or not options:
        return _na("No variants/options were collected (incomplete data); hygiene cannot be evaluated.",
                   "incomplete_data")

    issues = []
    generic_opts = [o for o in options if (o.get("name") or "").strip().lower() in GENERIC_OPTION_NAMES]
    if generic_opts:
        issues.append(_issue("generic_option_name",
                             f"Generic option name(s): {[o.get('name') for o in generic_opts]}.",
                             option_ids=[_oid(o) for o in generic_opts]))

    generic_vals = [v for v in variants
                    if any((s.get("value") or "").strip().lower() in GENERIC_OPTION_VALUES
                           for s in (v.get("selectedOptions") or []))]
    if generic_vals and len(variants) > 1:
        issues.append(_issue("generic_option_value",
                             f"{len(generic_vals)} variants use a placeholder option value (e.g. 'Default Title').",
                             variant_ids=[_vid(v) for v in generic_vals]))

    spellings: dict[tuple[str, str], set[str]] = {}
    for v in variants:
        for s in (v.get("selectedOptions") or []):
            val = (s.get("value") or "").strip()
            if val:
                spellings.setdefault(((s.get("name") or "").strip().lower(), val.lower()), set()).add(val)
    conflicting = {k for k, forms in spellings.items() if len(forms) > 1}
    if conflicting:
        affected = [v for v in variants for s in (v.get("selectedOptions") or [])
                    if ((s.get("name") or "").strip().lower(), (s.get("value") or "").strip().lower()) in conflicting]
        issues.append(_issue("inconsistent_option_values",
                             f"Option value(s) written inconsistently: {sorted(k[1] for k in conflicting)}.",
                             variant_ids=[_vid(v) for v in {id(v): v for v in affected}.values()]))

    failed = len(generic_opts) + (len(generic_vals) if len(variants) > 1 else 0) + len(conflicting)
    return _graded("Option names and values are descriptive and consistent.", issues,
                   len(options) + len(variants), failed)


def _to_decimal(raw) -> Decimal | None:
    try:
        d = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


def check_pricing_clarity(product: dict) -> dict:
    """missing / non-numeric / negative = invalid data. Zero can be intentional, so it is a soft signal
    (never worse than partial)."""
    variants = product.get("variants") or []
    if not variants:
        return _na("No variants to evaluate.", "incomplete_data")
    missing, bad, negative, zero = [], [], [], []
    for v in variants:
        raw = v.get("price")
        if raw in (None, ""):
            missing.append(v)
            continue
        d = _to_decimal(raw)
        if d is None:
            bad.append(v)
        elif d < 0:
            negative.append(v)
        elif d == 0:
            zero.append(v)

    issues = []
    if missing:
        issues.append(_issue("missing_price", f"{len(missing)} variant(s) have no price.",
                             variant_ids=[_vid(v) for v in missing]))
    invalid = bad + negative
    if invalid:
        parts = []
        if bad:
            parts.append(f"{len(bad)} non-numeric")
        if negative:
            parts.append(f"{len(negative)} negative")
        issues.append(_issue("invalid_price", f"{' and '.join(parts)} price value(s).",
                             variant_ids=[_vid(v) for v in invalid]))
    if zero:
        issues.append(_issue("zero_price", f"{len(zero)} variant(s) are priced at 0 (confirm this is intentional).",
                             variant_ids=[_vid(v) for v in zero]))

    if not issues:
        return _verdict("pass", f"All {len(variants)} variant(s) have a numeric, positive price.")
    hard = len(missing) + len(invalid)
    verdict = "fail" if hard and hard >= len(variants) else "partial"
    return _verdict(verdict, " ".join(i["description"] for i in issues), issues)


def check_availability_signals(product: dict) -> dict:
    """Being SOLD OUT is not a defect. Not being able to tell is."""
    variants = product.get("variants") or []
    if not variants:
        return _na("No variants to evaluate.", "incomplete_data")
    no_signal = [v for v in variants if not isinstance(v.get("available"), bool)]
    issues = []
    if no_signal:
        issues.append(_issue("missing_inventory_signal",
                             f"{len(no_signal)} variant(s) have no available/availableForSale value.",
                             variant_ids=[_vid(v) for v in no_signal]))
    sold_out = sum(1 for v in variants if v.get("available") is False)
    return _graded(f"All variants expose a clear buyable-now signal ({sold_out} currently sold out).",
                   issues, len(variants), len(no_signal))


# ── PRODUCT: identifiers ─────────────────────────────────────────────────

def _gtin_digits(code: str | None) -> str | None:
    """Digits of a barcode that is DECLARED in GTIN shape (numeric, 8/12/13/14 digits), else None.
    Non-numeric or odd-length barcodes may be internal codes and are not judged as GTINs."""
    digits = re.sub(r"[\s-]", "", code or "")
    return digits if digits.isdigit() and len(digits) in (8, 12, 13, 14) else None


def is_valid_gtin(code: str | None) -> bool:
    digits = _gtin_digits(code)
    if not digits or set(digits) == {"0"}:
        return False
    nums = [int(c) for c in digits]
    check = nums.pop()
    total = sum(n * (3 if i % 2 == 0 else 1) for i, n in enumerate(reversed(nums)))
    return (10 - total % 10) % 10 == check


def check_identifiers(product: dict) -> dict:
    variants = product.get("variants") or []
    if not variants:
        return _na("No variants to evaluate.", "incomplete_data")
    issues = []

    no_sku = [v for v in variants if not (v.get("sku") or "").strip()]
    if no_sku:
        issues.append(_issue("missing_sku", f"{len(no_sku)}/{len(variants)} variant(s) have no SKU.",
                             variant_ids=[_vid(v) for v in no_sku]))
    skus = [v["sku"].strip().lower() for v in variants if (v.get("sku") or "").strip()]
    dup_skus = {s for s in skus if skus.count(s) > 1}
    if dup_skus:
        dv = [v for v in variants if (v.get("sku") or "").strip().lower() in dup_skus]
        issues.append(_issue("duplicate_sku", f"{len(dv)} variants share a SKU (case-insensitive).",
                             variant_ids=[_vid(v) for v in dv]))

    gtin_like = [v for v in variants if _gtin_digits(v.get("barcode"))]
    bad = [v for v in gtin_like if not is_valid_gtin(v["barcode"])]
    if bad:
        issues.append(_issue("invalid_gtin", f"{len(bad)} GTIN-format barcode(s) fail check-digit validation or are all zeros.",
                             variant_ids=[_vid(v) for v in bad]))
    without = [v for v in variants if not (v.get("barcode") or "").strip()]
    if without and gtin_like:
        issues.append(_issue("missing_gtin",
                             f"{len(without)}/{len(variants)} variant(s) have no barcode while others carry a GTIN.",
                             variant_ids=[_vid(v) for v in without]))

    failed = len(no_sku) + len(bad) + (len(without) if gtin_like else 0)
    gtin_note = ("Declared GTINs pass check-digit validation." if gtin_like
                 else "No GTIN-format barcodes supplied; GTIN validation not performed.")
    return _graded(f"All variants have unique SKUs. {gtin_note}", issues, len(variants), failed,
                   fail_if_core=len(no_sku) == len(variants))


def find_cross_product_duplicate_skus(products: list[dict]) -> dict[str, dict]:
    """Catalog-level: SKUs (case-insensitive) used by variants of DIFFERENT products.
    Returns {product_id: {"skus": [...], "variant_ids": [...]}}."""
    owners: dict[str, list[tuple[str, str | None]]] = {}
    for p in products:
        pid = str(p.get("id") or p.get("product_id") or "").strip()
        if not pid:
            continue
        for v in p.get("variants") or []:
            sku = (v.get("sku") or "").strip().lower()
            if sku:
                owners.setdefault(sku, []).append((pid, _vid(v)))
    result: dict[str, dict] = {}
    for sku, entries in owners.items():
        pids = {e[0] for e in entries}
        if len(pids) < 2:
            continue
        for pid in pids:
            r = result.setdefault(pid, {"skus": [], "variant_ids": []})
            r["skus"].append(sku)
            r["variant_ids"] += [vid for p_, vid in entries if p_ == pid]
    return result


def apply_cross_product_duplicate_skus(verdict: str, issues: list[dict], pid: str,
                                       dup_map: dict[str, dict]) -> tuple[str, list[dict]]:
    """Fold a cross-product duplicate-SKU finding into a product's identifiers result."""
    info = dup_map.get(str(pid))
    if not info:
        return verdict, issues
    shown = sorted(set(info["skus"]))[:5]
    desc = f"Possible duplicate SKU shared with other products: {shown}."
    issues = [dict(i) for i in issues]
    existing = next((i for i in issues if i.get("issue_type") == "duplicate_sku"), None)
    if existing:
        existing["affected_variant_ids"] = _uniq((existing.get("affected_variant_ids") or []) + info["variant_ids"])
    else:
        issues.append(_issue("duplicate_sku", desc, variant_ids=info["variant_ids"]))
    return ("partial" if verdict == "pass" else verdict), issues


# ── PRODUCT: taxonomy, media, guardrails ─────────────────────────────────

def check_comparable_attributes(product: dict) -> dict:
    issues = []
    has_category_field = "category" in product        # absent on public audits
    cat = product.get("category")
    if has_category_field and not (isinstance(cat, dict) and cat.get("id")):
        issues.append(_issue("missing_taxonomy_category", "No Shopify standard taxonomy category is assigned."))
    ptype = (product.get("product_type") or "").strip()
    if not ptype:
        issues.append(_issue("missing_product_type", "product_type is empty."))
    elif ptype.lower() in GENERIC_PRODUCT_TYPES:
        issues.append(_issue("generic_product_type",
                             f"product_type '{ptype}' is too generic to help an agent categorize or compare the product."))
    return _graded("Taxonomy category and a specific product type are set.", issues,
                   2 if has_category_field else 1, len(issues))


def check_media_quality(product: dict) -> dict:
    """Media COMPLETENESS (presence + alt text); not whether the image is good or loads."""
    if "images" not in product:
        return _na("Image data not available for this audit source.", "incomplete_data")
    images = product.get("images") or []
    if not images:
        if "media_truncated" in (product.get("data_warnings") or []):
            return _na("No image seen in the collected media, but media was truncated; cannot confirm there is none.",
                       "incomplete_data")
        return _verdict("fail", "Product has no images.",
                        [_issue("missing_product_image", "Product has no images.")])
    no_alt = [i for i in images if not (i.get("alt") or "").strip()]
    if no_alt:
        msg = f"{len(no_alt)}/{len(images)} images have no alt text."
        return _verdict("partial", msg, [_issue("missing_image_alt", msg)])
    return _verdict("pass", f"{len(images)} image(s), all with alt text.")


def _risk_kinds(product: dict) -> set[str]:
    """SUSPECTED risk kinds from taxonomy + title/type/tags. Keyword matching is heuristic."""
    kinds: set[str] = set()
    cat = ((product.get("category") or {}).get("fullName") or "").lower()
    segments = {s.strip() for s in cat.split(">") if s.strip()}
    if segments & AGE_TAXONOMY_SEGMENTS:
        kinds.add("age")
    if segments & WARNING_TAXONOMY_SEGMENTS:
        kinds.add("warning")
    hay = " ".join([str(product.get("product_type") or ""), str(product.get("title") or ""),
                    " ".join(product.get("tags") or [])])
    if _AGE_RE.search(hay):
        kinds.add("age")
    if _WARNING_RE.search(hay):
        kinds.add("warning")
    return kinds


def _populated(meta) -> bool:
    return isinstance(meta, dict) and str(meta.get("value") or "").strip() not in ("", "[]", "{}", "null", "false")


def check_product_guardrails(product: dict) -> dict:
    """Disclosure SIGNALS only: a populated metafield is not proof of enforcement."""
    kinds = _risk_kinds(product)
    if not kinds:
        return _na(f"Product '{product.get('title')}' is not in a suspected risky category.")
    if "metafields" not in product:      # public audit: unknown, not a defect
        return _na("Metafields were not available for this audit source, so guardrails cannot be evaluated.",
                   "incomplete_data")
    populated = {k for k, m in (product.get("metafields") or {}).items() if _populated(m)}

    def has(tokens: set[str]) -> bool:
        return any(_tokens(k) & (tokens | GENERIC_GUARD_TOKENS) for k in populated)

    issues = []
    if "age" in kinds and not has(AGE_GUARD_TOKENS):
        issues.append(_issue("missing_age_limit",
                             "Suspected age-restricted product has no populated age-limit guardrail metafield."))
    if "warning" in kinds and not has(WARNING_GUARD_TOKENS):
        issues.append(_issue("missing_warning",
                             "Suspected health/safety/financial product has no populated warning metafield."))
    return _graded("Guardrail metafield signal(s) present and populated.", issues, len(kinds), len(issues))


# ── STORE ────────────────────────────────────────────────────────────────

def _section_ok(ctx: dict | None, name: str) -> tuple[bool, str]:
    if not store_context_usable(ctx):
        return False, "No store context (public audit, failed fetch, or no Admin API)."
    sec = (ctx.get("sections") or {}).get(name)
    if not sec or sec.get("status") != "ok":
        return False, f"Section '{name}' could not be fetched ({(sec or {}).get('status')}): {(sec or {}).get('error')}"
    return True, ""


def _gate(ctx: dict | None, name: str) -> dict | None:
    """Returns an NA result (with the right na_reason) when the section is unusable, else None."""
    ok, why = _section_ok(ctx, name)
    if ok:
        return None
    return _na(why, "no_store_context" if not store_context_usable(ctx) else "fetch_failed")


_POLICY_TYPES = {"privacy": ("PRIVACY_POLICY",), "refund": ("REFUND_POLICY",),
                 "shipping": ("SHIPPING_POLICY",), "terms": ("TERMS_OF_SERVICE", "TERMS_OF_SALE")}


def check_legal_pages(ctx: dict | None) -> dict:
    gate = _gate(ctx, "policies")
    if gate:
        return gate
    by_type = {p.get("type"): strip_html(p.get("body")) for p in ctx.get("policies") or []}
    ship_required = (ctx.get("catalog_flags") or {}).get("requires_shipping") is True
    issues, required_count = [], 0
    for name, ptypes in _POLICY_TYPES.items():
        required = name != "shipping" or ship_required     # unknown shipping need is never a defect
        text = max((by_type.get(t, "") for t in ptypes), key=lambda s: len(_words(s)), default="")
        required_count += 1 if required else 0
        if len(_words(text)) < MIN_POLICY_WORDS:
            if required:
                issues.append(_issue(f"missing_{name}_policy", f"The {name} policy is missing or effectively empty."))
        elif has_placeholder(text):
            issues.append(_issue(f"placeholder_{name}_policy", f"The {name} policy contains suspected unfilled placeholder text."))
    return _graded("All required policies are present with no placeholder text.", issues,
                   required_count, len(issues), fail_if_core=required_count > 0 and len(issues) >= required_count)


def check_fulfillment_context(ctx: dict | None) -> dict:
    gate = _gate(ctx, "delivery")
    if gate:
        return gate
    if (ctx.get("catalog_flags") or {}).get("requires_shipping") is not True:
        return _na("No shippable product confirmed (digital-only or unknown), so fulfillment is not evaluated.")
    methods, countries, rest_of_world = [], set(), False
    for prof in ctx.get("delivery_profiles") or []:
        for grp in prof.get("profileLocationGroups") or []:
            for zn in ((grp.get("locationGroupZones") or {}).get("nodes") or []):
                for c in ((zn.get("zone") or {}).get("countries") or []):
                    code = c.get("code") or {}
                    if code.get("restOfWorld"):
                        rest_of_world = True
                    elif code.get("countryCode"):
                        countries.add(code["countryCode"])
                methods += [m for m in ((zn.get("methodDefinitions") or {}).get("nodes") or []) if m.get("active")]
    pickup = [l for l in ctx.get("locations") or [] if l.get("isActive") and l.get("localPickupSettingsV2")]
    ships_to = (ctx.get("shop") or {}).get("shipsToCountries") or []
    pickup_only = bool(pickup) and not methods

    issues = []
    no_methods = not methods and not pickup
    no_region = not pickup_only and not countries and not rest_of_world and not ships_to
    if no_methods:
        issues.append(_issue("missing_shipping_methods", "No active shipping method or local pickup is configured."))
    if no_region:
        issues.append(_issue("missing_region_coverage", "No shipping zone or destination country is configured."))

    thin_pickup = []
    for l in pickup:
        s = l.get("localPickupSettingsV2")
        if isinstance(s, dict) and "instructions" in s and not (s.get("instructions") or "").strip():
            thin_pickup.append(l.get("name") or l.get("id") or "location")
    if thin_pickup:
        issues.append(_issue("missing_pickup_information",
                             f"Pickup is enabled but has no pickup instructions at: {thin_pickup}."))

    policies_ok, _ = _section_ok(ctx, "policies")
    if methods and policies_ok:
        ship_text = next((strip_html(p.get("body")) for p in ctx.get("policies") or []
                          if p.get("type") == "SHIPPING_POLICY"), "")
        if len(_words(ship_text)) >= MIN_POLICY_WORDS and not _DELIVERY_TIME_RE.search(ship_text):
            issues.append(_issue("missing_delivery_time",
                                 "The shipping policy states no delivery timeframe (e.g. '3-5 business days')."))

    return _graded(f"{len(methods)} active method(s), {len(pickup)} pickup location(s), "
                   f"{len(countries) or 'rest-of-world/other'} destination(s).",
                   issues, 0, len(issues), fail_if_core=no_methods and no_region)


def _walk_menu(items: list[dict]) -> set[str]:
    toks: set[str] = set()
    for it in items or []:
        toks |= _tokens(it.get("title")) | _tokens((it.get("url") or "").rsplit("/", 1)[-1])
        toks |= _walk_menu(it.get("items") or [])          # any depth
    return toks


def _menu_tokens(ctx: dict) -> set[str]:
    toks: set[str] = set()
    for m in ctx.get("menus") or []:
        toks |= _walk_menu(m.get("items") or [])
    return toks


def _page_tokens(ctx: dict) -> set[str]:
    toks: set[str] = set()
    for p in ctx.get("pages") or []:
        toks |= _tokens(p.get("handle")) | _tokens(p.get("title"))
    return toks


def _site_tokens(ctx: dict) -> set[str]:
    return _page_tokens(ctx) | _menu_tokens(ctx)


def check_contact_brand(ctx: dict | None) -> dict:
    gate = _gate(ctx, "content")
    if gate:
        return gate
    policies_ok, _ = _section_ok(ctx, "policies")
    profile_ok, _ = _section_ok(ctx, "profile")
    toks = _site_tokens(ctx)
    shop = ctx.get("shop") or {}
    brand = shop.get("brand") or {}
    contact_policy = policies_ok and any(
        p.get("type") == "CONTACT_INFORMATION" and _words(strip_html(p.get("body")))
        for p in ctx.get("policies") or [])
    has_contact = contact_policy or bool(toks & CONTACT_TOKENS)
    has_brand = bool(toks & ABOUT_TOKENS) or (profile_ok and bool(
        brand.get("shortDescription") or brand.get("slogan") or (shop.get("description") or "").strip()))

    issues, unknown = [], []
    if not has_contact:
        (issues if policies_ok else unknown).append(
            _issue("missing_contact_information",
                   "No public contact page, menu link or contact-information policy found."))
    if not has_brand:
        (issues if profile_ok else unknown).append(
            _issue("missing_brand_information", "No about page, brand description or shop description found."))
    if not issues and unknown:
        return _na("Contact/brand could not be fully evaluated because a store-context section failed to load.",
                   "fetch_failed")
    return _graded("Public contact and brand information found.", issues, 2 - len(unknown), len(issues))


def check_faq_or_guidance(ctx: dict | None) -> dict:
    gate = _gate(ctx, "content")
    if gate:
        return gate
    faq_pages = [p for p in ctx.get("pages") or []
                 if (_tokens(p.get("handle")) | _tokens(p.get("title"))) & FAQ_TOKENS]
    meta_hit = False
    for d in ((ctx.get("metaobjectDefinitions") or {}).get("edges") or []):
        n = d.get("node") or {}
        if (_tokens(n.get("type")) | _tokens(n.get("name"))) & FAQ_TOKENS and (n.get("metaobjectsCount") or 0) > 0:
            meta_hit = True
    menu_hit = bool(_menu_tokens(ctx) & FAQ_TOKENS)

    body_known = [p for p in faq_pages if "body" in p]
    if any(len(_words(strip_html(p.get("body")))) >= MIN_FAQ_WORDS for p in body_known):
        return _verdict("pass", "FAQ/help page with substantive content found.")
    if body_known:
        msg = f"FAQ/help page found but its body has fewer than {MIN_FAQ_WORDS} words."
        return _verdict("partial", msg, [_issue("insufficient_shopping_guidance", msg)])
    if faq_pages or meta_hit:
        return _verdict("pass", "FAQ/help page or FAQ metaobject entries found (content depth not verified: bodies not collected).")
    if menu_hit:
        msg = "Only a menu entry labelled like FAQ/help was found; no FAQ page or content could be verified."
        return _verdict("partial", msg, [_issue("insufficient_shopping_guidance", msg)])
    msg = "No FAQ/help page, menu entry or FAQ metaobject entries found."
    return _verdict("partial", msg, [_issue("missing_faq", msg)])


def check_store_guardrails(ctx: dict | None) -> dict:
    """Restriction DISCLOSURE signals (metafield or policy text). Cannot prove checkout enforcement."""
    gate = _gate(ctx, "core")
    if gate:
        return gate
    flags = ctx.get("catalog_flags") or {}
    if not flags.get("has_risky_products"):
        return _na("No suspected risky products seen in the audited products; absence in a sample is not proof "
                   "of absence, so store guardrails are not evaluated.")
    edges = ((ctx.get("shop") or {}).get("metafields") or {}).get("edges") or []
    keys = [f"{(e.get('node') or {}).get('namespace')}.{(e.get('node') or {}).get('key')}"
            for e in edges if (e.get("node") or {}).get("value")]
    policies_ok, _ = _section_ok(ctx, "policies")
    text_hit = policies_ok and any(_STORE_GUARD_TEXT_RE.search(strip_html(p.get("body")))
                                   for p in ctx.get("policies") or [])
    if any(_tokens(k) & _STORE_GUARD_TOKENS for k in keys) or text_hit:
        return _verdict("pass", "Store-level restriction disclosure signal found (metafield or policy text); "
                                "enforcement is not verified.")
    if not policies_ok:
        return _na("Policy text could not be fetched, so store guardrails cannot be fully evaluated.", "fetch_failed")
    msg = "Suspected risky products present but no store-level restriction metafield or policy text found."
    issue_type = "missing_age_gating" if "age" in (flags.get("risk_kinds") or []) else "missing_manual_approval_rule"
    return _verdict("partial", msg, [_issue(issue_type, msg)])




def _make_verdict(verdict, evidence, issue_type=None, *, variant_ids=None, option_ids=None):
    result = {"verdict": verdict, "evidence": evidence, "issues": []}
    if issue_type and verdict in ("partial", "fail"):
        result["issues"] = [_issue(issue_type, evidence, variant_ids, option_ids)]
    return result


def check_description_presence(product: dict) -> dict | None:
    """Empty-description case only."""
    text = product.get("description_text")
    if text is None:
        text = strip_html(product.get("description"))
    if not (text or "").strip():
        return _make_verdict("fail", "Product description is empty.", "insufficient_product_description")
    return None


# ── dispatch tables ──────────────────────────────────────────────────────

PRODUCT_DETERMINISTIC_CHECKS = {
    "stable_ids_urls": check_stable_ids_urls,
    "published_to_sales_channel": check_published_to_sales_channel,
    "variant_selection": check_variant_selection,
    "variant_hygiene": check_variant_hygiene,
    "pricing_clarity": check_pricing_clarity,
    "availability_signals": check_availability_signals,
    "identifiers": check_identifiers,
    "media_quality": check_media_quality,
    "product_guardrails": check_product_guardrails,
    "comparable_attributes": check_comparable_attributes,   
}

PRODUCT_CHECKS_MERGED_WITH_LLM = {"comparable_attributes"}

STORE_DETERMINISTIC_CHECKS = {
    "legal_pages": check_legal_pages,
    "fulfillment_context": check_fulfillment_context,
    "contact_brand": check_contact_brand,
    "faq_or_guidance": check_faq_or_guidance,
    "store_guardrails": check_store_guardrails,
}

_TRUNCATION_RULES = {
    "variants_truncated": ({"variant_selection", "pricing_clarity", "availability_signals",
                            "identifiers", "variant_hygiene"}, {"pass": "na", "fail": "partial"}),
    "media_truncated": ({"media_quality"}, {"pass": "na"}),
    "metafields_truncated": ({"product_guardrails"}, {"fail": "na", "partial": "na"}),
}


def _guard_truncation(check_id: str, result: dict, product: dict) -> dict:
    warnings = set(product.get("data_warnings") or [])
    for warning, (check_ids, remap) in _TRUNCATION_RULES.items():
        if warning in warnings and check_id in check_ids:
            action = remap.get(result.get("verdict"))
            if action == "na":
                return _na(f"Incomplete data ({warning}): only part of this product's data was collected, "
                           f"so this conclusion cannot be confirmed.", "incomplete_data")
            if action:
                return {**result, "verdict": action,
                        "evidence": f"{result.get('evidence', '')} (Based on partial data: {warning}.)"}
    return result


def run_product_deterministic_checks(product: dict) -> dict[str, dict]:
    return {cid: _guard_truncation(cid, fn(product), product)
            for cid, fn in PRODUCT_DETERMINISTIC_CHECKS.items()}


def run_store_deterministic_checks(ctx: dict | None) -> dict[str, dict]:
    usable = store_context_usable(ctx)
    results = {cid: fn(ctx if usable else None) for cid, fn in STORE_DETERMINISTIC_CHECKS.items()}
    if not usable:
        # Public audit / failed context fetch: every context-dependent check (including the
        # LLM-judged policy_semantics) is NA so missing evidence is never scored as a defect.
        for cid in STORE_CONTEXT_REQUIRED_CHECKS:
            results[cid] = _na(f"'{cid}' cannot be evaluated: store context was not available for this audit.",
                               "no_store_context")
    return results


# ── merging with LLM verdicts ─────────────────────────────────

_VERDICT_ORDER = {"na": 0, "pass": 1, "partial": 2, "fail": 3}


def merge_with_llm(
    det: dict,
    llm_verdict: str,
    llm_issues: list[dict],
) -> tuple[str, list[dict]]:
    if det.get("verdict") == "na":
        return llm_verdict, llm_issues or []

    verdict = max(
        (det.get("verdict", "na"), llm_verdict),
        key=lambda v: _VERDICT_ORDER.get(v, 0),
    )

    merged = []
    seen = set()

    for issue in (det.get("issues") or []) + (llm_issues or []):
        issue_type = issue.get("issue_type")
        if not issue_type:
            merged.append(issue)
            continue

        if issue_type in seen:
            continue

        seen.add(issue_type)
        merged.append(issue)

    if verdict in ("pass", "na"):
        merged = []

    return verdict, merged


def coverage_summary(results: list[dict]) -> dict[str, Any]:
    """results: deterministic check result dicts (store + product). Quantifies how much was UNKNOWN,
    so a store with little collected data cannot look healthy just because unknowns are excluded."""
    total = len(results)
    reasons = Counter(r.get("na_reason") for r in results if r.get("verdict") == "na")
    unknown = sum(n for reason, n in reasons.items() if reason in NA_UNKNOWN_REASONS)
    return {
        "total_checks": total,
        "unknown_checks": unknown,
        "coverage_ratio": round(1 - unknown / total, 3) if total else 0.0,
        "na_reasons": dict(reasons),
    }


def compute_catalog_flags(products: list[dict], catalog_complete: bool = False) -> dict[str, Any]:
    """catalog_complete=True only when `products` is the WHOLE catalog (e.g. audited == total).
    A sample can prove presence, never absence."""
    shippable = [v.get("requires_shipping") for p in products for v in (p.get("variants") or [])
                 if v.get("requires_shipping") is not None]
    if any(shippable):
        requires_shipping = True
    elif shippable and catalog_complete:
        requires_shipping = False
    else:
        requires_shipping = None            # unknown
    kinds: set[str] = set()
    for p in products:
        kinds |= _risk_kinds(p)
    return {"requires_shipping": requires_shipping, "has_risky_products": bool(kinds),
            "risk_kinds": sorted(kinds), "catalog_complete": catalog_complete}


# ── CATALOG CONSISTENCY (works for Admin AND public products) ────────────

_UNITS = {
    "mm": "length", "cm": "length", "m": "length", "in": "length", "inch": "length", "inches": "length", "ft": "length",
    "g": "weight", "kg": "weight", "oz": "weight", "lb": "weight", "lbs": "weight",
    "ml": "volume", "l": "volume", "fl oz": "volume",
}
_UNIT_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*(mm|cm|m|inches|inch|in|ft|kg|g|lbs|lb|oz|ml|fl oz|l)\b", re.I)
_SHOPIFY_UNIT_NAMES = {"MILLIMETERS": "mm", "CENTIMETERS": "cm", "METERS": "m", "INCHES": "in", "FEET": "ft",
                       "GRAMS": "g", "KILOGRAMS": "kg", "OUNCES": "oz", "POUNDS": "lb",
                       "MILLILITERS": "ml", "LITERS": "l", "FLUID_OUNCES": "fl oz"}


def _unit_of(meta: dict) -> str | None:
    mtype, value = (meta.get("type") or ""), meta.get("value")
    if mtype in ("dimension", "weight", "volume") or mtype.startswith(("list.dimension", "list.weight", "list.volume")):
        try:
            data = json.loads(value)
            data = data[0] if isinstance(data, list) and data else data
            return _SHOPIFY_UNIT_NAMES.get(str(data.get("unit")).upper())
        except (ValueError, AttributeError, TypeError):
            return None
    if "text" in mtype or mtype == "":
        m = _UNIT_RE.search(str(value or ""))
        return m.group(2).lower() if m else None
    return None


def _format_and_unit_issues(group: list[dict], pid_fn, targets_fn) -> tuple[list[dict], set[str]]:
    types_by_key: dict[str, dict[str, list[str]]] = {}
    units_by_key: dict[str, dict[str, list[str]]] = {}
    for p in group:
        pid = pid_fn(p)
        for key, meta in (p.get("metafields") or {}).items():
            if not isinstance(meta, dict) or meta.get("value") in (None, ""):
                continue
            types_by_key.setdefault(key, {}).setdefault(meta.get("type") or "unknown", []).append(pid)
            unit = _unit_of(meta)
            if unit:
                units_by_key.setdefault(key, {}).setdefault(unit, []).append(pid)

    issues, affected = [], set()
    for key, by_type in types_by_key.items():
        if len(by_type) > 1:
            ids = {pid for v in by_type.values() for pid in v}
            affected |= ids
            issues.append({"issue_type": "inconsistent_attribute_format", "status": "existing", "field": key,
                           "description": f"Metafield '{key}' uses different types across comparable products: {sorted(by_type)}.",
                           "affected_product_ids": sorted(ids), "targets": targets_fn(ids)})
    for key, by_unit in units_by_key.items():
        dims = {_UNITS.get(u) for u in by_unit}
        if len(by_unit) > 1 and len(dims) == 1:       # same dimension, different unit (cm vs in)
            ids = {pid for v in by_unit.values() for pid in v}
            affected |= ids
            issues.append({"issue_type": "inconsistent_attribute_units", "status": "existing", "field": key,
                           "description": f"Metafield '{key}' mixes units across comparable products: {sorted(by_unit)}.",
                           "affected_product_ids": sorted(ids), "targets": targets_fn(ids)})
    return issues, affected


def _group_key(product: dict) -> str | None:
    """Taxonomy category first (Admin), then product_type. Never by option names."""
    cat = ((product.get("category") or {}).get("fullName") or "").strip().lower()
    if cat:
        return f"category:{cat}"
    ptype = (product.get("product_type") or "").strip().lower()
    return f"type:{ptype}" if ptype else None


def _comparable_metafields(product: dict) -> dict[str, dict]:
    out = {}
    for k, m in (product.get("metafields") or {}).items():
        if isinstance(m, dict) and not (m.get("namespace") or "").startswith(("app--", "shopify--")):
            out[k] = m
    return out


def _cons_na(evidence: str, reason: str = "nothing_to_compare") -> dict[str, Any]:
    return {"verdict": "na", "evidence": evidence, "issues": [], "affected_product_ids": [], "na_reason": reason}


def check_catalog_consistency(products: list[dict], measurement_observations: list[dict] | None = None) -> dict:
    def pid(p: dict) -> str:
        return str(p.get("id") or p.get("product_id") or "").strip()

    valid = [p for p in products if pid(p)]
    by_id = {pid(p): p for p in valid}
    if len(valid) < 2:
        return _cons_na("Fewer than two identifiable products: nothing to compare.")

    groups: dict[str, list[dict]] = {}
    for p in valid:
        key = _group_key(p)
        if key:
            groups.setdefault(key, []).append(p)
    comparable = [g for g in groups.values() if len(g) >= 2]
    if not comparable:
        return _cons_na("No two products share a taxonomy category or product type, so none are comparable.")

    def targets_for(ids, include_options: bool = False) -> list[dict]:
        out = []
        for i in sorted(ids):
            p = by_id.get(i) or {}
            out.append({
                "product_id": i,
                "option_ids": _uniq(_oid(o) for o in (p.get("options") or [])) if include_options else [],
                "variant_ids": [],
            })
        return out

    issues: list[dict] = []
    affected: set[str] = set()

    for group in comparable:
        # 1. option structure (single-default-variant products have no real options: excluded)
        with_options = [p for p in group if not is_default_variant_product(p)]
        if len(with_options) >= 2:
            option_sets = {
                pid(p): {(o.get("name") or "").strip().lower()
                         for o in (p.get("options") or []) if (o.get("name") or "").strip()}
                for p in with_options
            }
            for name in sorted(set().union(*option_sets.values())):
                present = {i for i, s in option_sets.items() if name in s}
                missing = {i for i, s in option_sets.items() if name not in s}
                if present and missing and len(present) > len(with_options) * CONSISTENCY_MAJORITY:
                    affected |= missing
                    issues.append({
                        "issue_type": "inconsistent_option_structure", "status": "existing",
                        "description": f"Option '{name}' is present on {len(present)}/{len(with_options)} comparable products.",
                        "field": "options.name", "affected_product_ids": sorted(missing),
                        "targets": targets_for(missing, include_options=True),
                    })

        # 2. metafield key structure 
        key_sets = {pid(p): set(_comparable_metafields(p)) for p in group if "metafields" in p}
        if len(key_sets) >= 2:
            for key in sorted(set().union(*key_sets.values())):
                present = {i for i, s in key_sets.items() if key in s}
                missing = {i for i, s in key_sets.items() if key not in s}
                if present and missing and len(present) > len(key_sets) * CONSISTENCY_MAJORITY:
                    affected |= missing
                    issues.append({
                        "issue_type": "inconsistent_metafield_structure", "status": "existing",
                        "description": f"Metafield '{key}' is used by {len(present)}/{len(key_sets)} comparable products but missing from {len(missing)}.",
                        "field": key, "affected_product_ids": sorted(missing), "targets": targets_for(missing),
                    })

        # 3 + 4. metafield declared types and units
        slim = [{**p, "metafields": _comparable_metafields(p)} for p in group]
        fmt_issues, fmt_affected = _format_and_unit_issues(slim, pid, targets_for)
        issues += fmt_issues
        affected |= fmt_affected

    # 5. LLM measurement observations (optional)
    group_idx = {pid(p): gi for gi, g in enumerate(comparable) for p in g}
    by_group_field: dict[tuple[int, str], list[tuple[str, str]]] = {}
    for ob in (measurement_observations or []):
        if not isinstance(ob, dict):
            continue
        opid = str(ob.get("product_id") or "").strip()
        field = str(ob.get("field") or "").strip().lower()
        dim = str(ob.get("dimension") or "").strip().lower()
        gi = group_idx.get(opid)
        if opid and field and dim and gi is not None:
            by_group_field.setdefault((gi, field), []).append((opid, dim))
    for (gi, field), obs in by_group_field.items():
        dims = {d for _, d in obs}
        if len(dims) > 1:
            ids = {p for p, _ in obs}
            affected |= ids
            issues.append({
                "issue_type": "inconsistent_attribute_units", "status": "existing", "field": field,
                "description": f"Comparable products use measurements with different physical dimensions for '{field}': {sorted(dims)}.",
                "affected_product_ids": sorted(ids), "targets": targets_for(ids),
            })

    total = len({pid(p) for g in comparable for p in g})
    hit = len(affected)
    if hit == 0:
        verdict = "pass"
    else:
        verdict = "fail" if hit / total >= CONSISTENCY_FAIL_RATIO else "partial"
    return {
        "verdict": verdict,
        "evidence": f"{hit}/{total} comparable product(s) affected by catalog consistency checks "
                    f"across {len(comparable)} comparable group(s).",
        "issues": issues,
        "affected_product_ids": sorted(affected),
    }

