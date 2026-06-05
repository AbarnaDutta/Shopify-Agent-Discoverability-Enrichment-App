# app/services/product_fetcher.py
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any


# ── exceptions ────────────────────────────────────────────────────────

class InvalidStoreURLError(Exception):
    """Raised when the URL is syntactically wrong or missing a host."""

class NonShopifyStoreError(Exception):
    """Raised when the URL resolves but is not a Shopify store."""

class StoreUnreachableError(Exception):
    """Raised when the store URL cannot be reached at all."""

@dataclass
class ShopifyConfig:
    store_url: str
    api_version: str


def normalize_store_url(store: str) -> str:
    print("Normalizing store URL:", repr(store))
    store = store.strip()

    if not store:
        raise InvalidStoreURLError("Shopify store URL is required.")

    store = re.sub(r"^https?:/*", "", store, flags=re.IGNORECASE)

    store = store.lstrip("/")
    store = store.rstrip("/")

    store = f"https://{store}"

    parsed = urllib.parse.urlparse(store)

    if not parsed.netloc or "." not in parsed.netloc:
        raise InvalidStoreURLError(
            f"'{store}' doesn't look like a valid store URL. "
            "Try entering it like: your-store.myshopify.com"
        )

    return store
def request_json(url: str, headers: dict[str, str] | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload, dict(response.headers.items())
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} while fetching {url}: {message}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not fetch {url}: {error.reason}") from error


def fetch_products_public(store_url: str, max_products: int) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    page = 1

    while len(products) < max_products:
        limit = min(250, max_products - len(products))
        url = f"{store_url}/products.json?limit={limit}&page={page}"

        try:
            payload, _headers = request_json(url)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise NonShopifyStoreError(
                    f"'{store_url}' does not appear to be a Shopify store — "
                    "/products.json returned 404."
                ) from error
            raise
        except RuntimeError as error:
            msg = str(error)
            if any(k in msg for k in ("Name or service not known", "nodename nor servname",
                                       "Could not fetch", "getaddrinfo")):
                raise StoreUnreachableError(
                    f"Could not reach '{store_url}'. "
                    "Please check that the store URL is correct and the store is live."
                ) from error
            raise

        if "products" not in payload:
            raise NonShopifyStoreError(
                f"'{store_url}' responded but does not look like a Shopify store — "
                "no 'products' key in the response."
            )

        batch = payload.get("products", [])
        if not batch:
            break

        products.extend(batch)
        if len(batch) < limit:
            break
        page += 1

    return products


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def compact_product(product: dict[str, Any], store_url: str) -> dict[str, Any]:
    handle = product.get("handle")
    variants = product.get("variants") or []
    images = product.get("images") or []

    return {
        "id": product.get("id"),
        "title": product.get("title"),
        "handle": handle,
        "url": f"{store_url}/products/{handle}" if handle else None,
        "vendor": product.get("vendor"),
        "product_type": product.get("product_type"),
        "tags": product.get("tags"),
        "description": strip_html(product.get("body_html")),
        "options": product.get("options"),
        "variants": [
            {
                "id": variant.get("id"),
                "title": variant.get("title"),
                "sku": variant.get("sku"),
                "price": variant.get("price"),
                "barcode": variant.get("barcode"),
                "available": variant.get("available"),
                "inventory_quantity": variant.get("inventory_quantity"),
                "option1": variant.get("option1"),
                "option2": variant.get("option2"),
                "option3": variant.get("option3"),
            }
            for variant in variants[:20]
        ],
        "images": [
            {
                "src": image.get("src"),
                "alt": image.get("alt"),
                "position": image.get("position"),
            }
            for image in images[:10]
        ],
    }
