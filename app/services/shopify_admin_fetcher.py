# app/services/shopify_admin_fetcher.py
from __future__ import annotations

import html as _html
import json
import random
import re
import time
import urllib.error
import urllib.request
from typing import Any, Callable


PRODUCTS_PAGE_SIZE = 5
VARIANTS_FIRST = 25
METAFIELDS_FIRST = 25
MEDIA_FIRST = 6
PUBLICATIONS_FIRST = 5
MAX_EXTRA_PAGES = 20          
MAX_RETRIES = 5
THROTTLE_FLOOR = 300          
_SHOP_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.myshopify\.com$", re.I)
_API_VERSION_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_ALLOWED_PRODUCT_STATUSES = {"active", "draft", "archived"}


class ShopifyAdminAPIError(Exception):
    """Raised when Shopify Admin GraphQL returns an error."""


class ShopifyScopeError(ShopifyAdminAPIError):
    """Missing access scope / ACCESS_DENIED. Means 'unknown', not 'defect'."""


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward an Admin API token through an unexpected redirect."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ShopifyAdminAPIError("Shopify Admin API returned an unexpected redirect; request was not followed.")


def _validate_shop_api_inputs(shop_domain: str, access_token: str, api_version: str) -> tuple[str, str, str]:
    domain = (shop_domain or "").strip().lower().rstrip(".")
    version = (api_version or "").strip()
    if not _SHOP_DOMAIN_RE.fullmatch(domain):
        raise ValueError("shop_domain must be the shop's *.myshopify.com domain.")
    if not access_token or not str(access_token).strip():
        raise ValueError("access_token is required.")
    if not _API_VERSION_RE.fullmatch(version):
        raise ValueError("api_version must use Shopify's YYYY-MM format.")
    return domain, str(access_token), version


# ── throttle handling ─────────────────────────────

def _retry_after(error: urllib.error.HTTPError) -> float | None:
    try:
        return float(error.headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None


def _backoff(attempt: int) -> float:
    return min(30.0, (2 ** attempt) + random.random())


def _respect_throttle(result: dict[str, Any]) -> None:
    cost = (result.get("extensions") or {}).get("cost") or {}
    status = cost.get("throttleStatus") or {}
    available = status.get("currentlyAvailable")
    rate = status.get("restoreRate") or 50
    if available is not None and available < THROTTLE_FLOOR:
        time.sleep((THROTTLE_FLOOR - available) / rate)


def _graphql_request(
    shop_domain: str,
    access_token: str,
    api_version: str,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shop_domain, access_token, api_version = _validate_shop_api_inputs(shop_domain, access_token, api_version)
    url = f"https://{shop_domain}/admin/api/{api_version}/graphql.json"
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    opener = urllib.request.build_opener(_NoRedirectHandler())
    last_error = "unknown error"

    for attempt in range(MAX_RETRIES):
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Shopify-Access-Token": access_token,
            },
        )
        try:
            with opener.open(request, timeout=60) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            text = error.read().decode("utf-8", errors="replace")
            if error.code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {error.code}: {text[:200]}"
                time.sleep(_retry_after(error) or _backoff(attempt))
                continue
            if error.code in (401, 403):
                raise ShopifyScopeError(f"Shopify Admin API HTTP {error.code}: {text[:300]}") from error
            raise ShopifyAdminAPIError(f"Shopify Admin API HTTP {error.code}: {text[:500]}") from error
        except urllib.error.URLError as error:
            last_error = f"connection error: {error.reason}"
            time.sleep(_backoff(attempt))
            continue

        try:
            result = json.loads(body)
        except json.JSONDecodeError as error:
            raise ShopifyAdminAPIError("Shopify Admin API returned invalid JSON.") from error

        errors = result.get("errors")
        if errors:
            codes = {
                (e.get("extensions") or {}).get("code")
                for e in (errors if isinstance(errors, list) else [])
                if isinstance(e, dict)
            }
            if "THROTTLED" in codes:
                last_error = "THROTTLED"
                _respect_throttle(result)
                time.sleep(_backoff(attempt))
                continue
            if "ACCESS_DENIED" in codes:
                raise ShopifyScopeError(f"Access denied: {str(errors)[:300]}")
            raise ShopifyAdminAPIError(f"Shopify GraphQL errors: {str(errors)[:500]}")

        _respect_throttle(result)
        return result

    raise ShopifyAdminAPIError(f"Shopify Admin API failed after {MAX_RETRIES} attempts: {last_error}")


# ── helpers ──────────────────────────────────────────────────────────────

def _html_to_text(value: str | None) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", value or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</li>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def _nodes(connection: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Works for both {edges:[{node}]} and {nodes:[]} shapes."""
    if not connection:
        return []
    if connection.get("nodes") is not None:
        return connection["nodes"] or []
    return [e.get("node") or {} for e in (connection.get("edges") or [])]


# ── PRODUCTS FOR AUDIT ───────────────────────────────────────────────────

_VARIANT_FIELDS = """
  id title sku barcode price compareAtPrice position taxable
  availableForSale inventoryPolicy inventoryQuantity
  selectedOptions { name value }
  image { id url altText }
  inventoryItem { tracked requiresShipping }
"""

_PRODUCTS_QUERY = (
    """
query ProductsForAudit($cursor: String, $first: Int!, $query: String) {
  products(first: $first, after: $cursor, query: $query) {
    edges { node {
      id title handle vendor productType tags descriptionHtml status
      onlineStoreUrl isGiftCard hasOnlyDefaultVariant tracksInventory
      category { id name fullName }
      seo { title description }
      options { id name position values }
      variants(first: __VF__) {
        pageInfo { hasNextPage endCursor }
        edges { node { __VARIANT__ } }
      }
      media(first: __MF__) {
        pageInfo { hasNextPage }
        edges { node { mediaContentType alt ... on MediaImage { id image { url altText } } } }
      }
      metafields(first: __MT__) {
        pageInfo { hasNextPage endCursor }
        edges { node { namespace key type value } }
      }
      resourcePublicationsV2(first: __PB__, onlyPublished: true) {
        nodes { isPublished publication { id name } }
      }
    } }
    pageInfo { hasNextPage endCursor }
  }
}
""".replace("__VARIANT__", _VARIANT_FIELDS)
    .replace("__VF__", str(VARIANTS_FIRST))
    .replace("__MF__", str(MEDIA_FIRST))
    .replace("__MT__", str(METAFIELDS_FIRST))
    .replace("__PB__", str(PUBLICATIONS_FIRST))
)

_MORE_VARIANTS_QUERY = """
query MoreVariants($id: ID!, $after: String) {
  product(id: $id) {
    variants(first: 50, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node { __VARIANT__ } }
    }
  }
}
""".replace("__VARIANT__", _VARIANT_FIELDS)

_MORE_METAFIELDS_QUERY = """
query MoreMetafields($id: ID!, $after: String) {
  product(id: $id) {
    metafields(first: 50, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node { namespace key type value } }
    }
  }
}
"""

_PRODUCTS_COUNT_QUERY = """
query ProductsCount($query: String) {
  productsCount(query: $query) { count precision }
}
"""


def _drain(creds, product_id, query, field, first_connection) -> tuple[list[dict], bool]:
    """Follow nested pagination. Returns (edges, still_truncated)."""
    edges = list(first_connection.get("edges") or [])
    info = first_connection.get("pageInfo") or {}
    pages = 0
    while info.get("hasNextPage") and pages < MAX_EXTRA_PAGES:
        res = _graphql_request(*creds, query, {"id": product_id, "after": info.get("endCursor")})
        conn = ((res.get("data") or {}).get("product") or {}).get(field) or {}
        edges += conn.get("edges") or []
        info = conn.get("pageInfo") or {}
        pages += 1
    return edges, bool(info.get("hasNextPage"))


def _compact_admin_product(product: dict[str, Any], creds: tuple[str, str, str]) -> dict[str, Any]:
    warnings: list[str] = []
    product_id = product.get("id")

    v_conn = product.get("variants") or {}
    v_edges, v_trunc = _drain(creds, product_id, _MORE_VARIANTS_QUERY, "variants", v_conn)
    if v_trunc:
        warnings.append("variants_truncated")

    compact_variants = []
    for edge in v_edges:
        v = edge.get("node") or {}
        selected = v.get("selectedOptions") or []
        values = [o.get("value") for o in selected]
        image = v.get("image") or {}
        inv_item = v.get("inventoryItem") or {}
        compact_variants.append({
            "id": v.get("id"),
            "title": v.get("title"),
            "sku": v.get("sku"),
            "barcode": v.get("barcode"),
            "price": v.get("price"),
            "compare_at_price": v.get("compareAtPrice"),
            "available": v.get("availableForSale"),
            "inventory_policy": v.get("inventoryPolicy"),
            "inventory_quantity": v.get("inventoryQuantity"),
            "inventory_tracked": inv_item.get("tracked"),
            "requires_shipping": inv_item.get("requiresShipping"),
            "selectedOptions": selected,
            "option1": values[0] if len(values) > 0 else None,
            "option2": values[1] if len(values) > 1 else None,
            "option3": values[2] if len(values) > 2 else None,
            "image": {"id": image.get("id"), "src": image.get("url"), "alt": image.get("altText")}
            if image.get("url") else None,
        })

    # media
    media_conn = product.get("media") or {}
    if (media_conn.get("pageInfo") or {}).get("hasNextPage"):
        warnings.append("media_truncated")
    images = []
    media_types: dict[str, int] = {}
    for edge in media_conn.get("edges") or []:
        node = edge.get("node") or {}
        mtype = node.get("mediaContentType") or "UNKNOWN"
        media_types[mtype] = media_types.get(mtype, 0) + 1
        image = node.get("image")
        if image:
            images.append({
                "id": node.get("id"),
                "src": image.get("url"),
                "alt": image.get("altText") or node.get("alt"),
                "position": len(images) + 1,
            })

    # metafields 
    m_edges, m_trunc = _drain(creds, product_id, _MORE_METAFIELDS_QUERY, "metafields", product.get("metafields") or {})
    if m_trunc:
        warnings.append("metafields_truncated")
    metafields: dict[str, Any] = {}
    for edge in m_edges:
        node = edge.get("node") or {}
        ns, key = node.get("namespace"), node.get("key")
        if ns and key:
            metafields[f"{ns}.{key}"] = {
                "namespace": ns, "key": key, "type": node.get("type"), "value": node.get("value"),
            }

    channels = [
        (n.get("publication") or {}).get("name")
        for n in _nodes(product.get("resourcePublicationsV2"))
        if n.get("isPublished")
    ]

    online_url = product.get("onlineStoreUrl") 

    return {
        "id": product_id,
        "title": product.get("title"),
        "handle": product.get("handle"),
        "url": online_url,                     
        "online_store_url": online_url,
        "vendor": product.get("vendor"),
        "product_type": product.get("productType"),
        "category": product.get("category"),    
        "status": product.get("status"),
        "tags": product.get("tags") or [],
        "description": product.get("descriptionHtml") or "",           
        "description_text": _html_to_text(product.get("descriptionHtml")),  
        "seo": product.get("seo") or {},
        "is_gift_card": product.get("isGiftCard"),
        "has_only_default_variant": product.get("hasOnlyDefaultVariant"),
        "tracks_inventory": product.get("tracksInventory"),
        "published_channels": [c for c in channels if c],
        "options": product.get("options") or [],
        "image": images[0] if images else None,
        "images": images,
        "media_types": media_types,
        "variants": compact_variants,
        "metafields": metafields,
        "data_warnings": warnings,
    }


def fetch_products_count(shop_domain: str, access_token: str, api_version: str, status: str | None = "active") -> int | None:
    """Total products, so the report can say 'audited 10 of N'."""
    if status is not None and status not in _ALLOWED_PRODUCT_STATUSES:
        raise ValueError("status must be active, draft, archived, or None.")
    try:
        res = _graphql_request(
            shop_domain, access_token, api_version, _PRODUCTS_COUNT_QUERY,
            {"query": f"status:{status}" if status else None},
        )
        return ((res.get("data") or {}).get("productsCount") or {}).get("count")
    except ShopifyAdminAPIError:
        return None


def fetch_products_admin(
    shop_domain: str,
    access_token: str,
    max_products: int | None,
    api_version: str,
    status: str | None = "active",
) -> list[dict[str, Any]]:
    """Cursor-paginated product fetch. Only ACTIVE products by default:
    drafts/archived products are not sellable and must not be audited."""
    _validate_shop_api_inputs(shop_domain, access_token, api_version)
    if status is not None and status not in _ALLOWED_PRODUCT_STATUSES:
        raise ValueError("status must be active, draft, archived, or None.")
    if max_products is not None and max_products <= 0:
        return []

    creds = (shop_domain.strip().lower().rstrip("."), access_token, api_version.strip())
    products: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        first = PRODUCTS_PAGE_SIZE
        if max_products is not None:
            first = min(first, max_products - len(products))

        result = _graphql_request(
            *creds, _PRODUCTS_QUERY,
            {"cursor": cursor, "first": first, "query": f"status:{status}" if status else None},
        )
        connection = (result.get("data") or {}).get("products") or {}
        edges = connection.get("edges") or []
        if not edges:
            break

        for edge in edges:
            products.append(_compact_admin_product(edge.get("node") or {}, creds))
            if max_products is not None and len(products) >= max_products:
                return products

        page_info = connection.get("pageInfo") or {}
        cursor = page_info.get("endCursor")
        if not page_info.get("hasNextPage") or not cursor:
            break

    return products


# ── PRODUCT VARIANT STATE ────────────────────────────

_PRODUCT_VARIANT_STATE_QUERY = """
query ProductVariantsForFix($id: ID!, $cursor: String) {
  product(id: $id) {
    id title
    options { id name position values }
    variants(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      edges { node { id title sku price selectedOptions { name value } } }
    }
  }
}
"""


def fetch_product_variant_state(shop_domain: str, access_token: str, api_version: str, product_id: str) -> dict[str, Any]:
    if not shop_domain:
        raise ValueError("shop_domain is required.")
    if not access_token:
        raise ValueError("access_token is required.")
    if not product_id:
        raise ValueError("product_id is required.")
    creds = _validate_shop_api_inputs(shop_domain, access_token, api_version)
    result = _graphql_request(*creds, _PRODUCT_VARIANT_STATE_QUERY, {"id": product_id, "cursor": None})
    product = (result.get("data") or {}).get("product")
    if not product:
        raise ShopifyAdminAPIError(f"Product '{product_id}' not found or inaccessible.")

    connection = product.get("variants") or {}
    variants = list(connection.get("edges") or [])
    page_info = connection.get("pageInfo") or {}
    page_count = 1
    while page_info.get("hasNextPage") and page_count < MAX_EXTRA_PAGES:
        cursor = page_info.get("endCursor")
        if not cursor:
            raise ShopifyAdminAPIError("Variant pagination indicated another page without an end cursor.")
        next_result = _graphql_request(*creds, _PRODUCT_VARIANT_STATE_QUERY, {"id": product_id, "cursor": cursor})
        next_product = (next_result.get("data") or {}).get("product")
        if not next_product:
            raise ShopifyAdminAPIError(f"Product '{product_id}' became unavailable during variant pagination.")
        next_connection = next_product.get("variants") or {}
        variants.extend(next_connection.get("edges") or [])
        page_info = next_connection.get("pageInfo") or {}
        page_count += 1
    if page_info.get("hasNextPage"):
        raise ShopifyAdminAPIError("Variant state is truncated after the configured pagination safety cap.")
    product["variants"] = {"edges": variants, "pageInfo": {"hasNextPage": False}}
    return product


# ── STORE CONTEXT ─────────────────────

_CORE_QUERY = """
query StoreCore {
  shop {
    id name email contactEmail currencyCode myshopifyDomain
    primaryDomain { host url sslEnabled }
    metafields(first: 20) { edges { node { namespace key type value } } }
  }
}
"""

_POLICIES_QUERY = """
query StorePolicies { shop { shopPolicies { id type title body url } } }
"""

_PROFILE_QUERY = """
query StoreProfile {
  shop {
    id
    name
    description
    shipsToCountries
    primaryDomain {
      host
      url
    }
  }
}
"""

_DELIVERY_QUERY = """
query StoreDelivery {
  deliveryProfiles(first: 5) {
    nodes {
      id name default
      profileLocationGroups {
        locationGroupZones(first: 10) {
          nodes {
            zone { id name countries { code { countryCode restOfWorld } } }
            methodDefinitions(first: 10) { nodes { id name active description } }
          }
        }
      }
    }
  }
}
"""

_LOCATIONS_QUERY = """
query StoreLocations {
  locations(first: 20) {
    nodes { id name isActive fulfillsOnlineOrders shipsInventory localPickupSettingsV2 { pickupTime instructions } }
  }
}
"""

_CONTENT_QUERY = """
query StoreContent {
  pages(first: 50) { nodes { id title handle bodySummary } }
  menus(first: 10) { nodes { id handle title items { title url items { title url } } } }
}
"""

_DEFINITIONS_QUERY = """
query StoreDefinitions {
  metafieldDefinitions(ownerType: PRODUCT, first: 50) {
    edges { node { id namespace key name type { name } } }
  }
  metaobjectDefinitions(first: 50) {
    edges { node { id type name description displayNameKey metaobjectsCount
      fieldDefinitions { key name type { name } } } }
  }
}
"""

_METAOBJECT_ENTRIES_QUERY = """
query Entries($type: String!) {
  metaobjects(type: $type, first: 10) {
    nodes { id handle displayName fields { key value } }
  }
}
"""


def _section(sections: dict[str, dict], name: str, fn: Callable[[], Any]) -> Any:
    try:
        data = fn()
        sections[name] = {"status": "ok", "error": None}
        return data
    except ShopifyScopeError as error:
        sections[name] = {"status": "scope_missing", "error": str(error)[:300]}
    except ShopifyAdminAPIError as error:
        sections[name] = {"status": "error", "error": str(error)[:300]}
    return None


def fetch_store_context_admin(shop_domain: str, access_token: str, api_version: str) -> dict[str, Any]:
    """Store-level context. A failed section is recorded in ctx["sections"] and
    the matching deterministic checks return 'na' (unknown) instead of
    reporting a defect. Never returns an empty dict silently."""
    creds = _validate_shop_api_inputs(shop_domain, access_token, api_version)
    sections: dict[str, dict] = {}
    ctx: dict[str, Any] = {"shop": {}, "sections": sections}

    def run(query: str) -> dict[str, Any]:
        return (_graphql_request(*creds, query).get("data") or {})

    core = _section(sections, "core", lambda: run(_CORE_QUERY))
    if core:
        ctx["shop"].update(core.get("shop") or {})

    pol = _section(sections, "policies", lambda: run(_POLICIES_QUERY))
    ctx["policies"] = ((pol or {}).get("shop") or {}).get("shopPolicies") or []
    ctx["shop"]["shopPolicies"] = ctx["policies"]

    prof = _section(sections, "profile", lambda: run(_PROFILE_QUERY))
    if prof:
        ctx["shop"].update(prof.get("shop") or {})

    deliv = _section(sections, "delivery", lambda: run(_DELIVERY_QUERY))
    ctx["delivery_profiles"] = _nodes((deliv or {}).get("deliveryProfiles"))

    loc = _section(sections, "locations", lambda: run(_LOCATIONS_QUERY))
    ctx["locations"] = _nodes((loc or {}).get("locations"))

    content = _section(sections, "content", lambda: run(_CONTENT_QUERY))
    ctx["pages"] = _nodes((content or {}).get("pages"))
    ctx["menus"] = _nodes((content or {}).get("menus"))

    defs = _section(sections, "definitions", lambda: run(_DEFINITIONS_QUERY))
    ctx["metafieldDefinitions"] = (defs or {}).get("metafieldDefinitions") or {"edges": []}
    ctx["metaobjectDefinitions"] = (defs or {}).get("metaobjectDefinitions") or {"edges": []}

    entries: dict[str, list] = {}
    for edge in (ctx["metaobjectDefinitions"].get("edges") or [])[:10]:
        node = edge.get("node") or {}
        if node.get("type") and (node.get("metaobjectsCount") or 0) > 0:
            try:
                res = _graphql_request(*creds, _METAOBJECT_ENTRIES_QUERY, {"type": node["type"]})
                entries[node["type"]] = _nodes((res.get("data") or {}).get("metaobjects"))
            except ShopifyAdminAPIError:
                pass
    ctx["metaobject_entries"] = entries
    return ctx


def fetch_store_policies(shop_domain: str, access_token: str, api_version: str) -> list[dict[str, Any]]:
    """Kept for backward compatibility. Uses GraphQL (REST policies.json is legacy).
    fetch_store_context_admin() already includes ctx["policies"], so jobs.py
    no longer needs a second call."""
    res = _graphql_request(shop_domain, access_token, api_version, _POLICIES_QUERY)
    return ((res.get("data") or {}).get("shop") or {}).get("shopPolicies") or []
