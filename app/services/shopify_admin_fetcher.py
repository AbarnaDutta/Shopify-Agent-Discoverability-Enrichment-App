#app/services/shopify_admin_fetcher.py
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class ShopifyAdminAPIError(Exception):
    """Raised when Shopify Admin GraphQL returns an error."""


def _graphql_request(
    shop_domain: str,
    access_token: str,
    api_version: str,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Execute a Shopify Admin GraphQL request.
    """

    url = (
        f"https://{shop_domain}/admin/api/"
        f"{api_version}/graphql.json"
    )

    payload = json.dumps(
        {
            "query": query,
            "variables": variables or {},
        }
    ).encode("utf-8")

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
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")

        raise ShopifyAdminAPIError(
            f"Shopify Admin API HTTP {error.code}: {body}"
        ) from error

    except urllib.error.URLError as error:
        raise ShopifyAdminAPIError(
            f"Could not connect to Shopify Admin API: {error.reason}"
        ) from error

    try:
        result = json.loads(body)
    except json.JSONDecodeError as error:
        raise ShopifyAdminAPIError(
            "Shopify Admin API returned invalid JSON."
        ) from error

    if result.get("errors"):
        raise ShopifyAdminAPIError(
            f"Shopify GraphQL errors: {result['errors']}"
        )

    return result


_PRODUCTS_QUERY = """
query ProductsForAudit($cursor: String, $first: Int!) {
  products(first: $first, after: $cursor) {
    edges {
      cursor

      node {
        id
        title
        handle
        vendor
        productType
        tags
        descriptionHtml
        status

        onlineStoreUrl

        options {
          id
          name
          values
        }

        variants(first: 100) {
          edges {
            node {
              id
              title
              sku
              barcode
              price

              selectedOptions {
                name
                value
              }

              inventoryQuantity
            }
          }
        }

        media(first: 10) {
          edges {
            node {
              ... on MediaImage {
                image {
                  url
                  altText
                }
              }
            }
          }
        }

        gtin: metafield(namespace: "app", key: "gtin") {
          value
          type
        }

        mpn: metafield(namespace: "app", key: "mpn") {
          value
          type
        }

        isDigitalService: metafield(
          namespace: "app",
          key: "is_digital_service"
        ) {
          value
          type
        }

        requiresCustomerInput: metafield(
          namespace: "app",
          key: "requires_customer_input"
        ) {
          value
          type
        }

        deliveryMethod: metafield(
          namespace: "app",
          key: "delivery_method"
        ) {
          value
          type
        }

        dimensions: metafield(
          namespace: "app",
          key: "dimensions"
        ) {
          value
          type
        }

        material: metafield(
          namespace: "app",
          key: "material"
        ) {
          value
          type
        }

        occasion: metafield(
          namespace: "app",
          key: "occasion"
        ) {
          value
          type
        }

        targetRecipient: metafield(
          namespace: "app",
          key: "target_recipient"
        ) {
          value
          type
        }

        contents: metafield(
          namespace: "app",
          key: "contents"
        ) {
          value
          type
        }

        agentGuardrails: metafield(
          namespace: "app",
          key: "agent_guardrails"
        ) {
          value
          type
        }
      }
    }

    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


def _compact_admin_product(
    product: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert Shopify Admin GraphQL product data into the same
    normalized structure consumed by the existing audit engine.
    """

    variants = product.get("variants", {}).get("edges", [])
    media = product.get("media", {}).get("edges", [])

    compact_variants = []

    for edge in variants[:20]:
        variant = edge.get("node", {})

        selected_options = variant.get("selectedOptions") or []

        option_values = [
            option.get("value")
            for option in selected_options
        ]

        compact_variants.append(
            {
                "id": variant.get("id"),
                "title": variant.get("title"),
                "sku": variant.get("sku"),
                "price": variant.get("price"),
                "barcode": variant.get("barcode"),
                "available": None,
                "inventory_quantity": variant.get(
                    "inventoryQuantity"
                ),
                "option1": (
                    option_values[0]
                    if len(option_values) > 0
                    else None
                ),
                "option2": (
                    option_values[1]
                    if len(option_values) > 1
                    else None
                ),
                "option3": (
                    option_values[2]
                    if len(option_values) > 2
                    else None
                ),
            }
        )

    compact_images = []

    for edge in media[:10]:
        node = edge.get("node", {})
        image = node.get("image")

        if not image:
            continue

        compact_images.append(
            {
                "src": image.get("url"),
                "alt": image.get("altText"),
                "position": None,
            }
        )

    metafields = {
        "gtin": product.get("gtin"),
        "mpn": product.get("mpn"),
        "is_digital_service": product.get(
            "isDigitalService"
        ),
        "requires_customer_input": product.get(
            "requiresCustomerInput"
        ),
        "delivery_method": product.get(
            "deliveryMethod"
        ),
        "dimensions": product.get("dimensions"),
        "material": product.get("material"),
        "occasion": product.get("occasion"),
        "target_recipient": product.get(
            "targetRecipient"
        ),
        "contents": product.get("contents"),
        "agent_guardrails": product.get(
            "agentGuardrails"
        ),
    }

    return {
        "id": product.get("id"),
        "title": product.get("title"),
        "handle": product.get("handle"),
        "url": product.get("onlineStoreUrl"),
        "vendor": product.get("vendor"),
        "product_type": product.get("productType"),
        "status": product.get("status"),
        "tags": product.get("tags") or [],
        "description": product.get("descriptionHtml") or "",
        "options": product.get("options") or [],
        "variants": compact_variants,
        "images": compact_images,
        "metafields": metafields,
    }


def fetch_products_admin(
    shop_domain: str,
    access_token: str,
    max_products: int | None,
    api_version: str,
) -> list[dict[str, Any]]:
    """
    Fetch products from Shopify Admin GraphQL using cursor pagination.

    max_products=None means fetch all products.
    """

    if not shop_domain:
        raise ValueError("shop_domain is required.")

    if not access_token:
        raise ValueError("access_token is required.")

    if max_products is not None and max_products <= 0:
        return []

    products: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        if max_products is None:
            first = 100
        else:
            remaining = max_products - len(products)
            first = min(100, remaining)

        result = _graphql_request(
            shop_domain=shop_domain,
            access_token=access_token,
            api_version=api_version,
            query=_PRODUCTS_QUERY,
            variables={
                "cursor": cursor,
                "first": first,
            },
        )

        data = result.get("data") or {}
        products_connection = data.get("products") or {}

        edges = products_connection.get("edges") or []

        if not edges:
            break

        for edge in edges:
            product = edge.get("node") or {}

            products.append(
                _compact_admin_product(product)
            )

            if (
                max_products is not None
                and len(products) >= max_products
            ):
                break

        if (
            max_products is not None
            and len(products) >= max_products
        ):
            break

        page_info = (
            products_connection.get("pageInfo") or {}
        )

        if not page_info.get("hasNextPage"):
            break

        cursor = page_info.get("endCursor")

        if not cursor:
            break

    return products