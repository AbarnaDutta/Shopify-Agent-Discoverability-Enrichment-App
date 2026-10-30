# app/services/fix_engine.py

from __future__ import annotations



import itertools

import re

import unicodedata

from decimal import Decimal, InvalidOperation

from typing import Any, Callable

from urllib.parse import urlparse



from app.services.issue_registry import get_issue_definition

from app.services.shopify_admin_fetcher import (

    ShopifyAdminAPIError,

    _graphql_request,

    fetch_product_variant_state,

)



API_VERSION = "2026-07"



_SHOP_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.myshopify\.com")

_PRODUCT_GID_RE = re.compile(r"gid://shopify/Product/[0-9]+")

_SHOP_GID_RE = re.compile(r"gid://shopify/Shop/[0-9]+")

_PAGE_GID_RE = re.compile(r"gid://shopify/Page/[0-9]+")



POLICY_TYPES = {"REFUND_POLICY", "SHIPPING_POLICY", "CONTACT_INFORMATION", "PRIVACY_POLICY", "TERMS_OF_SERVICE", "LEGAL_NOTICE"}





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

    if response.get("errors"):

        raise ShopifyAdminAPIError(f"Shopify GraphQL error: {response['errors']}")

    return response.get("data") or {}





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

  productVariantsBulkUpdate(productId: $productId, variants: $variants) {

    productVariants { id barcode price inventoryItem { id sku } }

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

from app.services.shopify_admin_fetcher import fetch_product_variant_state




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

            "update_fulfillment_information": lambda changes, **kw: self._apply_each(

                self.update_fulfillment_information,

                "update_fulfillment_information",

                changes,

                **kw,

            ),

            "update_policy": lambda changes, **kw: self._apply_each(

                self.update_policy, "update_policy", changes, **kw

            ),

            "update_store_contact": lambda changes, **kw: self._apply_each(

                self.update_store_contact, "update_store_contact", changes, **kw

            ),

            "update_brand_information": lambda changes, **kw: self._apply_each(

                self.update_brand_information,

                "update_brand_information",

                changes,

                **kw,

            ),

            "update_faq_guidance": lambda changes, **kw: self._apply_each(
                self.update_faq_guidance,
                "update_faq_guidance",
                changes,
                **kw,
            ),
            "create_faq": lambda changes, **kw: self._apply_each(
                self.update_faq_guidance,
                "create_faq",
                changes,
                **kw,
            ),

            "configure_store_guardrail": lambda changes, **kw: self._apply_each(

                self.configure_store_guardrail,

                "configure_store_guardrail",

                changes,

                **kw,

            ),

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

        **_: Any,

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



        if not isinstance(changes, list) or not changes:
            raise ValueError(
                "changes must be a non-empty list. Provide the explicit, "
                "merchant-approved changes required by this fix."
            )
        if not all(isinstance(change, dict) for change in changes):
            raise ValueError("Every item in changes must be a JSON object.")
        if len(changes) > 250:
            raise ValueError("Too many changes in one request (max 250).")

        result = handler(
            changes=changes,
            shop_domain=shop_domain,
            access_token=access_token,
        )
        if not isinstance(result, dict):
            raise ShopifyAdminAPIError("Store-wide fix handler returned an invalid result.")

        return {

            **result,

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



        if fix_action == "set_metafield":

            attributes = kwargs.get("attributes")

            if not attributes:

                raise ValueError("At least one metafield attribute is required.")

            if not isinstance(attributes, list):

                raise ValueError("Metafield attributes must be a list.")



        if fix_action in {"generate_sku", "update_sku"}:

            variants = kwargs.get("variants")

            if not variants:

                raise ValueError("At least one variant is required to set SKUs.")

            if not isinstance(variants, list):

                raise ValueError("Variants must be provided as a list.")



        return handler(product_id=product_id, **kwargs)



    def _apply_each(

        self,

        fn: Callable[..., dict[str, Any]],

        action: str,

        changes: list[dict[str, Any]],

        **kw: Any,

    ) -> dict[str, Any]:

        """Run a single-item store handler once per change (not atomic)."""

        results: list[dict[str, Any]] = []

        for index, change in enumerate(changes):

            try:

                results.append(fn(**{**change, **kw}))

            except (ValueError, ShopifyAdminAPIError) as error:

                raise ShopifyAdminAPIError(

                    f"{action}: change {index + 1} failed: {error}. "

                    f"{len(results)} earlier change(s) were saved and not rolled back."

                ) from error

        return {

            "success": True,

            "fix_action": action,

            "results": results,

            "verification_required": True,

            "message": "Saved. Refetch store context and rerun the check.",

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

        product_id = str(product_id or "").strip()

        product_type = _require(product_type, "Product type is required.")

        if not _PRODUCT_GID_RE.fullmatch(product_id):

            raise ValueError("A valid Shopify Product GID is required.")

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

    # Product-level: metafields

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

        if not attributes:

            raise ValueError("At least one metafield attribute is required.")

        if len(attributes) > 25:

            raise ValueError("Shopify allows at most 25 metafields per request.")



        metafields = []

        for attribute in attributes:

            key = _require(attribute.get("key"), "Metafield key is required.")

            mtype = _require(attribute.get("type"), f"Metafield type is required for '{key}'.")

            value = attribute.get("value")

            if value is None or not str(value).strip():

                raise ValueError(f"Metafield value is required for '{key}'.")

            metafields.append(

                {

                    "ownerId": product_id,

                    "namespace": str(attribute.get("namespace") or "details").strip(),

                    "key": key,

                    "type": mtype,

                    "value": str(value).strip(),

                }

            )



        result = _mutate(

            shop_domain, access_token, METAFIELDS_SET,

            {"metafields": metafields}, "metafieldsSet", "Shopify metafield update",

        )

        updated = result.get("metafields") or []

        if not updated:

            raise ShopifyAdminAPIError("Shopify did not return the updated metafields.")

        return {

            "success": True,

            "product_id": product_id,

            "fix_action": "set_metafield",

            "metafields": updated,

            "message": "Product metafields updated successfully.",

        }



    def set_mpn(

        self, *, product_id: str = "", variant_id: str, mpn: str, shop_domain: str, access_token: str, **_: Any

    ) -> dict[str, Any]:

        """Set MPN for a variant (metafield identifiers.mpn)."""

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

            "message": "Variant MPN updated successfully.",

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

                "a warning or enforce restrictions. Refetch shop.guardrailDisclosure "

                "and rerun the guardrail check."

            ),

        }



    # =================================================================

    # Store-level: policies, contact, brand/About page

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

            raise ValueError(

                "policy_type must be REFUND_POLICY, SHIPPING_POLICY, CONTACT_INFORMATION, PRIVACY_POLICY, TERMS_OF_SERVICE or LEGAL_NOTICE."

            )

        if not isinstance(body, str) or not body.strip():

            raise ValueError("Provide the complete approved policy body.")



        result = _mutate(

            shop_domain, access_token, SHOP_POLICY_UPDATE,

            {"policy": {"type": policy_type, "body": body.strip()}},

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



    def update_faq_guidance(
        self,
        *,
        shop_domain: str,
        access_token: str,
        page_id: str | None = None,
        body: str,
        merchant_approved: bool = False,
        title: str | None = None,
        publish: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """Update an existing FAQ/help page using merchant-approved content."""
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required before updating FAQ/help content.")

        page_id = str(page_id or "").strip()
        if page_id and not _PAGE_GID_RE.fullmatch(page_id):
            raise ValueError("page_id must be a valid Shopify Page GID when supplied.")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("Provide the complete merchant-approved FAQ/help page body.")

        page_title = _require(title or "Frequently Asked Questions", "A page title is required.")
        if page_id:
            page_input: dict[str, Any] = {"body": body.strip()}
            if title is not None:
                page_input["title"] = page_title
            if publish is True:
                page_input["isPublished"] = True
            result = _mutate(
                shop_domain, access_token,
                """
                mutation UpdateFaqGuidance($id: ID!, $page: PageUpdateInput!) {
                  pageUpdate(id: $id, page: $page) {
                    page { id title handle body isPublished }
                    userErrors { field message }
                  }
                }
                """,
                {"id": page_id, "page": page_input},
                "pageUpdate", "FAQ/help page update",
            )
            page = result.get("page")
            operation_message = "FAQ/help page updated."
        else:
            page_input = {"title": page_title, "body": body.strip(), "isPublished": bool(publish)}
            result = _mutate(
                shop_domain, access_token,
                """
                mutation CreateFaqGuidance($page: PageCreateInput!) {
                  pageCreate(page: $page) {
                    page { id title handle body isPublished }
                    userErrors { field message }
                  }
                }
                """,
                {"page": page_input},
                "pageCreate", "FAQ/help page creation",
            )
            page = result.get("page")
            operation_message = "FAQ/help page created."
        if not page:
            raise ShopifyAdminAPIError("Shopify did not return the FAQ/help page.")

        return {
            "success": True,
            "fix_action": "update_faq_guidance",
            "page": page,
            "verification_required": True,
            "message": f"{operation_message} Refetch its title/body and rerun the check to verify that the guidance issue is resolved.",
        }

    def update_brand_information(
        self,
        *,
        shop_domain: str,
        access_token: str,
        page_id: str | None = None,
        body: str,
        merchant_approved: bool = False,
        title: str | None = None,
        publish: bool = False,
        **_: Any,
    ) -> dict[str, Any]:
        """Update a selected About page or create one when page_id is omitted."""
        if merchant_approved is not True:
            raise ValueError("Merchant approval is required.")
        page_id = str(page_id or "").strip()
        if page_id and not _PAGE_GID_RE.fullmatch(page_id):
            raise ValueError("page_id must be a valid Shopify Page GID when supplied.")
        if not isinstance(body, str) or not body.strip():
            raise ValueError("Provide the complete approved page body.")

        page_title = _require(title or "About Our Store", "A page title is required.")
        if page_id:
            page_input: dict[str, Any] = {"body": body.strip()}
            if title is not None:
                page_input["title"] = page_title
            if publish is True:
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
            message = "About page updated."
        else:
            result = _mutate(
                shop_domain, access_token,
                """
                mutation CreateAbout($page: PageCreateInput!) {
                  pageCreate(page: $page) {
                    page { id title handle body isPublished }
                    userErrors { field message }
                  }
                }
                """,
                {"page": {"title": page_title, "body": body.strip(), "isPublished": bool(publish)}},
                "pageCreate", "About page creation",
            )
            page = result.get("page")
            message = "About page created."
        if not page:
            raise ShopifyAdminAPIError("Shopify did not return the page.")
        return {
            "success": True,
            "fix_action": "update_brand_information",
            "page": page,
            "verification_required": True,
            "message": f"{message} Refetch the page and rerun the check to verify the result.",
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

        product_id = str(product_id or "").strip()

        if not _PRODUCT_GID_RE.fullmatch(product_id):

            raise ValueError("A Shopify Product GID is required.")

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

        product: dict[str, Any],

        image_alts: dict[str, str],

        shop_domain: str,

        access_token: str,

        **_: Any,

    ) -> dict[str, Any]:

        if not product.get("id"):

            raise ValueError("Product ID is required.")

        if "images" not in product:

            raise ValueError("Image data is unavailable; refetch the product.")

        images = product.get("images") or []

        if not images:

            raise ValueError("Product has no images. Add an image first.")



        files: list[dict[str, str]] = []

        seen_ids: set[str] = set()

        for image in images:

            if (image.get("alt") or "").strip():

                continue  

            image_id = image.get("id")

            if not image_id or not image_id.startswith("gid://shopify/MediaImage/"):

                raise ValueError("An image is missing its MediaImage ID; refetch the product.")

            alt = (image_alts or {}).get(image_id)

            if not isinstance(alt, str) or not alt.strip():

                raise ValueError(f"Provide descriptive alt text for image '{image_id}'.")

            if image_id not in seen_ids:

                files.append({"id": image_id, "alt": alt.strip()})

                seen_ids.add(image_id)



        mutation = """

        mutation SetImageAlts($files: [FileUpdateInput!]!) {

          fileUpdate(files: $files) {

            files { id alt fileStatus }

            userErrors { field message }

          }

        }

        """

        updated_files: list[dict[str, Any]] = []

        for start in range(0, len(files), 25):

            batch = files[start:start + 25]

            try:

                result = _mutate(

                    shop_domain, access_token, mutation, {"files": batch},

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

            "product_id": product["id"],

            "fix_action": "set_product_image_alt",

            "files": updated_files,

            "verification_required": True,

            "message": (

                "Missing image alt text updated."

                if files

                else "All collected images already have alt text."

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

        if not variants:

            raise ValueError("At least one variant is required to set SKU.")



        formatted: list[dict[str, Any]] = []

        seen_ids: set[str] = set()

        seen_skus: set[str] = set()

        for v in variants:

            variant_id = _require(v.get("id"), "Variant ID is required for each variant.")

            sku = _require(v.get("sku"), f"SKU is required for variant '{variant_id}'.")

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

        if not updated:

            raise ShopifyAdminAPIError("Shopify did not return the updated variants.")

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

        if not variants:

            raise ValueError("At least one variant is required.")

        if len(variants) > 250:

            raise ValueError("Provide at most 250 variants per request.")



        formatted = []

        seen_ids: set[str] = set()

        for variant in variants:

            variant_id = _require(variant.get("id"), "Variant ID is required for each variant.")

            if variant_id in seen_ids:

                raise ValueError(f"Duplicate variant ID: '{variant_id}'.")

            raw_price = variant.get("price")

            if raw_price is None or isinstance(raw_price, bool):

                raise ValueError(f"A price is required for '{variant_id}'.")

            try:

                price = Decimal(str(raw_price).strip())

            except (InvalidOperation, ValueError):

                raise ValueError(f"Invalid price for variant '{variant_id}'.") from None

            if not price.is_finite() or price < 0:

                raise ValueError(f"Price must be finite and nonnegative for '{variant_id}'.")

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

        if not updated:

            raise ShopifyAdminAPIError("Shopify did not return the updated variants.")

        return {

            "success": True,

            "product_id": product_id,

            "fix_action": "set_variant_price",

            "variants": updated,

            "message": "Variant prices updated successfully.",

        }



    def build_variant_options_input(

        self,

        *,

        shop_domain: str,

        access_token: str,

        product_id: str,

        variant_option_values: dict[str, dict[str, str]] | None = None,

    ) -> dict[str, Any]:

        if not product_id:

            raise ValueError("Product ID is required.")

        variant_option_values = variant_option_values or {}

        if not variant_option_values:

            raise ValueError("At least one variant's option values are required.")



        product = fetch_product_variant_state(

            shop_domain=shop_domain,

            access_token=access_token,

            api_version=API_VERSION,

            product_id=product_id,

        )



        requested_by_option: dict[str, list[str]] = {}

        for requested in variant_option_values.values():

            for option_name, new_value in (requested or {}).items():

                if not option_name or new_value is None:

                    continue

                value_str = str(new_value).strip()

                if value_str and value_str not in requested_by_option.setdefault(option_name, []):

                    requested_by_option[option_name].append(value_str)



        product_options: list[dict[str, Any]] = []

        for option in product.get("options") or []:

            option_name = option.get("name")

            if not option_name:

                continue

            ordered: list[str] = []

            for v in option.get("values") or []:

                v = str(v).strip() if v else ""

                if v and v not in ordered:

                    ordered.append(v)

            for v in requested_by_option.get(option_name, []):

                if v not in ordered:

                    ordered.append(v)

            if not ordered:

                continue

            product_options.append(

                {

                    "id": option.get("id"),

                    "name": option_name,

                    "position": option.get("position"),

                    "values": [{"name": v} for v in ordered],

                }

            )

        if not product_options:

            raise ValueError("Product has no valid options.")


        variants_input: list[dict[str, Any]] = []

        for edge in (product.get("variants") or {}).get("edges", []):

            variant = edge.get("node") or {}

            variant_id = variant.get("id")

            if not variant_id:

                continue

            requested = variant_option_values.get(variant_id, {}) or {}

            option_values: list[dict[str, str]] = []

            for selected in variant.get("selectedOptions") or []:

                option_name = selected.get("name")

                if not option_name:

                    continue

                new_value = requested.get(option_name, selected.get("value"))

                if new_value is None or not str(new_value).strip():

                    raise ValueError(

                        f"Missing option value for variant '{variant_id}', option '{option_name}'."

                    )

                option_values.append({"optionName": option_name, "name": str(new_value).strip()})

            if not option_values:

                raise ValueError(f"Variant '{variant_id}' has no option values.")

            variants_input.append({"id": variant_id, "optionValues": option_values})



        if not variants_input:

            raise ValueError("Product has no valid variants.")



        return {"id": product_id, "productOptions": product_options, "variants": variants_input}



    def build_variant_matrix_input(

        self,

        *,

        shop_domain: str,

        access_token: str,

        product_id: str,

        options: list[dict[str, Any]],

        default_price: str | None = None,

    ) -> dict[str, Any]:

        if not options:

            raise ValueError("At least one option with values is required.")

        for option in options:

            if not option.get("name") or not str(option.get("name")).strip():

                raise ValueError("Every option needs a name.")

            if not option.get("values"):

                raise ValueError(f"Option '{option.get('name')}' needs at least one value.")



        combo_count = 1

        for option in options:

            combo_count *= len(option["values"])

        if combo_count > 100:

            raise ValueError(

                f"This would create {combo_count} variants, which exceeds the "

                "100-variant safety limit for this tool."

            )



        product = fetch_product_variant_state(

            shop_domain=shop_domain,

            access_token=access_token,

            api_version=API_VERSION,

            product_id=product_id,

        )

        existing = (product.get("variants") or {}).get("edges", [])

        current_price = existing[0].get("node", {}).get("price") if existing else None

        price = str(default_price or current_price or "0.00")



        options_input = [

            {

                "name": option["name"].strip(),

                "position": index + 1,

                "values": [{"name": v} for v in option["values"]],

            }

            for index, option in enumerate(options)

        ]

        option_names = [option["name"].strip() for option in options]

        value_lists = [option["values"] for option in options]

        title = product.get("title") or ""



        variants_input = []

        for combo in itertools.product(*value_lists):

            selected = [{"optionName": n, "name": v} for n, v in zip(option_names, combo)]

            sku = self.suggest_sku(

                product_title=title,

                selected_options=[{"value": v} for v in combo],

            )["suggested_sku"]

            variants_input.append({"optionValues": selected, "price": price, "sku": sku})



        return {"title": title, "options": options_input, "variants": variants_input}



    @staticmethod

    def suggest_normalized_option_value(value: str) -> str:

        cleaned = " ".join((value or "").strip().split())

        return cleaned.title() if cleaned else cleaned


    def fix_variant_options(

        self,

        *,

        product_id: str,

        product_set_input: dict[str, Any],

        shop_domain: str,

        access_token: str,

        synchronous: bool = True,

        **_: Any,

    ) -> dict[str, Any]:

        """Normalize options/variants via productSet. Product ID is forced from product_id."""

        product_id = _require(product_id, "Product ID is required.")

        if not isinstance(product_set_input, dict):

            raise ValueError("product_set_input must be a dict.")



        result = _mutate(

            shop_domain, access_token,

            """

            mutation FixVariantOptions($input: ProductSetInput!, $synchronous: Boolean!) {

              productSet(input: $input, synchronous: $synchronous) {

                product {

                  id

                  options { id name }

                  variants(first: 100) { nodes { id title } }

                }

                userErrors { field message }

              }

            }

            """,

            {"input": {**product_set_input, "id": product_id}, "synchronous": synchronous},

            "productSet", "Shopify productSet (variant options)",

        )

        product = result.get("product")

        if not product:

            raise ShopifyAdminAPIError("Shopify did not return the updated product.")

        return {

            "success": True,

            "product_id": product.get("id"),

            "options": product.get("options"),

            "variants": product.get("variants"),

            "fix_action": "fix_variant_options",

            "message": "Product options and variants normalized successfully.",

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

            "message": "Variant GTIN updated successfully.",

        }



    # =================================================================

    # Store-wide: fulfillment

    # =================================================================



    def update_fulfillment_information(

        self,

        *,

        shop_domain: str,

        access_token: str,

        delivery_profile_id: str | None = None,

        delivery_profile_update: dict[str, Any] | None = None,

        pickup_settings: list[dict[str, Any]] | None = None,

        shipping_policy_body: str | None = None,

        **_: Any,

    ) -> dict[str, Any]:

        """

        Merchant-approved fulfillment updates (delivery profile, pickup, shipping policy).

        Shipping-policy update replaces the whole policy body. Not atomic.

        """

        _clean_shop(shop_domain, access_token)



        if (delivery_profile_id is None) != (delivery_profile_update is None):

            raise ValueError("Provide both delivery_profile_id and delivery_profile_update.")

        if delivery_profile_update is not None:

            if not str(delivery_profile_id or "").strip():

                raise ValueError("Delivery profile ID is required.")

            if not delivery_profile_update:

                raise ValueError("Delivery profile update cannot be empty.")



        for settings in pickup_settings or []:

            if not settings.get("locationId"):

                raise ValueError("Pickup locationId is required.")

            if not settings.get("pickupTime"):

                raise ValueError("Pickup pickupTime is required.")

            instructions = settings.get("instructions")

            if not isinstance(instructions, str) or not instructions.strip():

                raise ValueError("Nonblank pickup instructions are required for each location.")



        if shipping_policy_body is not None:

            if not isinstance(shipping_policy_body, str) or not shipping_policy_body.strip():

                raise ValueError("Shipping policy body must not be blank.")



        if delivery_profile_update is None and not pickup_settings and shipping_policy_body is None:

            raise ValueError("Provide at least one fulfillment update.")



        completed: list[dict[str, Any]] = []



        def run(mutation: str, variables: dict[str, Any], operation: str) -> None:

            try:

                result = _mutate(

                    shop_domain, access_token, mutation, variables, operation, operation

                )

            except ShopifyAdminAPIError as error:

                prior = [c["operation"] for c in completed]

                raise ShopifyAdminAPIError(

                    f"{error}. Previously completed operations: {prior}. "

                    "Refetch settings before retrying; changes are not rolled back."

                ) from error

            completed.append({"operation": operation, "result": result})



        if delivery_profile_update is not None:

            run(

                """

                mutation UpdateFulfillmentProfile($id: ID!, $profile: DeliveryProfileInput!) {

                  deliveryProfileUpdate(id: $id, profile: $profile) {

                    profile { id name }

                    userErrors { field message }

                  }

                }

                """,

                {"id": delivery_profile_id.strip(), "profile": delivery_profile_update},

                "deliveryProfileUpdate",

            )



        for settings in pickup_settings or []:

            run(

                """

                mutation UpdatePickup($settings: DeliveryLocationLocalPickupEnableInput!) {

                  locationLocalPickupEnable(localPickupSettings: $settings) {

                    localPickupSettings { instructions pickupTime }

                    userErrors { field message }

                  }

                }

                """,

                {"settings": {**settings, "instructions": settings["instructions"].strip()}},

                "locationLocalPickupEnable",

            )



        if shipping_policy_body is not None:

            run(

                SHOP_POLICY_UPDATE,

                {"policy": {"type": "SHIPPING_POLICY", "body": shipping_policy_body.strip()}},

                "shopPolicyUpdate",

            )



        return {

            "success": True,

            "fix_action": "update_fulfillment_information",

            "updates": completed,

            "verification_required": True,

            "message": (

                "Fulfillment updates saved. Refetch store context, restore "

                "catalog_flags, and rerun check_fulfillment_context."

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



        completed = []

        for index, job in enumerate(jobs):

            try:

                completed.append(

                    _mutate(

                        shop_domain, access_token, job["query"], job["variables"],

                        job["operation"], job["operation"],

                    )

                )

            except ShopifyAdminAPIError as error:

                raise ShopifyAdminAPIError(

                    f"{action}: update {index + 1} failed: {error}. "

                    f"{len(completed)} earlier updates completed and were not "

                    "rolled back. Refetch before retrying."

                ) from error



        return {

            "success": True,

            "fix_action": action,

            "updates": completed,

            "verification_required": True,

            "message": "Updates saved. Refetch products and rerun consistency checks.",

        }



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

        seen = set()

        for product in products:

            product_id = str(product.get("product_id") or "").strip()

            if not product_id:

                raise ValueError("product_id is required.")

            for option in product.get("options") or []:

                option_id = str(option.get("id") or "").strip()

                name = str(option.get("name") or "").strip()

                if not option_id or not name:

                    raise ValueError("Each option needs its existing ID and new name.")

                identity = (product_id, option_id)

                if identity in seen:

                    raise ValueError(f"Duplicate option update: {identity}.")

                seen.add(identity)

                jobs.append(

                    {

                        "query": mutation,

                        "operation": "productOptionUpdate",

                        "variables": {"productId": product_id, "option": {"id": option_id, "name": name}},

                    }

                )

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

        seen = set()

        for product in products:

            product_id = str(product.get("product_id") or "").strip()

            if not product_id:

                raise ValueError("product_id is required.")

            for metafield in product.get("metafields") or []:

                entry: dict[str, Any] = {"ownerId": product_id}

                for field in ("namespace", "key", "type"):

                    value = metafield.get(field)

                    if not isinstance(value, str) or not value.strip():

                        raise ValueError(f"Metafield {field} is required.")

                    entry[field] = value.strip()

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
