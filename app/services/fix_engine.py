# app/services/fix_engine.py
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Callable
from urllib.parse import urlparse

from app.services.issue_registry import get_issue_definition
from app.services.shopify_admin_fetcher import (
    ShopifyAdminAPIError,
    _graphql_request,
)

API_VERSION = "2026-07"
MAX_BULK = 250

_SHOP_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.myshopify\.com")
_PRODUCT_GID_RE = re.compile(r"gid://shopify/Product/[0-9]+")
_SHOP_GID_RE = re.compile(r"gid://shopify/Shop/[0-9]+")
_PAGE_GID_RE = re.compile(r"gid://shopify/Page/[0-9]+")
_OPTION_GID_RE = re.compile(r"gid://shopify/ProductOption/[0-9]+")
_DIGITS_RE = re.compile(r"[0-9]+")

POLICY_TYPES = {
    "REFUND_POLICY",
    "SHIPPING_POLICY",
    "CONTACT_INFORMATION",
    "PRIVACY_POLICY",
    "TERMS_OF_SERVICE",
}

STORE_CHANGE_FIELDS: dict[str, set[str]] = {
    "update_fulfillment_information": {
        "delivery_profile_id", "delivery_profile_update", "pickup_settings",
        "shipping_policy_body", "merchant_approved",
    },
    "update_policy": {"policy_type", "body", "merchant_approved"},
    "update_store_contact": {"body", "merchant_approved"},
    "update_brand_information": {"page_id", "body", "title", "publish", "merchant_approved"},
    "configure_store_guardrail": {"warning_text", "shop_id", "merchant_approved"},
    "create_faq": {"title", "body", "publish", "merchant_approved"},
}


NORMALIZE_ACTIONS = {
    "normalize_option_structure",
    "normalize_metafield_structure",
    "normalize_attribute_formats",
    "normalize_attribute_units",
}


# ---------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------

def _clean_shop(shop_domain: Any, access_token: Any) -> tuple[str, str]:
    """Validate credentials so the token is only ever sent to *.myshopify.com."""
    shop_domain = str(shop_domain or "").strip().lower()
    access_token = str(access_token or "").strip()
    if not _SHOP_RE.fullmatch(shop_domain):
        raise ValueError("A valid shop.myshopify.com hostname is required.")
    if not access_token:
        raise ValueError("Shopify access token is required.")
    return shop_domain, access_token


def _gql(
    shop_domain: Any,
    access_token: Any,
    query: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    shop_domain, access_token = _clean_shop(shop_domain, access_token)
    response = _graphql_request(
        shop_domain, access_token, API_VERSION, query, variables or {}
    )
    if not isinstance(response, dict):
        raise ShopifyAdminAPIError("Malformed response from Shopify.")
    if response.get("errors"):
        raise ShopifyAdminAPIError(f"Shopify GraphQL error: {response['errors']}")
    data = response.get("data")
    if not isinstance(data, dict):
        raise ShopifyAdminAPIError("Shopify returned no data.")
    return data


def _mutate(
    shop_domain: Any,
    access_token: Any,
    mutation: str,
    variables: dict[str, Any],
    operation: str,
    label: str,
) -> dict[str, Any]:
    """Run a mutation and raise on top-level errors, missing result or userErrors."""
    data = _gql(shop_domain, access_token, mutation, variables)
    result = data.get(operation)
    if not result:
        raise ShopifyAdminAPIError(f"Shopify returned no result for {operation}.")
    user_errors = result.get("userErrors") or []
    if user_errors:
        messages = "; ".join(
            e.get("message", "Unknown Shopify error") for e in user_errors
        )
        raise ShopifyAdminAPIError(f"{label} failed: {messages}")
    return result


def _require(value: Any, message: str) -> str:
    value = str(value or "").strip()
    if not value:
        raise ValueError(message)
    return value


def _require_text(value: Any, message: str) -> str:
    """Strict: must already be a nonblank string."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    return value.strip()


def _require_product_gid(value: Any) -> str:
    value = str(value or "").strip()
    if not _PRODUCT_GID_RE.fullmatch(value):
        raise ValueError("A valid Shopify Product GID is required.")
    return value


def _dict_list(value: Any, name: str, *, max_items: int = MAX_BULK) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list.")
    if len(value) > max_items:
        raise ValueError(f"{name} may contain at most {max_items} items.")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"Every item in {name} must be an object.")
    return value


def _parse_price(raw: Any, label: str) -> Decimal:
    if raw is None or isinstance(raw, bool):
        raise ValueError(f"A price is required for {label}.")
    try:
        price = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise ValueError(f"Invalid price for {label}.") from None
    if not price.is_finite() or price < 0:
        raise ValueError(f"Price must be finite and nonnegative for {label}.")
    return price


def _is_valid_gtin(value: str) -> bool:
    """GTIN-8/12/13/14 with GS1 check digit."""
    if not _DIGITS_RE.fullmatch(value) or len(value) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in value]
    check = digits.pop()
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return (10 - total % 10) % 10 == check


PRODUCT_UPDATE = """
mutation ProductUpdate($product: ProductUpdateInput!) {
  productUpdate(product: $product) {
    product { id handle title productType descriptionHtml }
    userErrors { field message }
  }
}
"""

METAFIELDS_SET = """
mutation MetafieldsSet($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields { id namespace key type value }
    userErrors { field message code }
  }
}
"""

VARIANTS_BULK_UPDATE = """
mutation VariantsBulkUpdate(
  $productId: ID!,
  $variants: [ProductVariantsBulkInput!]!
) {
  productVariantsBulkUpdate(
    productId: $productId, variants: $variants, allowPartialUpdates: false
  ) {
    productVariants { id barcode price inventoryItem { id sku } }
    userErrors { field message code }
  }
}
"""

VARIANT_OPTIONS_UPDATE = """
mutation UpdateVariantOptions(
  $productId: ID!,
  $variants: [ProductVariantsBulkInput!]!
) {
  productVariantsBulkUpdate(
    productId: $productId, variants: $variants, allowPartialUpdates: false
  ) {
    productVariants { id selectedOptions { name value } }
    userErrors { field message code }
  }
}
"""

SHOP_POLICY_UPDATE = """
mutation UpdatePolicy($policy: ShopPolicyInput!) {
  shopPolicyUpdate(shopPolicy: $policy) {
    shopPolicy { id type body url }
    userErrors { field message code }
  }
}
"""

PRODUCT_VARIANT_STATE = """
query ProductVariantState($id: ID!, $cursor: String) {
  product(id: $id) {
    id
    title
    options { id name position values }
    variants(first: 100, after: $cursor) {
      pageInfo { hasNextPage endCursor }
      nodes { id title sku price selectedOptions { name value } }
    }
  }
}
"""

PRODUCT_MEDIA = """
query ProductMedia($id: ID!) {
  product(id: $id) {
    id
    media(first: 250) {
      pageInfo { hasNextPage }
      nodes { id alt mediaContentType }
    }
  }
}
"""

FILE_UPDATE = """
mutation SetImageAlts($files: [FileUpdateInput!]!) {
  fileUpdate(files: $files) {
    files { id alt fileStatus }
    userErrors { field message }
  }
}
"""

DELIVERY_PROFILE_UPDATE = """
mutation UpdateFulfillmentProfile($id: ID!, $profile: DeliveryProfileInput!) {
  deliveryProfileUpdate(id: $id, profile: $profile) {
    profile { id name }
    userErrors { field message }
  }
}
"""

LOCAL_PICKUP_ENABLE = """
mutation UpdatePickup($settings: DeliveryLocationLocalPickupEnableInput!) {
  locationLocalPickupEnable(localPickupSettings: $settings) {
    localPickupSettings { instructions pickupTime }
    userErrors { field message }
  }
}
"""


class FixEngine:
    """Central dispatcher for executing approved fixes."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "update_product_handle": self.update_product_handle,
            "set_metafield": self.set_metafield,
            "set_product_type": self.set_product_type,
            "update_product_type": self.update_product_type,
            "update_product_description": self.update_product_description,
            "update_product_title": self.update_product_title,
            "rename_product_option": self.rename_product_option,
            "generate_sku": self.generate_sku,
            "update_sku": self.update_sku,
            "fix_variant_options": self.fix_variant_options,
            "set_gtin": self.set_gtin,
            "set_mpn": self.set_mpn,
            "set_product_image": self.set_product_image,
            "set_product_image_alt": self.set_product_image_alt,
            "set_variant_price": self.set_variant_price,
            "review_product_claim": self.review_product_claim,
            "set_guardrail_metafield": self.set_guardrail_metafield,
        }

        self._store_handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "normalize_option_structure": lambda changes, **kw: self.normalize_option_structure(
                products=changes, **kw
            ),
            "normalize_metafield_structure": lambda changes, **kw: self.normalize_metafield_structure(
                products=changes, **kw
            ),
            "normalize_attribute_formats": lambda changes, **kw: self.normalize_attribute_formats(
                products=changes, **kw
            ),
            "normalize_attribute_units": lambda changes, **kw: self.normalize_attribute_units(
                products=changes, **kw
            ),
            "update_fulfillment_information": self._each(
                self.update_fulfillment_information, "update_fulfillment_information"
            ),
            "update_policy": self._each(self.update_policy, "update_policy"),
            "update_store_contact": self._each(self.update_store_contact, "update_store_contact"),
            "update_brand_information": self._each(
                self.update_brand_information, "update_brand_information"
            ),
            "configure_store_guardrail": self._each(
                self.configure_store_guardrail, "configure_store_guardrail"
            ),
            "create_faq": self._each(self.create_faq, "create_faq"),
        }

    # =================================================================
    # Dispatchers
    # =================================================================

    def execute_store(
        self,
        *,
        check_id: str,
        issue_type: str,
        changes: list[dict[str, Any]],
        shop_domain: str,
        access_token: str,
        issue_id: str | None = None,
        merchant_approved: bool | None = None,
    ) -> dict[str, Any]:
        definition = get_issue_definition(check_id, issue_type)
        if definition is None:
            raise ValueError(f"Unknown issue type '{issue_type}' for check '{check_id}'.")
        if definition.get("scope") != "store":
            raise ValueError(f"Issue '{issue_type}' is not store-scoped. Use /products/fix.")
        if definition.get("fix_mode") == "unsupported":
            raise ValueError(f"Issue '{issue_type}' is not automatically fixable.")

        fix_action = definition.get("fix_action")
        handler = self._store_handlers.get(fix_action)
        if handler is None:
            raise ValueError(f"No store-wide handler registered for fix_action '{fix_action}'.")

        changes = _dict_list(changes, "changes")

        needs_top_level_approval = (
            definition.get("fix_mode") == "approval" or fix_action in NORMALIZE_ACTIONS
        )
        if needs_top_level_approval and merchant_approved is not True:
            raise ValueError("Merchant approval is required.")

        if merchant_approved is True and fix_action in STORE_CHANGE_FIELDS:
            changes = [
                {**change, "merchant_approved": change.get("merchant_approved", True)}
                for change in changes
            ]

        result = handler(
            changes=changes, shop_domain=shop_domain, access_token=access_token
        )
        return {
            **result,
            "issue_id": issue_id,
            "check_id": check_id,
            "issue_type": issue_type,
            "fix_action": fix_action,
        }

    def execute(
        self,
        *,
        check_id: str,
        issue_type: str,
        product_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        definition = get_issue_definition(check_id, issue_type)
        if definition is None:
            raise ValueError(f"Unknown issue type '{issue_type}' for '{check_id}'.")
        if definition.get("scope") == "store":
            raise ValueError(f"Issue '{issue_type}' is store-scoped. Use execute_store.")

        fix_mode = definition.get("fix_mode")
        fix_action = definition.get("fix_action")

        if fix_mode == "unsupported":
            raise ValueError(f"Issue '{issue_type}' is not automatically fixable.")
        if not fix_action:
            raise ValueError(f"No fix_action configured for issue '{issue_type}'.")

        handler = self._handlers.get(fix_action)
        if handler is None:
            raise ValueError(f"No handler registered for fix_action '{fix_action}'.")

        if fix_mode == "approval" and kwargs.get("merchant_approved") is not True:
            raise ValueError("Merchant approval is required.")

        return handler(product_id=product_id, **kwargs)

    def validate_registered_actions(self) -> list[str]:
        """Registry shape errors plus supported actions that have no handler."""
        from app.services.issue_registry import ISSUE_TYPES, validate_issue_registry

        errors = validate_issue_registry()
        for check_id, issues in ISSUE_TYPES.items():
            for issue_type, definition in issues.items():
                if definition.get("fix_mode") == "unsupported":
                    continue
                handlers = (
                    self._store_handlers
                    if definition.get("scope") == "store"
                    else self._handlers
                )
                action = definition.get("fix_action")
                if action not in handlers:
                    errors.append(f"{check_id}/{issue_type}: missing handler for {action!r}")
        return errors

    def _each(self, fn: Callable[..., dict[str, Any]], action: str) -> Callable[..., dict[str, Any]]:
        allowed = STORE_CHANGE_FIELDS[action]
        return lambda changes, **kw: self._apply_each(
            fn, action, changes, allowed_fields=allowed, **kw
        )

    def _apply_each(
        self,
        fn: Callable[..., dict[str, Any]],
        action: str,
        changes: list[dict[str, Any]],
        *,
        allowed_fields: set[str],
        **kw: Any,
    ) -> dict[str, Any]:
        """Validate every change up front, then execute each independently (not atomic)."""
        for index, change in enumerate(changes):
            unknown = set(change) - allowed_fields
            if unknown:
                raise ValueError(
                    f"Change {index + 1} has unsupported field(s): {sorted(unknown)}."
                )
            if change.get("merchant_approved") is not True:
                raise ValueError(f"Change {index + 1}: merchant approval is required.")

        results: list[dict[str, Any]] = []
        for index, change in enumerate(changes):
            try:
                results.append({
                    "index": index,
                    "success": True,
                    "result": fn(**{**change, **kw}),
                })
            except (ValueError, ShopifyAdminAPIError) as error:
                results.append({"index": index, "success": False, "error": str(error)})

        successful = sum(1 for item in results if item["success"])
        failed = len(results) - successful
        return {
            "success": failed == 0,
            "partial_success": successful > 0 and failed > 0,
            "fix_action": action,
            "total": len(changes),
            "successful": successful,
            "failed": failed,
            "results": results,
            "verification_required": successful > 0,
            "message": (
                "All changes saved."
                if failed == 0
                else f"{successful} change(s) saved; {failed} failed. Refetch Shopify data before retrying."
            ),
        }

    # =================================================================
    # Product-level: handle / title / description / type
    # =================================================================

    def update_product_handle(
        self, *, product_id: str, handle: str, shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        product_id = _require(product_id, "Product ID is required.")
        handle = _require(handle, "Product handle is required.")
        result = _mutate(
            shop_domain, access_token, PRODUCT_UPDATE,
            {"product": {"id": product_id, "handle": handle}},
            "productUpdate", "Shopify product update",
        )
        product = result.get("product")
        if not product:
            raise ShopifyAdminAPIError("Shopify did not return the updated product.")
        return {
            "success": True,
            "product_id": product.get("id"),
            "handle": product.get("handle"),
            "fix_action": "update_product_handle",
            "message": "Product handle updated successfully.",
        }

    def suggest_product_handle(self, *, product_title: str) -> dict[str, Any]:
        value = unicodedata.normalize("NFKD", product_title or "")
        value = value.encode("ascii", "ignore").decode("ascii").lower()
        value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
        if not value:
            raise ValueError("Unable to generate a valid product handle from product title.")
        return {"suggested_handle": value}

    def set_product_type(
        self, *, product_id: str, product_type: str, shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        product_id = _require(product_id, "Product ID is required.")
        product_type = _require(product_type, "Product type is required.")
        result = _mutate(
            shop_domain, access_token, PRODUCT_UPDATE,
            {"product": {"id": product_id, "productType": product_type}},
            "productUpdate", "Shopify product update",
        )
        product = result.get("product")
        if not product:
            raise ShopifyAdminAPIError("Shopify did not return the updated product.")
        return {
            "success": True,
            "product_id": product.get("id"),
            "product_type": product.get("productType"),
            "fix_action": "set_product_type",
            "message": "Product type updated successfully.",
        }

    def update_product_type(
        self, *, product_id: str, product_type: str, shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        product_id = _require_product_gid(product_id)
        product_type = _require(product_type, "Product type is required.")
        result = _mutate(
            shop_domain, access_token, PRODUCT_UPDATE,
            {"product": {"id": product_id, "productType": product_type}},
            "productUpdate", "Shopify product update",
        )
        product = result.get("product") or {}
        if product.get("id") != product_id or product.get("productType") != product_type:
            raise ShopifyAdminAPIError("Shopify did not confirm the requested product type.")
        return {
            "success": True,
            "product_id": product["id"],
            "product_type": product["productType"],
            "fix_action": "update_product_type",
            "message": "Product type updated successfully.",
        }

    def update_product_description(
        self, *, product_id: str, description_html: str, shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        product_id = _require(product_id, "Product ID is required.")
        description_html = _require(description_html, "Product description is required.")
        result = _mutate(
            shop_domain, access_token, PRODUCT_UPDATE,
            {"product": {"id": product_id, "descriptionHtml": description_html}},
            "productUpdate", "Shopify product update",
        )
        product = result.get("product")
        if not product:
            raise ShopifyAdminAPIError("Shopify did not return the updated product.")
        return {
            "success": True,
            "product_id": product.get("id"),
            "description_html": product.get("descriptionHtml"),
            "fix_action": "update_product_description",
            "message": "Product description updated successfully.",
        }

    def review_product_claim(
        self,
        *,
        product_id: str,
        description_html: str,
        shop_domain: str,
        access_token: str,
        merchant_approved: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """Save a complete, merchant-reviewed replacement description.

        Does not validate substantiation, certify compliance, or remove the
        claim from other surfaces (ads, feeds, theme content, metafields).
        """
        if merchant_approved is not True:
            raise ValueError(
                "Merchant review and approval of the complete replacement description are required."
            )
        description_html = _require_text(
            description_html, "Provide the complete reviewed replacement description."
        )
        result = self.update_product_description(
            product_id=product_id,
            description_html=description_html,
            shop_domain=shop_domain,
            access_token=access_token,
        )
        return {
            **result,
            "fix_action": "review_product_claim",
            "verification_required": True,
            "message": (
                "Reviewed description saved. This does not certify the claim or remove "
                "it from other surfaces. Rerun the audit to confirm."
            ),
        }

    def update_product_title(
        self, *, product_id: str, title: str, shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        product_id = _require(product_id, "Product ID is required.")
        title = _require(title, "Product title is required.")
        result = _mutate(
            shop_domain, access_token, PRODUCT_UPDATE,
            {"product": {"id": product_id, "title": title}},
            "productUpdate", "Shopify product update",
        )
        product = result.get("product")
        if not product:
            raise ShopifyAdminAPIError("Shopify did not return the updated product.")
        return {
            "success": True,
            "product_id": product.get("id"),
            "title": product.get("title"),
            "fix_action": "update_product_title",
            "message": "Product title updated successfully.",
        }

    # =================================================================
    # Product-level: metafields / guardrails
    # =================================================================

    def set_metafield(
        self,
        *,
        product_id: str,
        attributes: list[dict[str, str]],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        """Set product metafields (default namespace 'details')."""
        product_id = _require(product_id, "Product ID is required.")
        attributes = _dict_list(attributes, "attributes", max_items=25)

        metafields = []
        seen: set[tuple[str, str]] = set()
        for attribute in attributes:
            key = _require_text(attribute.get("key"), "Metafield key is required.")
            mtype = _require_text(attribute.get("type"), f"Metafield type is required for '{key}'.")
            value = attribute.get("value")
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Metafield value is required for '{key}'.")
            namespace = str(attribute.get("namespace") or "details").strip()
            if (namespace, key) in seen:
                raise ValueError(f"Duplicate metafield '{namespace}.{key}' in request.")
            seen.add((namespace, key))
            metafields.append(
                {
                    "ownerId": product_id,
                    "namespace": namespace,
                    "key": key,
                    "type": mtype,
                    "value": value.strip(),
                }
            )

        result = _mutate(
            shop_domain, access_token, METAFIELDS_SET,
            {"metafields": metafields}, "metafieldsSet", "Shopify metafield update",
        )
        updated = result.get("metafields") or []
        if len(updated) != len(metafields):
            raise ShopifyAdminAPIError("Shopify did not return all updated metafields.")
        return {
            "success": True,
            "product_id": product_id,
            "fix_action": "set_metafield",
            "metafields": updated,
            "message": "Product metafields updated successfully.",
        }

    def set_guardrail_metafield(
        self,
        *,
        product_id: str,
        shop_domain: str,
        access_token: str,
        minimum_age: int | None = None,
        warning_text: str | None = None,
        merchant_approved: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """Save guardrail metadata (guardrails.minimum_age / guardrails.warning).

        This is disclosure metadata only. It does not enforce age restrictions;
        the collector must read the same namespace and keys.
        """
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required.")
        product_id = _require_product_gid(product_id)

        attributes: list[dict[str, str]] = []
        if minimum_age is not None:
            if (
                isinstance(minimum_age, bool)
                or not isinstance(minimum_age, int)
                or not 0 <= minimum_age <= 120
            ):
                raise ValueError("minimum_age must be a whole number between 0 and 120.")
            attributes.append({
                "namespace": "guardrails",
                "key": "minimum_age",
                "type": "number_integer",
                "value": str(minimum_age),
            })
        if warning_text is not None:
            attributes.append({
                "namespace": "guardrails",
                "key": "warning",
                "type": "multi_line_text_field",
                "value": _require_text(warning_text, "warning_text must not be blank."),
            })
        if not attributes:
            raise ValueError("Provide minimum_age and/or warning_text.")

        result = self.set_metafield(
            product_id=product_id, attributes=attributes,
            shop_domain=shop_domain, access_token=access_token,
        )
        return {
            **result,
            "fix_action": "set_guardrail_metafield",
            "verification_required": True,
            "message": (
                "Guardrail metadata saved. This is disclosure only; it does not "
                "enforce age restrictions or display a warning."
            ),
        }

    def set_mpn(
        self, *, product_id: str = "", variant_id: str, mpn: str, shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        """Set MPN for a variant (custom metafield identifiers.mpn)."""
        variant_id = _require(variant_id, "Variant ID is required.")
        mpn = _require(mpn, "MPN is required.")
        result = _mutate(
            shop_domain, access_token, METAFIELDS_SET,
            {
                "metafields": [
                    {
                        "ownerId": variant_id,
                        "namespace": "identifiers",
                        "key": "mpn",
                        "type": "single_line_text_field",
                        "value": mpn,
                    }
                ]
            },
            "metafieldsSet", "Shopify MPN update",
        )
        updated = result.get("metafields") or []
        if not updated:
            raise ShopifyAdminAPIError("Shopify did not return the updated MPN metafield.")
        return {
            "success": True,
            "product_id": product_id,
            "variant_id": variant_id,
            "fix_action": "set_mpn",
            "metafields": updated,
            "message": (
                "Variant MPN saved as a custom metafield (identifiers.mpn). "
                "It is not sent to sales channels or feeds unless mapped."
            ),
        }

    # =================================================================
    # Store-level: guardrail disclosure (Shop-owned $app metafield)
    # =================================================================

    def configure_store_guardrail(
        self,
        *,
        shop_domain: str,
        access_token: str,
        warning_text: str,
        shop_id: str | None = None,
        merchant_approved: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required.")
        if not isinstance(warning_text, str):
            raise ValueError("warning_text must be a string.")
        warning_text = warning_text.strip()
        if warning_text in ("", "[]", "{}", "null", "false"):
            raise ValueError("warning_text must contain a merchant-approved disclosure.")

        data = _gql(shop_domain, access_token, "query { shop { id } }")
        actual_id = (data.get("shop") or {}).get("id")
        if not actual_id or not _SHOP_GID_RE.fullmatch(actual_id):
            raise ShopifyAdminAPIError("Could not resolve the shop ID.")
        if shop_id is not None and str(shop_id).strip() != actual_id:
            raise ValueError("shop_id does not match the authenticated shop.")

        result = _mutate(
            shop_domain, access_token, METAFIELDS_SET,
            {
                "metafields": [
                    {
                        "ownerId": actual_id,
                        "namespace": "$app",
                        "key": "warning",
                        "type": "multi_line_text_field",
                        "value": warning_text,
                    }
                ]
            },
            "metafieldsSet", "Store disclosure update",
        )
        updated = result.get("metafields") or []
        if not updated:
            raise ShopifyAdminAPIError("Shopify did not return the updated metafield.")
        return {
            "success": True,
            "shop_id": actual_id,
            "fix_action": "configure_store_guardrail",
            "metafields": updated,
            "verification_required": True,
            "message": (
                "Store disclosure saved. This is evidence only; it does not display "
                "a warning or enforce restrictions."
            ),
        }

    # =================================================================
    # Store-level: policies, contact, brand/About page, FAQ
    # =================================================================

    def update_policy(
        self,
        *,
        shop_domain: str,
        access_token: str,
        policy_type: str,
        body: str,
        merchant_approved: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """Replace a policy with merchant-approved text (replaces the ENTIRE body)."""
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required.")
        if not isinstance(policy_type, str):
            raise ValueError("policy_type must be a string.")
        policy_type = policy_type.strip().upper()
        if policy_type not in POLICY_TYPES:
            raise ValueError(f"policy_type must be one of: {', '.join(sorted(POLICY_TYPES))}.")
        body = _require_text(body, "Provide the complete approved policy body.")

        result = _mutate(
            shop_domain, access_token, SHOP_POLICY_UPDATE,
            {"policy": {"type": policy_type, "body": body}},
            "shopPolicyUpdate", "Policy update",
        )
        policy = result.get("shopPolicy")
        if not policy:
            raise ShopifyAdminAPIError("Shopify did not return the updated policy.")
        return {
            "success": True,
            "fix_action": "update_policy",
            "policy": policy,
            "verification_required": True,
            "message": "Policy saved. Refetch policies and rerun the check; a successful save does not mean the check passes.",
        }

    def update_store_contact(
        self,
        *,
        shop_domain: str,
        access_token: str,
        body: str,
        merchant_approved: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        result = self.update_policy(
            shop_domain=shop_domain,
            access_token=access_token,
            policy_type="CONTACT_INFORMATION",
            body=body,
            merchant_approved=merchant_approved,
        )
        result["fix_action"] = "update_store_contact"
        return result

    def update_brand_information(
        self,
        *,
        shop_domain: str,
        access_token: str,
        page_id: str,
        body: str,
        merchant_approved: bool = False,
        title: str | None = None,
        publish: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """Replace the body of a merchant-selected About page (needs write_content).

        Cannot create a missing page; use create_faq-style creation separately if needed.
        """
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required.")
        page_id = str(page_id or "").strip()
        if not _PAGE_GID_RE.fullmatch(page_id):
            raise ValueError("An existing Shopify Page GID is required.")
        body = _require_text(body, "Provide the complete approved page body.")
        if not isinstance(publish, bool):
            raise ValueError("publish must be a boolean.")

        page_input: dict[str, Any] = {"body": body}
        if title is not None:
            page_input["title"] = _require_text(title, "title must not be blank.")
        if publish:
            page_input["isPublished"] = True

        result = _mutate(
            shop_domain, access_token,
            """
            mutation UpdateAbout($id: ID!, $page: PageUpdateInput!) {
              pageUpdate(id: $id, page: $page) {
                page { id title handle body isPublished }
                userErrors { field message }
              }
            }
            """,
            {"id": page_id, "page": page_input},
            "pageUpdate", "About page update",
        )
        page = result.get("page")
        if not page:
            raise ShopifyAdminAPIError("Shopify did not return the updated page.")
        return {
            "success": True,
            "fix_action": "update_brand_information",
            "page": page,
            "verification_required": True,
            "message": (
                "About page saved. Refetch published pages and rerun the check "
                "before reporting resolved."
            ),
        }

    def create_faq(
        self,
        *,
        shop_domain: str,
        access_token: str,
        title: str,
        body: str,
        merchant_approved: bool = False,
        publish: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """Create a page containing the complete approved FAQ HTML (draft unless publish=True).

        Creates a NEW page on every call. After a timeout, check existing pages
        before retrying to avoid duplicates. Does not add a navigation link.
        """
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required.")
        title = _require_text(title, "A nonblank FAQ page title is required.")
        body = _require_text(body, "The complete approved FAQ body is required.")
        if not isinstance(publish, bool):
            raise ValueError("publish must be a boolean.")

        result = _mutate(
            shop_domain, access_token,
            """
            mutation CreateFaq($page: PageCreateInput!) {
              pageCreate(page: $page) {
                page { id title handle isPublished }
                userErrors { field message }
              }
            }
            """,
            {"page": {"title": title, "body": body, "isPublished": publish}},
            "pageCreate", "FAQ page creation",
        )
        page = result.get("page")
        if not page:
            raise ShopifyAdminAPIError("Shopify did not return the created page.")
        return {
            "success": True,
            "fix_action": "create_faq",
            "page": page,
            "verification_required": True,
            "message": (
                "FAQ page created as a published page."
                if publish
                else "FAQ page created as a draft. Publish it and add a navigation link in Shopify admin."
            ),
        }

    # =================================================================
    # Images
    # =================================================================

    def set_product_image(
        self,
        *,
        product_id: str,
        image_url: str,
        alt_text: str,
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        product_id = _require_product_gid(product_id)
        image_url = (image_url or "").strip()
        parsed = urlparse(image_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("image_url must be an accessible HTTPS image URL.")
        alt_text = _require(alt_text, "Descriptive image alt text is required.")

        result = _mutate(
            shop_domain, access_token,
            """
            mutation AddProductImage($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
              productUpdate(product: $product, media: $media) {
                product { id }
                userErrors { field message }
              }
            }
            """,
            {
                "product": {"id": product_id},
                "media": [
                    {"originalSource": image_url, "mediaContentType": "IMAGE", "alt": alt_text}
                ],
            },
            "productUpdate", "Image upload",
        )
        if not result.get("product"):
            raise ShopifyAdminAPIError("Shopify did not return the updated product.")
        return {
            "success": True,
            "product_id": product_id,
            "fix_action": "set_product_image",
            "verification_required": True,
            "message": (
                "Image upload submitted. Wait for processing, then refetch "
                "the product and rerun check_media_quality."
            ),
        }

    def set_product_image_alt(
        self,
        *,
        product_id: str,
        image_alts: dict[str, str],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        """Set alt text for images missing it. Media ownership is verified against Shopify."""
        product_id = _require_product_gid(product_id)
        if not isinstance(image_alts, dict) or not image_alts:
            raise ValueError("image_alts must be a non-empty object of image ID to alt text.")

        data = _gql(shop_domain, access_token, PRODUCT_MEDIA, {"id": product_id})
        product = data.get("product")
        if not product:
            raise ShopifyAdminAPIError("Product not found.")
        media = product.get("media") or {}
        if (media.get("pageInfo") or {}).get("hasNextPage"):
            raise ShopifyAdminAPIError("Product has too many media items to update safely.")

        owned = {
            m["id"]: m
            for m in media.get("nodes") or []
            if m.get("mediaContentType") == "IMAGE" and m.get("id")
        }
        if not owned:
            raise ValueError("Product has no images. Add an image first.")
        unknown = [k for k in image_alts if k not in owned]
        if unknown:
            raise ValueError(f"Image(s) do not belong to this product: {unknown}.")

        files: list[dict[str, str]] = []
        for image_id, image in owned.items():
            if (image.get("alt") or "").strip():
                continue
            alt = image_alts.get(image_id)
            if not isinstance(alt, str) or not alt.strip():
                raise ValueError(f"Provide descriptive alt text for image '{image_id}'.")
            files.append({"id": image_id, "alt": alt.strip()})

        updated_files: list[dict[str, Any]] = []
        for start in range(0, len(files), 25):
            batch = files[start:start + 25]
            try:
                result = _mutate(
                    shop_domain, access_token, FILE_UPDATE, {"files": batch},
                    "fileUpdate", "Image alt update",
                )
            except ShopifyAdminAPIError as error:
                raise ShopifyAdminAPIError(f"{error} (earlier batches may have saved)") from error
            returned = result.get("files") or []
            if {f["id"] for f in returned} != {f["id"] for f in batch}:
                raise ShopifyAdminAPIError(
                    "Shopify did not return all requested image updates. Refetch before retrying."
                )
            updated_files.extend(returned)

        return {
            "success": True,
            "product_id": product_id,
            "fix_action": "set_product_image_alt",
            "files": updated_files,
            "verification_required": True,
            "message": (
                "Image alt text updated. Alt text is stored on the file, so any other "
                "product using the same image is affected too."
                if files
                else "All images already have alt text."
            ),
        }

    # =================================================================
    # Options / variants
    # =================================================================

    def rename_product_option(
        self,
        *,
        product_id: str,
        option_id: str,
        new_name: str,
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        product_id = _require(product_id, "Product ID is required.")
        option_id = _require(option_id, "Option ID is required.")
        new_name = _require(new_name, "New option name is required.")
        result = _mutate(
            shop_domain, access_token,
            """
            mutation RenameProductOption($productId: ID!, $option: OptionUpdateInput!) {
              productOptionUpdate(productId: $productId, option: $option) {
                product { id options { id name position } }
                userErrors { field message code }
              }
            }
            """,
            {"productId": product_id, "option": {"id": option_id, "name": new_name}},
            "productOptionUpdate", "Product option update",
        )
        product = result.get("product")
        if not product:
            raise ShopifyAdminAPIError("Shopify did not return the updated product.")
        return {
            "success": True,
            "product_id": product.get("id"),
            "options": product.get("options"),
            "fix_action": "rename_product_option",
            "message": "Product option renamed successfully.",
        }

    def _set_skus(
        self,
        *,
        action: str,
        product_id: str,
        variants: list[dict[str, Any]],
        shop_domain: str,
        access_token: str,
    ) -> dict[str, Any]:
        product_id = _require(product_id, "Product ID is required.")
        variants = _dict_list(variants, "variants")

        formatted: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_skus: set[str] = set()
        for v in variants:
            variant_id = _require_text(v.get("id"), "Variant ID is required for each variant.")
            sku = _require_text(v.get("sku"), f"SKU is required for variant '{variant_id}'.")
            if variant_id in seen_ids:
                raise ValueError(f"Duplicate variant ID: '{variant_id}'.")
            if sku.lower() in seen_skus:
                raise ValueError(f"Duplicate SKU within request: '{sku}'.")
            seen_ids.add(variant_id)
            seen_skus.add(sku.lower())
            formatted.append({"id": variant_id, "inventoryItem": {"sku": sku}})

        result = _mutate(
            shop_domain, access_token, VARIANTS_BULK_UPDATE,
            {"productId": product_id, "variants": formatted},
            "productVariantsBulkUpdate", "Variant update",
        )
        updated = result.get("productVariants") or []
        saved = {v.get("id"): ((v.get("inventoryItem") or {}).get("sku") or "") for v in updated}
        for item in formatted:
            if saved.get(item["id"]) != item["inventoryItem"]["sku"]:
                raise ShopifyAdminAPIError(
                    f"SKU for variant '{item['id']}' did not persist. Refetch before retrying."
                )
        return {
            "success": True,
            "product_id": product_id,
            "fix_action": action,
            "variants": updated,
            "verification_required": True,
            "message": "Variant SKUs updated successfully. Shopify does not enforce SKU uniqueness; check ERP/WMS conflicts.",
        }

    def generate_sku(
        self, *, product_id: str, variants: list[dict[str, Any]], shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        return self._set_skus(
            action="generate_sku", product_id=product_id, variants=variants,
            shop_domain=shop_domain, access_token=access_token,
        )

    def update_sku(
        self, *, product_id: str, variants: list[dict[str, Any]], shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        """Replace duplicate SKUs with merchant-approved unique values."""
        return self._set_skus(
            action="update_sku", product_id=product_id, variants=variants,
            shop_domain=shop_domain, access_token=access_token,
        )

    def suggest_sku(
        self, *, product_title: str, selected_options: list[dict[str, str]] | None = None
    ) -> dict[str, Any]:
        def slug(value: str, max_len: int) -> str:
            value = unicodedata.normalize("NFKD", value or "")
            value = value.encode("ascii", "ignore").decode("ascii").upper()
            return re.sub(r"[^A-Z0-9]+", "", value)[:max_len]

        title_part = slug(product_title, 6) or "ITEM"
        option_parts = [
            slug(o.get("value", ""), 4) for o in (selected_options or []) if o.get("value")
        ]
        option_parts = [p for p in option_parts if p]
        sku = "-".join([title_part, *option_parts]) if option_parts else title_part
        return {"suggested_sku": sku}

    def set_variant_price(
        self, *, product_id: str, variants: list[dict[str, Any]], shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        product_id = _require(product_id, "Product ID is required.")
        variants = _dict_list(variants, "variants")

        formatted = []
        seen_ids: set[str] = set()
        for variant in variants:
            variant_id = _require_text(variant.get("id"), "Variant ID is required for each variant.")
            if variant_id in seen_ids:
                raise ValueError(f"Duplicate variant ID: '{variant_id}'.")
            price = _parse_price(variant.get("price"), f"'{variant_id}'")
            seen_ids.add(variant_id)
            formatted.append({"id": variant_id, "price": format(price, "f")})

        result = _mutate(
            shop_domain, access_token,
            """
            mutation SetVariantPrice($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkUpdate(
                productId: $productId, variants: $variants, allowPartialUpdates: false
              ) {
                productVariants { id price }
                userErrors { field message code }
              }
            }
            """,
            {"productId": product_id, "variants": formatted},
            "productVariantsBulkUpdate", "Price update",
        )
        updated = result.get("productVariants") or []
        saved = {v.get("id"): v.get("price") for v in updated}
        for item in formatted:
            try:
                ok = Decimal(str(saved.get(item["id"]))) == Decimal(item["price"])
            except (InvalidOperation, ValueError):
                ok = False
            if not ok:
                raise ShopifyAdminAPIError(
                    f"Price for variant '{item['id']}' did not persist. Refetch before retrying."
                )
        return {
            "success": True,
            "product_id": product_id,
            "fix_action": "set_variant_price",
            "variants": updated,
            "message": "Variant prices updated successfully.",
        }

    # -----------------------------------------------------------------
    # Variant option values (targeted updates; never productSet)
    # -----------------------------------------------------------------

    def _fetch_variant_state(
        self, *, shop_domain: str, access_token: str, product_id: str
    ) -> dict[str, Any]:
        """Load product options and EVERY variant (fully paginated)."""
        product_id = _require_product_gid(product_id)
        product: dict[str, Any] | None = None
        variants: list[dict[str, Any]] = []
        cursor: str | None = None

        for _page in range(30):  
            data = _gql(
                shop_domain, access_token, PRODUCT_VARIANT_STATE,
                {"id": product_id, "cursor": cursor},
            )
            node = data.get("product")
            if not node:
                raise ShopifyAdminAPIError("Product not found.")
            product = product or node
            page = node.get("variants") or {}
            variants.extend(page.get("nodes") or [])
            info = page.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                break
            cursor = info.get("endCursor")
        else:
            raise ShopifyAdminAPIError("Product has too many variants to load safely.")

        return {
            "id": product["id"],
            "title": product.get("title"),
            "options": product.get("options") or [],
            "variants": variants,
        }

    def get_variant_options_state(
        self, *, shop_domain: str, access_token: str, product_id: str
    ) -> dict[str, Any]:
        """Read-only state for the options editor (all variants, with option IDs)."""
        state = self._fetch_variant_state(
            shop_domain=shop_domain, access_token=access_token, product_id=product_id
        )
        return {
            "product_id": state["id"],
            "title": state["title"],
            "options": [o.get("name") for o in state["options"]],
            "options_detail": [
                {"id": o.get("id"), "name": o.get("name"), "values": o.get("values") or []}
                for o in state["options"]
            ],
            "variants": [
                {
                    "id": v.get("id"),
                    "title": v.get("title"),
                    "sku": v.get("sku"),
                    "selected_options": [
                        {
                            "name": s.get("name"),
                            "value": s.get("value"),
                            "suggested_value": self.suggest_normalized_option_value(s.get("value")),
                        }
                        for s in v.get("selectedOptions") or []
                    ],
                }
                for v in state["variants"]
            ],
        }

    @staticmethod
    def suggest_normalized_option_value(value: str) -> str:
        cleaned = " ".join((value or "").strip().split())
        return cleaned.title() if cleaned else cleaned

    def fix_variant_options(
        self,
        *,
        product_id: str,
        variant_option_values: dict[str, dict[str, str]],
        shop_domain: str,
        access_token: str,
        merchant_approved: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """Change option values on EXISTING variants via targeted bulk updates.

        Replaces the old productSet flow, which could delete any variant missing
        from the submitted list. Here every variant keeps its identity, requested
        IDs/option names are validated, and duplicate combinations are rejected
        before anything is written.
        """
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required.")
        product_id = _require_product_gid(product_id)
        if not isinstance(variant_option_values, dict) or not variant_option_values:
            raise ValueError("variant_option_values must be a non-empty object.")
        if len(variant_option_values) > MAX_BULK:
            raise ValueError(f"At most {MAX_BULK} variants can be updated per request.")

        state = self._fetch_variant_state(
            shop_domain=shop_domain, access_token=access_token, product_id=product_id
        )
        option_names = [o.get("name") for o in state["options"] if o.get("name")]
        if not option_names:
            raise ValueError("Product has no options.")
        by_id = {v["id"]: v for v in state["variants"] if v.get("id")}

        requested_clean: dict[str, dict[str, str]] = {}
        for variant_id, requested in variant_option_values.items():
            if variant_id not in by_id:
                raise ValueError(f"Variant '{variant_id}' does not belong to this product.")
            if not isinstance(requested, dict) or not requested:
                raise ValueError(f"Provide option values for variant '{variant_id}'.")
            clean: dict[str, str] = {}
            for name, value in requested.items():
                if name not in option_names:
                    raise ValueError(f"Unknown option '{name}' for this product.")
                clean[name] = _require_text(
                    value, f"Option '{name}' for variant '{variant_id}' must not be blank."
                )
            requested_clean[variant_id] = clean


        target: dict[str, dict[str, str]] = {}
        for variant_id, variant in by_id.items():
            current = {
                s["name"]: s["value"] for s in variant.get("selectedOptions") or [] if s.get("name")
            }
            wanted = {**current, **requested_clean.get(variant_id, {})}
            missing = [n for n in option_names if not str(wanted.get(n) or "").strip()]
            if missing:
                raise ValueError(f"Variant '{variant_id}' is missing value(s) for: {missing}.")
            target[variant_id] = wanted

        seen: dict[tuple[str, ...], str] = {}
        for variant_id, wanted in target.items():
            combo = tuple(wanted[n].casefold() for n in option_names)
            if combo in seen:
                raise ValueError(
                    f"These changes would give variants '{seen[combo]}' and '{variant_id}' "
                    "identical option values."
                )
            seen[combo] = variant_id

        changed = [
            variant_id
            for variant_id in requested_clean
            if target[variant_id]
            != {s["name"]: s["value"] for s in by_id[variant_id].get("selectedOptions") or []}
        ]
        if not changed:
            raise ValueError("No option values changed.")

        formatted = [
            {
                "id": variant_id,
                "optionValues": [
                    {"optionName": n, "name": target[variant_id][n]} for n in option_names
                ],
            }
            for variant_id in changed
        ]
        result = _mutate(
            shop_domain, access_token, VARIANT_OPTIONS_UPDATE,
            {"productId": product_id, "variants": formatted},
            "productVariantsBulkUpdate", "Variant option update",
        )

        saved = {
            v.get("id"): {s["name"]: s["value"] for s in v.get("selectedOptions") or []}
            for v in result.get("productVariants") or []
        }
        for variant_id in changed:
            if saved.get(variant_id) != target[variant_id]:
                raise ShopifyAdminAPIError(
                    f"Option values for variant '{variant_id}' did not persist. Refetch before retrying."
                )

        return {
            "success": True,
            "product_id": product_id,
            "updated_variants": len(changed),
            "variants": result.get("productVariants"),
            "fix_action": "fix_variant_options",
            "verification_required": True,
            "message": f"Updated option values on {len(changed)} variant(s).",
        }

    def set_gtin(
        self,
        *,
        product_id: str,
        variant_id: str,
        gtin: str,
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        """Set the native variant barcode (the audit's GTIN source of truth)."""
        product_id = _require(product_id, "Product ID is required.")
        variant_id = _require(variant_id, "Variant ID is required.")
        gtin = _require(gtin, "GTIN is required.")
        if not _is_valid_gtin(gtin):
            raise ValueError(
                "GTIN must be 8, 12, 13 or 14 digits with a valid check digit."
            )

        result = _mutate(
            shop_domain, access_token, VARIANTS_BULK_UPDATE,
            {"productId": product_id, "variants": [{"id": variant_id, "barcode": gtin}]},
            "productVariantsBulkUpdate", "GTIN update",
        )
        updated = next(
            (v for v in (result.get("productVariants") or []) if v.get("id") == variant_id),
            None,
        )
        if not updated:
            raise ShopifyAdminAPIError("Shopify did not return the updated variant.")
        saved = updated.get("barcode")
        if str(saved or "").strip() != gtin:
            raise ShopifyAdminAPIError(
                f"GTIN update did not persist. Expected {gtin!r}, received {saved!r}."
            )
        return {
            "success": True,
            "product_id": product_id,
            "variant_id": variant_id,
            "fix_action": "set_gtin",
            "barcode": saved,
            "message": "Variant barcode (GTIN) updated successfully.",
        }

    # =================================================================
    # Store-wide: fulfillment
    # =================================================================

    def update_fulfillment_information(
        self,
        *,
        shop_domain: str,
        access_token: str,
        merchant_approved: bool = False,
        delivery_profile_id: str | None = None,
        delivery_profile_update: dict[str, Any] | None = None,
        pickup_settings: list[dict[str, Any]] | None = None,
        shipping_policy_body: str | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        """
        Merchant-approved fulfillment updates (delivery profile, pickup, shipping policy).
        The shipping-policy update replaces the whole policy body. Not atomic.
        """
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required.")
        _clean_shop(shop_domain, access_token)

        if (delivery_profile_id is None) != (delivery_profile_update is None):
            raise ValueError("Provide both delivery_profile_id and delivery_profile_update.")
        if delivery_profile_update is not None:
            if not isinstance(delivery_profile_update, dict) or not delivery_profile_update:
                raise ValueError("delivery_profile_update must be a non-empty object.")
            delivery_profile_id = _require_text(delivery_profile_id, "Delivery profile ID is required.")

        clean_pickups: list[dict[str, str]] = []
        if pickup_settings is not None:
            for settings in _dict_list(pickup_settings, "pickup_settings", max_items=50):
                clean_pickups.append({
                    "locationId": _require_text(settings.get("locationId"), "Pickup locationId is required."),
                    "pickupTime": _require_text(settings.get("pickupTime"), "Pickup pickupTime is required."),
                    "instructions": _require_text(
                        settings.get("instructions"),
                        "Nonblank pickup instructions are required for each location.",
                    ),
                })

        if shipping_policy_body is not None:
            shipping_policy_body = _require_text(
                shipping_policy_body, "Shipping policy body must not be blank."
            )

        if delivery_profile_update is None and not clean_pickups and shipping_policy_body is None:
            raise ValueError("Provide at least one fulfillment update.")

        completed: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []

        def step(operation: str, call: Callable[[], Any]) -> None:
            try:
                completed.append({"operation": operation, "success": True, "result": call()})
            except (ValueError, ShopifyAdminAPIError) as error:
                failures.append({"operation": operation, "success": False, "error": str(error)})

        if delivery_profile_update is not None:
            step(
                "deliveryProfileUpdate",
                lambda: _mutate(
                    shop_domain, access_token, DELIVERY_PROFILE_UPDATE,
                    {"id": delivery_profile_id, "profile": delivery_profile_update},
                    "deliveryProfileUpdate", "deliveryProfileUpdate",
                ),
            )

        for settings in clean_pickups:
            step(
                "locationLocalPickupEnable",
                lambda s=settings: _mutate(
                    shop_domain, access_token, LOCAL_PICKUP_ENABLE, {"settings": s},
                    "locationLocalPickupEnable", "locationLocalPickupEnable",
                ),
            )

        if shipping_policy_body is not None:
            step(
                "shopPolicyUpdate",
                lambda: self.update_policy(
                    shop_domain=shop_domain,
                    access_token=access_token,
                    policy_type="SHIPPING_POLICY",
                    body=shipping_policy_body,
                    merchant_approved=True,
                ),
            )

        successful, failed = len(completed), len(failures)
        return {
            "success": failed == 0,
            "partial_success": successful > 0 and failed > 0,
            "fix_action": "update_fulfillment_information",
            "total": successful + failed,
            "successful": successful,
            "failed": failed,
            "updates": completed + failures,
            "verification_required": successful > 0,
            "message": (
                "Fulfillment updates saved."
                if failed == 0
                else f"{successful} fulfillment operation(s) saved; {failed} failed. Refetch before retrying."
            ),
        }

    # =================================================================
    # Store-wide: normalization
    # =================================================================

    def _run_normalization(
        self,
        *,
        jobs: list[dict[str, Any]],
        action: str,
        shop_domain: str,
        access_token: str,
    ) -> dict[str, Any]:
        if not jobs:
            raise ValueError("At least one update is required.")

        completed: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for index, job in enumerate(jobs):
            try:
                result = _mutate(
                    shop_domain, access_token, job["query"], job["variables"],
                    job["operation"], job["operation"],
                )
                completed.append({
                    "index": index, "operation": job["operation"],
                    "success": True, "result": result,
                })
            except (ValueError, ShopifyAdminAPIError) as error:
                failures.append({
                    "index": index, "operation": job.get("operation"),
                    "success": False, "error": str(error),
                })

        successful, failed = len(completed), len(failures)
        return {
            "success": failed == 0,
            "partial_success": successful > 0 and failed > 0,
            "fix_action": action,
            "total": len(jobs),
            "successful": successful,
            "failed": failed,
            "results": completed + failures,
            "verification_required": successful > 0,
            "message": (
                "All normalization updates saved."
                if failed == 0
                else f"{successful} update(s) saved; {failed} failed. Refetch Shopify data before retrying."
            ),
        }

    @staticmethod
    def _validated_products(products: Any, key: str) -> list[tuple[str, list[dict[str, Any]]]]:
        """Validate every product/nested payload before the first write."""
        products = _dict_list(products, "changes")
        out: list[tuple[str, list[dict[str, Any]]]] = []
        for product in products:
            product_id = str(product.get("product_id") or "").strip()
            if not _PRODUCT_GID_RE.fullmatch(product_id):
                raise ValueError("Every change needs a valid Shopify Product GID in product_id.")
            items = product.get(key)
            if (
                not isinstance(items, list)
                or not items
                or not all(isinstance(i, dict) for i in items)
            ):
                raise ValueError(f"'{key}' must be a non-empty list of objects for '{product_id}'.")
            out.append((product_id, items))
        return out

    def normalize_option_structure(
        self, *, products: list[dict[str, Any]], shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        """Rename existing product options using explicit ID/name mappings."""
        mutation = """
        mutation NormalizeOption($productId: ID!, $option: OptionUpdateInput!) {
          productOptionUpdate(productId: $productId, option: $option) {
            product { id }
            userErrors { field message }
          }
        }
        """
        jobs = []
        seen: set[tuple[str, str]] = set()
        for product_id, options in self._validated_products(products, "options"):
            for option in options:
                option_id = str(option.get("id") or "").strip()
                name = option.get("name")
                if not _OPTION_GID_RE.fullmatch(option_id):
                    raise ValueError("Each option needs its existing ProductOption GID.")
                name = _require_text(name, "Each option needs a new name.")
                identity = (product_id, option_id)
                if identity in seen:
                    raise ValueError(f"Duplicate option update: {identity}.")
                seen.add(identity)
                jobs.append({
                    "query": mutation,
                    "operation": "productOptionUpdate",
                    "variables": {"productId": product_id, "option": {"id": option_id, "name": name}},
                })
        return self._run_normalization(
            jobs=jobs, action="normalize_option_structure",
            shop_domain=shop_domain, access_token=access_token,
        )

    def _normalize_product_metafields(
        self,
        *,
        products: list[dict[str, Any]],
        action: str,
        shop_domain: str,
        access_token: str,
    ) -> dict[str, Any]:
        """Write explicit canonical metafield values without changing namespaces."""
        inputs = []
        seen: set[tuple[str, str, str]] = set()
        for product_id, metafields in self._validated_products(products, "metafields"):
            for metafield in metafields:
                entry: dict[str, Any] = {"ownerId": product_id}
                for field in ("namespace", "key", "type"):
                    entry[field] = _require_text(metafield.get(field), f"Metafield {field} is required.")
                value = metafield.get("value")
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("Metafield value must be a nonblank serialized string.")
                entry["value"] = value
                identity = (product_id, entry["namespace"], entry["key"])
                if identity in seen:
                    raise ValueError(f"Duplicate metafield update: {identity}.")
                seen.add(identity)
                inputs.append(entry)

        jobs = [
            {
                "query": METAFIELDS_SET,
                "operation": "metafieldsSet",
                "variables": {"metafields": inputs[start:start + 25]},
            }
            for start in range(0, len(inputs), 25)
        ]
        return self._run_normalization(
            jobs=jobs, action=action, shop_domain=shop_domain, access_token=access_token
        )

    def normalize_metafield_structure(
        self, *, products: list[dict[str, Any]], shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        """Set missing keys using approved, product-specific values."""
        return self._normalize_product_metafields(
            products=products, action="normalize_metafield_structure",
            shop_domain=shop_domain, access_token=access_token,
        )

    def normalize_attribute_formats(
        self, *, products: list[dict[str, Any]], shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        """Save supplied canonical formats; does not migrate definitions."""
        return self._normalize_product_metafields(
            products=products, action="normalize_attribute_formats",
            shop_domain=shop_domain, access_token=access_token,
        )

    def normalize_attribute_units(
        self, *, products: list[dict[str, Any]], shop_domain: str, access_token: str, **_: Any
    ) -> dict[str, Any]:
        """Save supplied, correctly converted measurement values."""
        return self._normalize_product_metafields(
            products=products, action="normalize_attribute_units",
            shop_domain=shop_domain, access_token=access_token,
        )