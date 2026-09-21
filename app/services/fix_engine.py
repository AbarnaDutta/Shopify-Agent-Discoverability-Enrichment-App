from __future__ import annotations

from typing import Any, Callable
import re
import unicodedata
import requests

from app.services.issue_registry import get_issue_definition


class FixEngine:
    """
    Central dispatcher for executing approved fixes.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {
        "update_product_handle": self.update_product_handle,
        "set_metafield": self.set_metafield,
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
            raise ValueError(
                f"Unknown issue type '{issue_type}' "
                f"for'{check_id}'"
            )
        fix_mode = definition.get("fix_mode")
        fix_action = definition.get("fix_action")
        if fix_mode == "unsupported":
            raise ValueError(
                f"Issue '{issue_type}' is not automatically fixable."
            )

        if not fix_action:
            raise ValueError(
                f"No fix_action configured for issue '{issue_type}'."
            )

        handler = self._handlers.get(fix_action)

        if handler is None:
            raise ValueError(
                f"No handler registered for fix_action '{fix_action}'."
            )

        if fix_action == "set_metafield":
            attributes = kwargs.get("attributes")

            if not attributes:
                raise ValueError(
                    "At least one metafield attribute is required."
                )

            if not isinstance(attributes, list):
                raise ValueError(
                    "Metafield attributes must be a list."
                )

        return handler(
            product_id=product_id,
            **kwargs,
        )

    def update_product_handle(
        self,
        *,
        product_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Update a Shopify product handle after merchant approval.
        """

        handle = kwargs.get("handle")
        shop_domain = kwargs.get("shop_domain")
        access_token = kwargs.get("access_token")

        if not handle or not str(handle).strip():
            raise ValueError("Product handle is required.")

        if not shop_domain or not str(shop_domain).strip():
            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():
            raise ValueError("Shopify access token is required.")

        handle = str(handle).strip()
        shop_domain = str(shop_domain).strip()
        access_token = str(access_token).strip()

        api_version = "2026-07"

        graphql_url = (
            f"https://{shop_domain}/admin/api/"
            f"{api_version}/graphql.json"
        )

        mutation = """
        mutation productUpdate($input: ProductInput!) {
        productUpdate(input: $input) {
            product {
            id
            handle
            }
            userErrors {
            field
            message
            }
        }
        }
        """

        variables = {
            "input": {
                "id": product_id,
                "handle": handle,
            }
        }

        response = requests.post(
            graphql_url,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": access_token,
            },
            json={
                "query": mutation,
                "variables": variables,
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):
            raise ValueError(
                f"Shopify GraphQL error: {data['errors']}"
            )

        result = (
            data.get("data", {})
            .get("productUpdate", {})
        )

        user_errors = result.get("userErrors") or []

        if user_errors:
            messages = "; ".join(
                error.get("message", "Unknown Shopify error")
                for error in user_errors
            )

            raise ValueError(
                f"Shopify product update failed: {messages}"
            )

        product = result.get("product")

        if not product:
            raise ValueError(
                "Shopify did not return the updated product."
            )

        return {
            "success": True,
            "product_id": product.get("id"),
            "handle": product.get("handle"),
            "fix_action": "update_product_handle",
            "message": "Product handle updated successfully.",
        }
    
    def suggest_product_handle(
                self,
                *,
                product_title: str,
            ) -> dict[str, Any]:
    
                value = unicodedata.normalize("NFKD", product_title)
    
                value = value.encode(
                    "ascii",
                    "ignore",
                ).decode("ascii")
    
                value = value.lower()
    
                value = re.sub(
                    r"[^a-z0-9]+",
                    "-",
                    value,
                )
    
                value = value.strip("-")
    
                if not value:
                    raise ValueError(
                        "Unable to generate a valid product handle from product title."
                    )
    
                return {
                    "suggested_handle": value,
                }

    def set_metafield(
        self,
        *,
        product_id: str,
        attributes: list[dict[str, str]],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        """
        Set multiple Shopify product metafields dynamically.
        """

        if not product_id:
            raise ValueError("Product ID is required.")

        if not attributes:
            raise ValueError("At least one metafield attribute is required.")

        if not shop_domain or not shop_domain.strip():
            raise ValueError("Shop domain is required.")

        if not access_token or not access_token.strip():
            raise ValueError("Shopify access token is required.")

        metafields = []

        for attribute in attributes:
            key = attribute.get("key")
            metafield_type = attribute.get("type")
            value = attribute.get("value")

            if not key or not key.strip():
                raise ValueError("Metafield key is required.")

            if not metafield_type or not metafield_type.strip():
                raise ValueError(
                    f"Metafield type is required for '{key}'."
                )

            if value is None or not str(value).strip():
                raise ValueError(
                    f"Metafield value is required for '{key}'."
                )

            metafields.append(
                {
                    "ownerId": product_id,
                    "namespace": "details",
                    "key": key.strip(),
                    "type": metafield_type.strip(),
                    "value": str(value).strip(),
                }
            )

        api_version = "2026-07"

        graphql_url = (
            f"https://{shop_domain.strip()}/admin/api/"
            f"{api_version}/graphql.json"
        )

        mutation = """
        mutation MetafieldsSet($metafields: [MetafieldsSetInput!]!) {
          metafieldsSet(metafields: $metafields) {
            metafields {
              id
              namespace
              key
              type
              value
            }
            userErrors {
              field
              message
              code
            }
          }
        }
        """

        response = requests.post(
            graphql_url,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": access_token.strip(),
            },
            json={
                "query": mutation,
                "variables": {
                    "metafields": metafields,
                },
            },
            timeout=30,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):
            raise ValueError(
                f"Shopify GraphQL error: {data['errors']}"
            )

        result = (
            data.get("data", {})
            .get("metafieldsSet", {})
        )

        user_errors = result.get("userErrors") or []

        if user_errors:
            messages = "; ".join(
                error.get("message", "Unknown Shopify error")
                for error in user_errors
            )

            raise ValueError(
                f"Shopify metafield update failed: {messages}"
            )

        updated_metafields = result.get("metafields") or []

        if not updated_metafields:
            raise ValueError(
                "Shopify did not return the updated metafields."
            )

        return {
            "success": True,
            "product_id": product_id,
            "fix_action": "set_metafield",
            "metafields": updated_metafields,
            "message": "Product metafields updated successfully.",
        }


