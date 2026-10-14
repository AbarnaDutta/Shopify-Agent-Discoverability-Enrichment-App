# app/services/deterministic_checks.py
from __future__ import annotations

import html
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Any


def _uniq(ids) -> list[str]:
    return list(dict.fromkeys(str(i) for i in ids if i))


# ── config ───────────────────────────────────────────────────────────────
MIN_POLICY_WORDS = 10
GENERIC_OPTION_NAMES = {"title", "option", "option1", "option2", "option3",
                        "custom", "custom1", "custom2", "custom3", "variant", "default"}
GENERIC_OPTION_VALUES = {"default title", "default", "option1", "option2", "option3",
                         "custom", "undefined", "null"}
CONTACT_TOKENS = {"contact", "kontakt", "contacto", "contato", "contatto"}
ABOUT_TOKENS = {"about", "uber", "ueber", "propos", "acerca", "sobre", "chi", "story"}
FAQ_TOKENS = {"faq", "faqs", "help", "questions", "fragen", "preguntas", "perguntas", "domande", "aide"}
AGE_TAXONOMY_MARKERS = ("alcoholic beverages", "tobacco", "weapons", "mature")
WARNING_TAXONOMY_MARKERS = ("vitamins & supplements", "health care", "baby & toddler")
_AGE_RE = re.compile(
    r"\b(?:alcohol(?!-free)|tobacco|cigars?|cigarettes?|vapes?|vaping|e-liquids?|cannabis|cbd|"
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
# Store checks that need Admin store context. Without usable context they are NA, never a defect.
STORE_CONTEXT_REQUIRED_CHECKS = {
    "fulfillment_context", "policy_semantics", "faq_or_guidance",
    "store_guardrails", "legal_pages", "contact_brand",
}


# ── helpers ──────────────────────────────────────────────────────────────

def strip_html(text: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", text or "")).strip()


def _words(text: str | None) -> list[str]:
    return re.findall(r"\w+", text or "", flags=re.UNICODE)


def _tokens(text: str | None) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


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


def _na(evidence: str) -> dict:
    return _verdict("na", evidence)


def _graded(evidence_ok: str, issues: list[dict], checked: int, failed: int, *,
            fail_if_core: bool = False) -> dict:
    """pass when no issues; fail when a core requirement is unmet or everything failed; else partial."""
    if not issues:
        return _verdict("pass", evidence_ok)
    verdict = "fail" if (fail_if_core or (checked and failed >= checked)) else "partial"
    return _verdict(verdict, " ".join(i["description"] for i in issues), issues)


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


def _selected_names(variant: dict) -> set[str]:
    return {(s.get("name") or "").strip().lower()
            for s in (variant.get("selectedOptions") or []) if (s.get("name") or "").strip()}


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
    if url and (re.search(r"\s", url) or url.lower().startswith("http://")):
        issues.append(_issue("invalid_product_url", f"Product URL '{url}' is not a valid https URL."))
    return _graded(f"Product has id and valid handle '{handle}'.", issues, 3, len(issues),
                   fail_if_core=any(i["issue_type"] == "missing_product_id" for i in issues))


def check_published_to_sales_channel(product: dict) -> dict:
    if "published_channels" not in product:
        return _na("Sales-channel publication is only known for Admin-API audits.")
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
        return _na("No variants were collected for this product (incomplete data); selection cannot be evaluated.")
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
    if incomplete:
        issues.append(_issue("incomplete_selected_options",
                             f"{len(incomplete)}/{len(variants)} variants lack a complete set of selected options.",
                             variant_ids=[_vid(v) for v in incomplete]))

    dup_in_variant = [v for v in variants
                      if v not in incomplete and len(_selected_name_list(v)) != len(set(_selected_name_list(v)))]
    combos: dict[tuple, list[dict]] = {}
    for v in variants:
        if v in incomplete:
            continue
        key = tuple(sorted(((s.get("name") or "").strip().lower(), (s.get("value") or "").strip().lower())
                           for s in (v.get("selectedOptions") or [])))
        combos.setdefault(key, []).append(v)
    dupes = [v for g in combos.values() if len(g) > 1 for v in g]
    bad = {id(v): v for v in dupes + dup_in_variant}.values()
    if bad:
        issues.append(_issue("inconsistent_variant_options",
                             f"{len(list(bad))} variants repeat an option or share an identical option combination, so an agent cannot pick one SKU.",
                             variant_ids=[_vid(v) for v in bad]))

    failed = len(missing) + len(dup_names) + len(incomplete) + len(list(bad))
    return _graded("Options are named and every variant has a unique, complete option combination.",
                   issues, len(options) + len(variants), failed)


def check_variant_hygiene(product: dict) -> dict:
    options = product.get("options") or []
    variants = product.get("variants") or []
    if is_default_variant_product(product):
        return _na("Single default variant: no variant structure to evaluate.")
    if not variants or not options:
        return _na("No variants/options were collected (incomplete data); hygiene cannot be evaluated.")

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

    # same option, same value written differently ("Red" vs "red")
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
    variants = product.get("variants") or []
    if not variants:
        return _na("No variants to evaluate.")
    missing, zero, bad = [], [], []
    for v in variants:
        raw = v.get("price")
        if raw in (None, ""):
            missing.append(v)
        else:
            d = _to_decimal(raw)
            if d is None:
                bad.append(v)
            elif d <= 0:
                zero.append(v)
    issues = []
    if missing:
        issues.append(_issue("missing_price", f"{len(missing)} variant(s) have no price.",
                             variant_ids=[_vid(v) for v in missing]))
    if bad:
        issues.append(_issue("placeholder_price", f"{len(bad)} variant(s) have a non-numeric price.",
                             variant_ids=[_vid(v) for v in bad]))
    if zero:
        issues.append(_issue("zero_price", f"{len(zero)} variant(s) are priced at 0.",
                             variant_ids=[_vid(v) for v in zero]))
    return _graded(f"All {len(variants)} variant(s) have a numeric, non-zero price.",
                   issues, len(variants), len(missing) + len(bad) + len(zero))


def check_availability_signals(product: dict) -> dict:
    """Being SOLD OUT is not a defect. Not being able to tell is.
    (Public products.json has no inventory quantity, so only the boolean is required.)"""
    variants = product.get("variants") or []
    if not variants:
        return _na("No variants to evaluate.")
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

def is_valid_gtin(code: str | None) -> bool:
    digits = re.sub(r"[\s-]", "", code or "")
    if not digits.isdigit() or len(digits) not in (8, 12, 13, 14):
        return False
    nums = [int(c) for c in digits]
    check = nums.pop()
    total = sum(n * (3 if i % 2 == 0 else 1) for i, n in enumerate(reversed(nums)))
    return (10 - total % 10) % 10 == check


def check_identifiers(product: dict) -> dict:
    variants = product.get("variants") or []
    if not variants:
        return _na("No variants to evaluate.")
    issues = []

    no_sku = [v for v in variants if not (v.get("sku") or "").strip()]
    if no_sku:
        issues.append(_issue("missing_sku", f"{len(no_sku)}/{len(variants)} variant(s) have no SKU.",
                             variant_ids=[_vid(v) for v in no_sku]))
    skus = [v["sku"].strip().lower() for v in variants if (v.get("sku") or "").strip()]
    dup_skus = {s for s in skus if skus.count(s) > 1}
    if dup_skus:
        dv = [v for v in variants if (v.get("sku") or "").strip().lower() in dup_skus]
        issues.append(_issue("duplicate_sku", f"{len(dv)} variants share a SKU.",
                             variant_ids=[_vid(v) for v in dv]))

    with_code = [v for v in variants if (v.get("barcode") or "").strip()]
    bad = [v for v in with_code if not is_valid_gtin(v["barcode"])]
    if bad:
        issues.append(_issue("invalid_gtin", f"{len(bad)} barcode(s) fail GTIN length/check-digit validation.",
                             variant_ids=[_vid(v) for v in bad]))
    without = [v for v in variants if not (v.get("barcode") or "").strip()]
    # Only a defect when the merchant clearly uses barcodes elsewhere (mixed present/absent).
    if without and with_code:
        issues.append(_issue("missing_gtin",
                             f"{len(without)}/{len(variants)} variant(s) have no barcode while others do.",
                             variant_ids=[_vid(v) for v in without]))

    failed = len(no_sku) + len(bad) + (len(without) if with_code else 0)
    return _graded("All variants have unique SKUs and valid barcodes.", issues, len(variants), failed,
                   fail_if_core=len(no_sku) == len(variants))


# ── PRODUCT: taxonomy, media, guardrails ─────────────────────────────────

def check_comparable_attributes(product: dict) -> dict:
    issues = []
    has_category_field = "category" in product        # absent on public audits
    cat = product.get("category")
    if has_category_field and not (isinstance(cat, dict) and cat.get("id")):
        issues.append(_issue("missing_taxonomy_category", "No Shopify standard taxonomy category is assigned."))
    if not (product.get("product_type") or "").strip():
        issues.append(_issue("missing_product_type", "product_type is empty."))
    return _graded("Taxonomy category and product type are set.", issues,
                   2 if has_category_field else 1, len(issues))


def check_media_quality(product: dict) -> dict:
    if "images" not in product:
        return _na("Image data not available for this audit source.")
    images = product.get("images") or []
    if not images:
        if "media_truncated" in (product.get("data_warnings") or []):
            return _na("No image seen in the collected media, but media was truncated; cannot confirm there is none.")
        return _verdict("fail", "Product has no images.",
                        [_issue("missing_product_image", "Product has no images.")])
    no_alt = [i for i in images if not (i.get("alt") or "").strip()]
    if no_alt:
        msg = f"{len(no_alt)}/{len(images)} images have no alt text."
        return _verdict("partial", msg, [_issue("missing_image_alt", msg)])
    return _verdict("pass", f"{len(images)} image(s), all with alt text.")


def _risk_kinds(product: dict) -> set[str]:
    """Combine ALL evidence (taxonomy + title/type/tags). A non-risky category never hides a risky keyword."""
    kinds: set[str] = set()
    cat = ((product.get("category") or {}).get("fullName") or "").lower()
    if any(m in cat for m in AGE_TAXONOMY_MARKERS):
        kinds.add("age")
    if any(m in cat for m in WARNING_TAXONOMY_MARKERS):
        kinds.add("warning")
    hay = " ".join([str(product.get("product_type") or ""), str(product.get("title") or ""),
                    " ".join(product.get("tags") or [])])
    if _AGE_RE.search(hay):
        kinds.add("age")
    if _WARNING_RE.search(hay):
        kinds.add("warning")
    return kinds


def _product_is_risky(product: dict) -> bool:
    return bool(_risk_kinds(product))


def _populated(meta) -> bool:
    return isinstance(meta, dict) and str(meta.get("value") or "").strip() not in ("", "[]", "{}", "null")


def check_product_guardrails(product: dict) -> dict:
    kinds = _risk_kinds(product)
    if not kinds:
        return _na(f"Product '{product.get('title')}' is not in a risky category.")
    if "metafields" not in product:      # public audit: unknown, not a defect
        return _na("Metafields were not available for this audit source, so guardrails cannot be evaluated.")
    populated = {k for k, m in (product.get("metafields") or {}).items() if _populated(m)}

    def has(tokens: set[str]) -> bool:
        return any(_tokens(k) & (tokens | GENERIC_GUARD_TOKENS) for k in populated)

    issues = []
    if "age" in kinds and not has(AGE_GUARD_TOKENS):
        issues.append(_issue("missing_age_limit", "Age-restricted product has no populated age-limit guardrail metafield."))
    if "warning" in kinds and not has(WARNING_GUARD_TOKENS):
        issues.append(_issue("missing_warning", "Product in a health/safety/financial category has no populated warning metafield."))
    return _graded("Required guardrail metafield(s) are present and populated.", issues, len(kinds), len(issues))


# ── STORE ────────────────────────────────────────────────────────────────

def _section_ok(ctx: dict | None, name: str) -> tuple[bool, str]:
    if not ctx or "sections" not in ctx:
        return False, "No store context (public audit, failed fetch, or no Admin API)."
    sec = (ctx.get("sections") or {}).get(name)
    if not sec or sec.get("status") != "ok":
        return False, f"Section '{name}' could not be fetched ({(sec or {}).get('status')}): {(sec or {}).get('error')}"
    return True, ""


_POLICY_TYPES = {"privacy": "PRIVACY_POLICY", "refund": "REFUND_POLICY",
                 "shipping": "SHIPPING_POLICY", "terms": "TERMS_OF_SERVICE"}


def check_legal_pages(ctx: dict | None) -> dict:
    ok, why = _section_ok(ctx, "policies")
    if not ok:
        return _na(why)
    by_type = {p.get("type"): strip_html(p.get("body")) for p in ctx.get("policies") or []}
    ship_required = (ctx.get("catalog_flags") or {}).get("requires_shipping") is True
    issues, required_count = [], 0
    for name, ptype in _POLICY_TYPES.items():
        required = name != "shipping" or ship_required     # unknown shipping need is never a defect
        text = by_type.get(ptype, "")
        required_count += 1 if required else 0
        if len(_words(text)) < MIN_POLICY_WORDS:
            if required:
                issues.append(_issue(f"missing_{name}_policy", f"The {name} policy is missing or effectively empty."))
        elif has_placeholder(text):
            issues.append(_issue(f"placeholder_{name}_policy", f"The {name} policy contains unfilled placeholder text."))
    return _graded("All required policies are present with no placeholder text.", issues,
                   required_count, len(issues), fail_if_core=required_count > 0 and len(issues) >= required_count)


def check_fulfillment_context(ctx: dict | None) -> dict:
    ok, why = _section_ok(ctx, "delivery")
    if not ok:
        return _na(why)
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

    issues = []
    if not methods and not pickup:
        issues.append(_issue("missing_shipping_methods", "No active shipping method or local pickup is configured."))
    if not countries and not rest_of_world and not ships_to:
        issues.append(_issue("missing_region_coverage", "No shipping zone or destination country is configured."))
    return _graded(f"{len(methods)} active method(s), {len(pickup)} pickup location(s), "
                   f"{len(countries) or 'rest-of-world'} destination(s).", issues, 2, len(issues),
                   fail_if_core=len(issues) == 2)


def _site_tokens(ctx: dict) -> set[str]:
    toks: set[str] = set()
    for p in ctx.get("pages") or []:
        toks |= _tokens(p.get("handle")) | _tokens(p.get("title"))
    for m in ctx.get("menus") or []:
        for it in (m.get("items") or []):
            toks |= _tokens(it.get("title")) | _tokens((it.get("url") or "").rsplit("/", 1)[-1])
            for sub in it.get("items") or []:
                toks |= _tokens(sub.get("title")) | _tokens((sub.get("url") or "").rsplit("/", 1)[-1])
    return toks


def check_contact_brand(ctx: dict | None) -> dict:
    ok, why = _section_ok(ctx, "content")
    if not ok:
        return _na(why)
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
        return _na("Contact/brand could not be fully evaluated because a store-context section failed to load.")
    return _graded("Public contact and brand information found.", issues, 2 - len(unknown), len(issues))


def check_faq_or_guidance(ctx: dict | None) -> dict:
    ok, why = _section_ok(ctx, "content")
    if not ok:
        return _na(why)
    toks = _site_tokens(ctx)
    for d in ((ctx.get("metaobjectDefinitions") or {}).get("edges") or []):
        n = d.get("node") or {}
        if (_tokens(n.get("type")) | _tokens(n.get("name"))) & FAQ_TOKENS and (n.get("metaobjectsCount") or 0) > 0:
            toks |= FAQ_TOKENS
    if toks & FAQ_TOKENS:
        return _verdict("pass", "FAQ/help content found in pages, menus or metaobjects.")
    msg = "No FAQ/help page, menu entry or FAQ metaobject entries found."
    return _verdict("fail", msg, [_issue("missing_faq", msg)])


def check_store_guardrails(ctx: dict | None) -> dict:
    ok, why = _section_ok(ctx, "core")
    if not ok:
        return _na(why)
    flags = ctx.get("catalog_flags") or {}
    if not flags.get("has_risky_products"):
        return _na("No risky products seen in the audited products; absence in a sample is not proof of absence, "
                   "so store guardrails are not evaluated.")
    edges = ((ctx.get("shop") or {}).get("metafields") or {}).get("edges") or []
    keys = [f"{(e.get('node') or {}).get('namespace')}.{(e.get('node') or {}).get('key')}"
            for e in edges if (e.get("node") or {}).get("value")]
    policies_ok, _ = _section_ok(ctx, "policies")
    text_hit = policies_ok and any(_STORE_GUARD_TEXT_RE.search(strip_html(p.get("body")))
                                   for p in ctx.get("policies") or [])
    if any(_tokens(k) & _STORE_GUARD_TOKENS for k in keys) or text_hit:
        return _verdict("pass", "Store-level guardrail metafield or policy text present.")
    if not policies_ok:
        return _na("Policy text could not be fetched, so store guardrails cannot be fully evaluated.")
    msg = "Risky products present but no store-level guardrail metafield or policy text found."
    issue_type = "missing_age_gating" if "age" in (flags.get("risk_kinds") or []) else "missing_manual_approval_rule"
    return _verdict("partial", msg, [_issue(issue_type, msg)])


# ── legacy helpers (kept: report_builder imports these) ──────────────────
_variant_id = _vid
_option_id = _oid
_GENERIC_OPTION_NAMES = GENERIC_OPTION_NAMES


def _make_verdict(verdict, evidence, issue_type=None, *, variant_ids=None, option_ids=None):
    result = {"verdict": verdict, "evidence": evidence, "issues": []}
    if issue_type and verdict in ("partial", "fail"):
        result["issues"] = [_issue(issue_type, evidence, variant_ids, option_ids)]
    return result


def check_description_presence(product: dict) -> dict | None:
    """Empty-description case only (report_builder overrides product_understanding/clarity with it)."""
    text = product.get("description_text")
    if text is None:
        text = strip_html(product.get("description"))
    if not (text or "").strip():
        return _make_verdict("fail", "Product description is empty.", "insufficient_product_description")
    return None


def check_product_type_presence(product: dict) -> dict | None:
    if not (product.get("product_type") or "").strip():
        return _make_verdict("partial", "product_type field is empty.", "missing_product_type")
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
}

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
    "metafields_truncated": ({"product_guardrails"}, {"fail": "na"}),
}


def _guard_truncation(check_id: str, result: dict, product: dict) -> dict:
    warnings = set(product.get("data_warnings") or [])
    for warning, (check_ids, remap) in _TRUNCATION_RULES.items():
        if warning in warnings and check_id in check_ids:
            action = remap.get(result.get("verdict"))
            if action == "na":
                return _na(f"Incomplete data ({warning}): only part of this product's data was collected, "
                           f"so this conclusion cannot be confirmed.")
            if action:
                return {**result, "verdict": action,
                        "evidence": f"{result.get('evidence', '')} (Based on partial data: {warning}.)"}
    return result


def run_product_deterministic_checks(product: dict) -> dict[str, dict]:
    return {cid: _guard_truncation(cid, fn(product), product)
            for cid, fn in PRODUCT_DETERMINISTIC_CHECKS.items()}


def run_store_deterministic_checks(ctx: dict | None) -> dict[str, dict]:
    usable = bool(ctx) and "sections" in ctx
    results = {cid: fn(ctx if usable else None) for cid, fn in STORE_DETERMINISTIC_CHECKS.items()}
    if not usable:
        # Public audit / failed context fetch: every context-dependent check (including the
        # LLM-judged policy_semantics) is NA so missing evidence is never scored as a defect.
        for cid in STORE_CONTEXT_REQUIRED_CHECKS:
            results[cid] = _na(f"'{cid}' cannot be evaluated: store context was not available for this audit.")
    return results


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
    if mtype in ("dimension", "weight", "volume") or mtype.startswith("list.dimension"):
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


def _cons_na(evidence: str) -> dict[str, Any]:
    return {"verdict": "na", "evidence": evidence, "issues": [], "affected_product_ids": []}


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
                if present and missing and len(present) > len(with_options) / 2:
                    affected |= missing
                    issues.append({
                        "issue_type": "inconsistent_option_structure", "status": "existing",
                        "description": f"Option '{name}' is present on {len(present)}/{len(with_options)} comparable products.",
                        "field": "options.name", "affected_product_ids": sorted(missing),
                        "targets": targets_for(missing, include_options=True),
                    })

        # 2. metafield key structure (Admin audits only: public products have no metafields)
        key_sets = {pid(p): set(_comparable_metafields(p)) for p in group}
        for key in sorted(set().union(*key_sets.values())):
            present = {i for i, s in key_sets.items() if key in s}
            missing = {i for i, s in key_sets.items() if key not in s}
            if present and missing and len(present) > len(group) / 2:
                affected |= missing
                issues.append({
                    "issue_type": "inconsistent_metafield_structure", "status": "existing",
                    "description": f"Metafield '{key}' is used by {len(present)}/{len(group)} comparable products but missing from {len(missing)}.",
                    "field": key, "affected_product_ids": sorted(missing), "targets": targets_for(missing),
                })

        # 3 + 4. metafield declared types and units
        slim = [{**p, "metafields": _comparable_metafields(p)} for p in group]
        fmt_issues, fmt_affected = _format_and_unit_issues(slim, pid, targets_for)
        issues += fmt_issues
        affected |= fmt_affected

    # 5. LLM measurement observations (optional, kept from the old flow)
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

    total, hit = len(valid), len(affected)
    if hit == 0:
        verdict = "pass"
    else:
        verdict = "fail" if hit / total >= 0.9 else "partial"
    return {
        "verdict": verdict,
        "evidence": f"{hit}/{total} product(s) affected by catalog consistency checks "
                    f"across {len(comparable)} comparable group(s).",
        "issues": issues,
        "affected_product_ids": sorted(affected),
    }