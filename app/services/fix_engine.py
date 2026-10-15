from __future__ import annotations

import json

from typing import Any, Callable

import re

import unicodedata

import requests

from app.services.issue_registry import get_issue_definition

from app.services.shopify_admin_fetcher import fetch_product_variant_state

class FixEngine:

    """

    Central dispatcher for executing approved fixes.

    """

    def __init__(self) -> None:

        self._handlers: dict[str, Callable[..., dict[str, Any]]] = {

            "update_product_handle": self.update_product_handle,

            "set_metafield": self.set_metafield,

            "set_product_type": self.set_product_type,

            "update_product_description": self.update_product_description,

            "update_product_title": self.update_product_title,

            "rename_product_option": self.rename_product_option,

            "generate_sku": self.generate_sku,

            "fix_variant_options": self.fix_variant_options,

            "set_gtin": self.set_gtin,

            "set_mpn": self.set_mpn,

        }
        self._store_handlers: dict[str, Callable[..., dict[str, Any]]] = {
            "normalize_option_structure": self.normalize_option_structure_store_wide,
            "normalize_metafield_structure": self.normalize_metafield_structure_store_wide,
            "normalize_attribute_formats": self.normalize_attribute_formats_store_wide,
            "normalize_attribute_units": self.normalize_attribute_units_store_wide,
            "update_fulfillment_information": self.update_fulfillment_information,
        }

    def update_fulfillment_information(
        self,
        *,
        changes: list[dict[str, Any]],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        """
        Save merchant-approved, agent-readable fulfillment information
        to a Shopify Shop metafield.

        This does not modify Shopify shipping rates, delivery profiles,
        or pickup-location configuration.
        """
        if not shop_domain or not shop_domain.strip():
            raise ValueError("Shop domain is required.")

        if not access_token or not access_token.strip():
            raise ValueError("Shopify access token is required.")

        if not isinstance(changes, list) or len(changes) != 1:
            raise ValueError(
                "Provide exactly one changes object containing fulfillment information."
            )

        change = changes[0]

        if not isinstance(change, dict):
            raise ValueError("The fulfillment change must be a JSON object.")

        allowed_fields = {
            "delivery_timeframe",
            "shipping_methods",
            "pickup_information",
            "region_coverage",
            "fulfillment_constraints",
        }

        fulfillment_data = {
            key: value
            for key, value in change.items()
            if key in allowed_fields and value is not None
        }

        if not fulfillment_data:
            raise ValueError(
                "Provide at least one supported fulfillment field: "
                "delivery_timeframe, shipping_methods, pickup_information, "
                "region_coverage, or fulfillment_constraints."
            )

        for key, value in fulfillment_data.items():
            if isinstance(value, str) and not value.strip():
                raise ValueError(f"{key} cannot be an empty string.")

            if isinstance(value, list) and not value:
                raise ValueError(f"{key} cannot be an empty list.")

            if isinstance(value, (dict, list)):
                # Ensure the submitted data is JSON serializable.
                try:
                    json.dumps(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{key} must contain valid JSON data."
                    ) from exc

        shop_domain = shop_domain.strip()
        access_token = access_token.strip()
        api_version = "2026-07"

        graphql_url = (
            f"https://{shop_domain}/admin/api/"
            f"{api_version}/graphql.json"
        )

        headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": access_token,
        }

        # Retrieve the real Shopify Shop ID. Do not invent an owner ID.
        shop_query = """
        query GetShopId {
          shop {
            id
          }
        }
        """

        try:
            response = requests.post(
                graphql_url,
                headers=headers,
                json={"query": shop_query},
                timeout=30,
            )
            response.raise_for_status()
            response_data = response.json()
        except requests.RequestException as exc:
            raise ValueError(
                f"Could not retrieve the Shopify shop: {exc}"
            ) from exc
        except ValueError as exc:
            raise ValueError(
                "Shopify returned an invalid JSON response while retrieving the shop."
            ) from exc

        if response_data.get("errors"):
            raise ValueError(
                f"Shopify GraphQL error: {response_data['errors']}"
            )

        shop_id = (
            response_data.get("data", {})
            .get("shop", {})
            .get("id")
        )

        if not shop_id:
            raise ValueError("Shopify did not return the shop ID.")

        # Store the information in a structured Shop metafield.
        mutation = """
        mutation SetFulfillmentInformation(
          $metafields: [MetafieldsSetInput!]!
        ) {
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

        variables = {
            "metafields": [
                {
                    "ownerId": shop_id,
                    "namespace": "agentic_commerce",
                    "key": "fulfillment_information",
                    "type": "json",
                    "value": json.dumps(
                        fulfillment_data,
                        ensure_ascii=False,
                    ),
                }
            ]
        }

        try:
            response = requests.post(
                graphql_url,
                headers=headers,
                json={
                    "query": mutation,
                    "variables": variables,
                },
                timeout=30,
            )
            response.raise_for_status()
            response_data = response.json()
        except requests.RequestException as exc:
            raise ValueError(
                f"Could not save fulfillment information: {exc}"
            ) from exc
        except ValueError as exc:
            raise ValueError(
                "Shopify returned an invalid JSON response while saving fulfillment information."
            ) from exc

        if response_data.get("errors"):
            raise ValueError(
                f"Shopify GraphQL error: {response_data['errors']}"
            )

        result = (
            response_data.get("data", {})
            .get("metafieldsSet", {})
        )

        user_errors = result.get("userErrors") or []

        if user_errors:
            messages = "; ".join(
                error.get("message", "Unknown Shopify error")
                for error in user_errors
            )
            raise ValueError(
                f"Could not save fulfillment information: {messages}"
            )

        saved_metafields = result.get("metafields") or []

        if not saved_metafields:
            raise ValueError(
                "Shopify did not confirm that fulfillment information was saved."
            )

        return {
            "success": True,
            "fix_action": "update_fulfillment_information",
            "shop_id": shop_id,
            "metafield": saved_metafields[0],
            "updated_fields": list(fulfillment_data.keys()),
            "message": (
                "Fulfillment information was saved to the Shopify Shop metafield. "
                "Shipping rates and pickup settings were not changed."
            ),
        }
        
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
            raise ValueError("changes must be a non-empty list.")
        if len(changes) > 250:
            raise ValueError("Too many changes in one request (max 250).")

        result = handler(changes=changes, shop_domain=shop_domain, access_token=access_token)
        return {**result, "check_id": check_id, "issue_type": issue_type, "fix_action": fix_action}

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

        if fix_action == "generate_sku":

            variants = kwargs.get("variants")

            if not variants:

                raise ValueError(

                    "At least one variant is required to generate SKUs."

                )

            if not isinstance(variants, list):

                raise ValueError(

                    "Variants must be provided as a list."

                )

        return handler(

            product_id=product_id,

            **kwargs,

        )

    # =================================================================

    # update_product_handle

    # =================================================================

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

    # =================================================================

    # set_metafield (product-level helper)

    # =================================================================

    def set_metafield(
        self,
        *,
        product_id: str,
        attributes: list[dict[str, Any]],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        """Set product metafields using Shopify Admin GraphQL.

        Each attribute requires ``key``, ``type`` and ``value``. ``namespace``
        is optional and defaults to ``details`` to preserve existing behavior.
        Values for the Shopify ``json`` metafield type must be valid JSON.
        """
        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError("Product ID is required.")
        if not isinstance(attributes, list) or not attributes:
            raise ValueError("attributes must be a non-empty list.")
        if not isinstance(shop_domain, str) or not shop_domain.strip():
            raise ValueError("Shop domain is required.")
        if not isinstance(access_token, str) or not access_token.strip():
            raise ValueError("Shopify access token is required.")

        metafields: list[dict[str, str]] = []
        seen_keys: set[tuple[str, str]] = set()
        for index, attribute in enumerate(attributes):
            if not isinstance(attribute, dict):
                raise ValueError(
                    f"Metafield attribute at index {index} must be an object."
                )
            namespace = attribute.get("namespace", "details")
            key = attribute.get("key")
            metafield_type = attribute.get("type")
            value = attribute.get("value")

            if not isinstance(namespace, str) or not namespace.strip():
                raise ValueError(f"Metafield namespace is required for attribute at index {index}.")
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"Metafield key is required for attribute at index {index}.")
            if not isinstance(metafield_type, str) or not metafield_type.strip():
                raise ValueError(f"Metafield type is required for '{key}'.")
            if value is None:
                raise ValueError(f"Metafield value is required for '{key}'.")

            namespace = namespace.strip()
            key = key.strip()
            metafield_type = metafield_type.strip()
            value_string = value if isinstance(value, str) else json.dumps(
                value, ensure_ascii=False, separators=(",", ":")
            )
            if not value_string.strip():
                raise ValueError(f"Metafield value is required for '{key}'.")
            if metafield_type == "json":
                try:
                    json.loads(value_string)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Metafield '{key}' has type 'json' but its value is not valid JSON."
                    ) from exc

            identity = (namespace, key)
            if identity in seen_keys:
                raise ValueError(f"Duplicate metafield namespace/key: '{namespace}.{key}'.")
            seen_keys.add(identity)
            metafields.append({
                "ownerId": product_id.strip(),
                "namespace": namespace,
                "key": key,
                "type": metafield_type,
                "value": value_string.strip(),
            })

        graphql_url = (
            f"https://{shop_domain.strip()}/admin/api/2026-07/graphql.json"
        )
        mutation = """
        mutation MetafieldsSet($metafields: [MetafieldsSetInput!]!) {
          metafieldsSet(metafields: $metafields) {
            metafields { id namespace key type value }
            userErrors { field message code }
          }
        }
        """
        try:
            response = requests.post(
                graphql_url,
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Access-Token": access_token.strip(),
                },
                json={"query": mutation, "variables": {"metafields": metafields}},
                timeout=30,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            response_body = exc.response.text[:2000] if exc.response is not None else str(exc)
            raise ValueError(f"Shopify Admin API HTTP {status_code}: {response_body}") from exc
        except requests.RequestException as exc:
            raise ValueError(f"Could not connect to Shopify Admin API: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError("Shopify Admin API returned an invalid JSON response.") from exc
        if not isinstance(data, dict):
            raise ValueError("Shopify Admin API returned an unexpected response format.")
        if data.get("errors"):
            raise ValueError(f"Shopify GraphQL error: {data['errors']}")

        response_data = data.get("data")
        if not isinstance(response_data, dict):
            raise ValueError("Shopify GraphQL response did not contain a valid data object.")
        result = response_data.get("metafieldsSet") or {}
        user_errors = result.get("userErrors") or []
        if user_errors:
            messages = "; ".join(
                error.get("message", "Unknown Shopify error") for error in user_errors
            )
            raise ValueError(f"Shopify metafield update failed: {messages}")
        updated_metafields = result.get("metafields") or []
        if len(updated_metafields) != len(metafields):
            raise ValueError("Shopify did not confirm that all requested metafields were saved.")
        return {
            "success": True,
            "product_id": product_id.strip(),
            "fix_action": "set_metafield",
            "metafields": updated_metafields,
            "message": "Product metafields updated successfully.",
        }

    def set_product_type(

        self,

        *,

        product_id: str,

        product_type: str,

        shop_domain: str,

        access_token: str,

        **_: Any,

    ) -> dict[str, Any]:

        """

        Set the Shopify product type for a product after merchant approval.

        """

        if not product_id:

            raise ValueError("Product ID is required.")

        if not product_type or not str(product_type).strip():

            raise ValueError("Product type is required.")

        if not shop_domain or not str(shop_domain).strip():

            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():

            raise ValueError("Shopify access token is required.")

        product_type = str(product_type).strip()

        shop_domain = str(shop_domain).strip()

        access_token = str(access_token).strip()

        api_version = "2026-07"

        graphql_url = (

            f"https://{shop_domain}/admin/api/"

            f"{api_version}/graphql.json"

        )

        mutation = """

        mutation SetProductType($input: ProductInput!) {

          productUpdate(input: $input) {

            product {

              id

              productType

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

                "productType": product_type,

            }

        }

        response = requests.post(

            graphql_url,

            headers={

                "Content-Type": "application/json",

                "X-Shopify-Access-Token": access_token,

            },

            json={"query": mutation, "variables": variables},

            timeout=30,

        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):

            raise ValueError(f"Shopify GraphQL error: {data['errors']}")

        result = data.get("data", {}).get("productUpdate", {})

        user_errors = result.get("userErrors") or []

        if user_errors:

            messages = "; ".join(

                e.get("message", "Unknown Shopify error")

                for e in user_errors

            )

            raise ValueError(f"Shopify product update failed: {messages}")

        product = result.get("product")

        if not product:

            raise ValueError(

                "Shopify did not return the updated product."

            )

        return {

            "success": True,

            "product_id": product.get("id"),

            "product_type": product.get("productType"),

            "fix_action": "set_product_type",

            "message": "Product type updated successfully.",

        }

    # =================================================================

    # update_product_description

    # =================================================================

    def update_product_description(

        self,

        *,

        product_id: str,

        description_html: str,

        shop_domain: str,

        access_token: str,

        **_: Any,

    ) -> dict[str, Any]:

        """

        Update Shopify product description (HTML) after merchant approval.

        """

        if not product_id:

            raise ValueError("Product ID is required.")

        if not description_html or not str(description_html).strip():

            raise ValueError("Product description is required.")

        if not shop_domain or not str(shop_domain).strip():

            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():

            raise ValueError("Shopify access token is required.")

        description_html = str(description_html).strip()

        shop_domain = str(shop_domain).strip()

        access_token = str(access_token).strip()

        api_version = "2026-07"

        graphql_url = (

            f"https://{shop_domain}/admin/api/"

            f"{api_version}/graphql.json"

        )

        mutation = """

        mutation UpdateProductDescription($input: ProductInput!) {

          productUpdate(input: $input) {

            product {

              id

              title

              descriptionHtml

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

                "descriptionHtml": description_html,

            }

        }

        response = requests.post(

            graphql_url,

            headers={

                "Content-Type": "application/json",

                "X-Shopify-Access-Token": access_token,

            },

            json={"query": mutation, "variables": variables},

            timeout=30,

        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):

            raise ValueError(f"Shopify GraphQL error: {data['errors']}")

        result = data.get("data", {}).get("productUpdate", {})

        user_errors = result.get("userErrors") or []

        if user_errors:

            messages = "; ".join(

                e.get("message", "Unknown Shopify error")

                for e in user_errors

            )

            raise ValueError(f"Shopify product update failed: {messages}")

        product = result.get("product")

        if not product:

            raise ValueError(

                "Shopify did not return the updated product."

            )

        return {

            "success": True,

            "product_id": product.get("id"),

            "description_html": product.get("descriptionHtml"),

            "fix_action": "update_product_description",

            "message": "Product description updated successfully.",

        }

    # =================================================================

    # update_product_title

    # =================================================================

    def update_product_title(

        self,

        *,

        product_id: str,

        title: str,

        shop_domain: str,

        access_token: str,

        **_: Any,

    ) -> dict[str, Any]:

        """

        Update Shopify product title after merchant approval.

        """

        if not product_id:

            raise ValueError("Product ID is required.")

        if not title or not str(title).strip():

            raise ValueError("Product title is required.")

        if not shop_domain or not str(shop_domain).strip():

            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():

            raise ValueError("Shopify access token is required.")

        title = str(title).strip()

        shop_domain = str(shop_domain).strip()

        access_token = str(access_token).strip()

        api_version = "2026-07"

        graphql_url = (

            f"https://{shop_domain}/admin/api/"

            f"{api_version}/graphql.json"

        )

        mutation = """

        mutation UpdateProductTitle($input: ProductInput!) {

          productUpdate(input: $input) {

            product {

              id

              title

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

                "title": title,

            }

        }

        response = requests.post(

            graphql_url,

            headers={

                "Content-Type": "application/json",

                "X-Shopify-Access-Token": access_token,

            },

            json={"query": mutation, "variables": variables},

            timeout=30,

        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):

            raise ValueError(f"Shopify GraphQL error: {data['errors']}")

        result = data.get("data", {}).get("productUpdate", {})

        user_errors = result.get("userErrors") or []

        if user_errors:

            messages = "; ".join(

                e.get("message", "Unknown Shopify error")

                for e in user_errors

            )

            raise ValueError(f"Shopify product update failed: {messages}")

        product = result.get("product")

        if not product:

            raise ValueError(

                "Shopify did not return the updated product."

            )

        return {

            "success": True,

            "product_id": product.get("id"),

            "title": product.get("title"),

            "fix_action": "update_product_title",

            "message": "Product title updated successfully.",

        }

    # =================================================================

    # rename_product_option

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
        """
        Rename a product option (e.g., 'Option1' -> 'Size') after merchant approval.
        """

        if not product_id:
            raise ValueError("Product ID is required.")

        if not option_id:
            raise ValueError("Option ID is required.")

        if not new_name or not str(new_name).strip():
            raise ValueError("New option name is required.")

        if not shop_domain or not str(shop_domain).strip():
            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():
            raise ValueError("Shopify access token is required.")

        new_name = str(new_name).strip()
        shop_domain = str(shop_domain).strip()
        access_token = str(access_token).strip()
        api_version = "2026-07"
        graphql_url = (
            f"https://{shop_domain}/admin/api/"
            f"{api_version}/graphql.json"
        )
        mutation = """
        mutation RenameProductOption($productId: ID!, $optionId: ID!, $newName: String!) {
          productOptionUpdate(
            productId: $productId,
            option: { id: $optionId, name: $newName }
          ) {
            product {
              id
              options {
                id
                name
                position
              }
            }
            userErrors {
              field
              message
              code
            }
          }
        }

        """

        variables = {
            "productId": product_id,
            "optionId": option_id,
            "newName": new_name,
        }

        try:
            response = requests.post(
                graphql_url,
                headers={
                    "Content-Type": "application/json",
                    "X-Shopify-Access-Token": access_token,
                },
                json={"query": mutation, "variables": variables},
                timeout=30,
            )
            response.raise_for_status()
        except requests.HTTPError as exc:
            status_code = (
                exc.response.status_code
                if exc.response is not None
                else "unknown"
            )
            # Shopify's response body is useful for debugging API errors.
            # Do not include request headers, since they contain the token.
            response_body = (
                exc.response.text[:2000]
                if exc.response is not None
                else str(exc)
            )
            raise ValueError(
                f"Shopify Admin API HTTP {status_code}: {response_body}"
            ) from exc
        except requests.RequestException as exc:
            raise ValueError(
                f"Could not connect to Shopify Admin API: {exc}"
            ) from exc

        try:
            data = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as exc:
            raise ValueError(
                "Shopify Admin API returned an invalid JSON response."
            ) from exc

        if not isinstance(data, dict):
            raise ValueError(
                "Shopify Admin API returned an unexpected response format."
            )

        if data.get("errors"):
            raise ValueError(f"Shopify GraphQL error: {data['errors']}")

        response_data = data.get("data")
        if not isinstance(response_data, dict):
            raise ValueError(
                "Shopify GraphQL response did not contain a valid data object."
            )

        result = response_data.get("productOptionUpdate") or {}

        user_errors = result.get("userErrors") or []

        if user_errors:
            messages = "; ".join(
                e.get("message", "Unknown Shopify error")
                for e in user_errors
            )
            raise ValueError(
                f"Shopify product option update failed: {messages}"
            )

        product = result.get("product")

        if not isinstance(product, dict):
            raise ValueError(
                "Shopify did not return the updated product."
            )

        updated_options = product.get("options")

        if not isinstance(updated_options, list):
            raise ValueError(
                "Shopify did not return the updated product options."
            )

        updated_option = next(
            (
                option
                for option in updated_options
                if option.get("id") == option_id
            ),
            None,
        )

        if not updated_option:
            raise ValueError(
                "The updated option was not found in Shopify's response."
            )

        if updated_option.get("name") != new_name:
            raise ValueError(
                "Shopify returned the product, but the option name "
                "does not match the requested name."
            )

        return {
            "success": True,
            "product_id": product.get("id"),
            "options": updated_options,
            "fix_action": "rename_product_option",
            "message": "Product option renamed successfully.",
        }

    # =================================================================

    # generate_sku (variantsBulkUpdate)

    # =================================================================

    def generate_sku(

        self,

        *,

        product_id: str,

        variants: list[dict[str, Any]],

        shop_domain: str,

        access_token: str,

        **_: Any,

    ) -> dict[str, Any]:

        if not product_id:

            raise ValueError("Product ID is required.")

        if not variants:

            raise ValueError("At least one variant is required to set SKU.")

        if not shop_domain or not str(shop_domain).strip():

            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():

            raise ValueError("Shopify access token is required.")

        shop_domain = str(shop_domain).strip()

        access_token = str(access_token).strip()

        formatted_variants: list[dict[str, Any]] = []

        for v in variants:

            variant_id = v.get("id")

            sku = v.get("sku")

            if not variant_id:

                raise ValueError("Variant ID is required for each variant.")

            if not sku or not str(sku).strip():

                raise ValueError(

                    f"SKU is required for variant '{variant_id}'."

                )

            formatted_variants.append(

                {

                    "id": variant_id,

                    "inventoryItem": {

                        "sku": str(sku).strip(),

                    },

                }

            )

        api_version = "2026-07"

        graphql_url = (

            f"https://{shop_domain}/admin/api/"

            f"{api_version}/graphql.json"

        )

        mutation = """

        mutation GenerateSkuForVariants(

            $productId: ID!,

            $variants: [ProductVariantsBulkInput!]!

        ) {

            productVariantsBulkUpdate(

                productId: $productId,

                variants: $variants

            ) {

                productVariants {

                    id

                    inventoryItem {

                        id

                        sku

                    }

                }

                userErrors {

                    field

                    message

                    code

                }

            }

        }

        """

        variables = {

            "productId": product_id,

            "variants": formatted_variants,

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

            .get("productVariantsBulkUpdate", {})

        )

        user_errors = result.get("userErrors") or []

        if user_errors:

            messages = "; ".join(

                error.get("message", "Unknown Shopify error")

                for error in user_errors

            )

            raise ValueError(

                f"Shopify variant update failed: {messages}"

            )

        updated_variants = result.get("productVariants") or []

        if not updated_variants:

            raise ValueError(

                "Shopify did not return the updated variants."

            )

        return {

            "success": True,

            "product_id": product_id,

            "fix_action": "generate_sku",

            "variants": updated_variants,

            "message": "Variant SKUs updated successfully.",

        }

    def suggest_sku(

        self,

        *,

        product_title: str,

        selected_options: list[dict[str, str]] | None = None,

    ) -> dict[str, Any]:

        def slug(value: str, max_len: int) -> str:

            value = unicodedata.normalize("NFKD", value or "")

            value = value.encode("ascii", "ignore").decode("ascii").upper()

            value = re.sub(r"[^A-Z0-9]+", "", value)

            return value[:max_len]

        title_part = slug(product_title, 6) or "ITEM"

        option_parts = [

            slug(option.get("value", ""), 4)

            for option in (selected_options or [])

            if option.get("value")

        ]

        option_parts = [part for part in option_parts if part]

        sku = "-".join([title_part, *option_parts]) if option_parts else title_part

        if not sku:

            raise ValueError(

                "Unable to generate a SKU suggestion from the given product title/options."

            )

        return {"suggested_sku": sku}

    # =================================================================

    # Builders for fix_variant_options

    # =================================================================

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

            api_version="2026-07",

            product_id=product_id,

        )

        # 1) Collect requested values per option name

        requested_values_by_option: dict[str, set[str]] = {}

        for requested_for_variant in variant_option_values.values():

            # requested_for_variant: { "Size": "Small", "Color": "Red", ... }

            for option_name, new_value in (requested_for_variant or {}).items():

                if not option_name or new_value is None:

                    continue

                value_str = str(new_value).strip()

                if not value_str:

                    continue

                requested_values_by_option.setdefault(option_name, set()).add(

                    value_str

                )

        # 2) Build productOptions including BOTH existing and requested values

        product_options: list[dict[str, Any]] = []

        for option in product.get("options") or []:

            option_id = option.get("id")

            option_name = option.get("name")

            position = option.get("position")

            option_values = option.get("values") or []

            if not option_name:

                continue

            # Existing values from Shopify

            value_set: set[str] = {

                str(v).strip() for v in option_values if v

            }

            # Add any new values from the UI for this option

            for requested_value in requested_values_by_option.get(option_name, set()):

                value_set.add(requested_value)

            if not value_set:

                continue

            product_options.append(

                {

                    "id": option_id,

                    "name": option_name,

                    "position": position,

                    "values": [

                        {"name": v} for v in sorted(value_set) if v

                    ],

                }

            )

        if not product_options:

            raise ValueError("Product has no valid options.")

        # 3) Build variants with final optionValues

        variants_input: list[dict[str, Any]] = []

        for edge in (product.get("variants") or {}).get("edges", []):

            variant = edge.get("node") or {}

            variant_id = variant.get("id")

            if not variant_id:

                continue

            requested_for_variant = variant_option_values.get(variant_id, {}) or {}

            current_selected_options = variant.get("selectedOptions") or []

            option_values: list[dict[str, str]] = []

            for selected_option in current_selected_options:

                option_name = selected_option.get("name")

                current_value = selected_option.get("value")

                if not option_name:

                    continue

                new_value = requested_for_variant.get(option_name, current_value)

                if new_value is None or not str(new_value).strip():

                    raise ValueError(

                        f"Missing option value for variant "

                        f"'{variant_id}', option '{option_name}'."

                    )

                option_values.append(

                    {

                        "optionName": option_name,

                        "name": str(new_value).strip(),

                    }

                )

            if not option_values:

                raise ValueError(

                    f"Variant '{variant_id}' has no option values."

                )

            variants_input.append(

                {

                    "id": variant_id,

                    "optionValues": option_values,

                }

            )

        if not variants_input:

            raise ValueError("Product has no valid variants.")

        # 4) ProductSetInput for productSet

        return {

            "id": product_id,

            "productOptions": product_options,

            "variants": variants_input,

        }

    def build_variant_matrix_input(

        self,

        *,

        shop_domain: str,

        access_token: str,

        product_id: str,

        options: list[dict[str, Any]],

        default_price: str | None = None,

    ) -> dict[str, Any]:

        from app.services.shopify_admin_fetcher import fetch_product_variant_state

        import itertools

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

            api_version="2026-07",

            product_id=product_id,

        )

        existing_variants = (product.get("variants") or {}).get("edges", [])

        current_price = existing_variants[0].get("node", {}).get("price") if existing_variants else None

        price = str(default_price or current_price or "0.00")

        options_input = [

            {"name": option["name"].strip(), "position": index + 1,

             "values": [{"name": v} for v in option["values"]]}

            for index, option in enumerate(options)

        ]

        option_names = [option["name"].strip() for option in options]

        value_lists = [option["values"] for option in options]

        title = product.get("title") or ""

        variants_input = []

        for combo in itertools.product(*value_lists):

            selected = [{"optionName": name, "name": value} for name, value in zip(option_names, combo)]

            sku = self.suggest_sku(

                product_title=title,

                selected_options=[{"value": value} for value in combo],

            )["suggested_sku"]

            variants_input.append({"optionValues": selected, "price": price, "sku": sku})

        return {"title": title, "options": options_input, "variants": variants_input}

    @staticmethod

    def suggest_normalized_option_value(value: str) -> str:

        cleaned = " ".join((value or "").strip().split())

        return cleaned.title() if cleaned else cleaned

    # =================================================================

    # fix_variant_options (via productSet)

    # =================================================================

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

        """

        Normalize product options/variants using productSet.

        `product_set_input` should be a partial/complete ProductSetInput.

        The product ID is enforced from `product_id`.

        """

        if not product_id:

            raise ValueError("Product ID is required.")

        if not isinstance(product_set_input, dict):

            raise ValueError("product_set_input must be a dict.")

        if not shop_domain or not str(shop_domain).strip():

            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():

            raise ValueError("Shopify access token is required.")

        shop_domain = str(shop_domain).strip()

        access_token = str(access_token).strip()

        # Ensure the product ID is present in the ProductSetInput

        product_set_input = {

            **product_set_input,

            "id": product_id,

        }

        api_version = "2026-07"

        graphql_url = (

            f"https://{shop_domain}/admin/api/"

            f"{api_version}/graphql.json"

        )

        mutation = """

        mutation FixVariantOptions($input: ProductSetInput!, $synchronous: Boolean!) {

          productSet(input: $input, synchronous: $synchronous) {

            product {

              id

              options {

                id

                name

              }

              variants(first: 10) {

                nodes {

                  id

                  title

                }

              }

            }

            userErrors {

              field

              message

            }

          }

        }

        """

        variables = {

            "input": product_set_input,

            "synchronous": synchronous,

        }

        response = requests.post(

            graphql_url,

            headers={

                "Content-Type": "application/json",

                "X-Shopify-Access-Token": access_token,

            },

            json={"query": mutation, "variables": variables},

            timeout=60,

        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):

            raise ValueError(f"Shopify GraphQL error: {data['errors']}")

        result = data.get("data", {}).get("productSet", {})

        user_errors = result.get("userErrors") or []

        if user_errors:

            messages = "; ".join(

                e.get("message", "Unknown Shopify error")

                for e in user_errors

            )

            raise ValueError(

                f"Shopify productSet (variant options) failed: {messages}"

            )

        product = result.get("product")

        if not product:

            raise ValueError(

                "Shopify did not return the updated product."

            )

        return {

            "success": True,

            "product_id": product.get("id"),

            "options": product.get("options"),

            "variants": product.get("variants"),

            "fix_action": "fix_variant_options",

            "message": "Product options and variants normalized successfully.",

        }

    # =================================================================

    # set_gtin (variant-level metafield)

    # =================================================================

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

        if not product_id:

            raise ValueError("Product ID is required.")

        if not variant_id:

            raise ValueError("Variant ID is required.")

        if not gtin or not str(gtin).strip():

            raise ValueError("GTIN is required.")

        if not shop_domain or not str(shop_domain).strip():

            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():

            raise ValueError("Shopify access token is required.")

        product_id = str(product_id).strip()

        variant_id = str(variant_id).strip()

        gtin = str(gtin).strip()

        shop_domain = str(shop_domain).strip()

        access_token = str(access_token).strip()

        api_version = "2026-07"

        graphql_url = (

            f"https://{shop_domain}/admin/api/"

            f"{api_version}/graphql.json"

        )

        # Shopify's native ProductVariant barcode field is the source of

        # truth used by the audit for GTIN/barcode validation.

        mutation = """

        mutation SetVariantBarcode(

            $productId: ID!,

            $variants: [ProductVariantsBulkInput!]!

        ) {

            productVariantsBulkUpdate(

                productId: $productId,

                variants: $variants

            ) {

                productVariants {

                    id

                    barcode

                }

                userErrors {

                    field

                    message

                    code

                }

            }

        }

        """

        variables = {

            "productId": product_id,

            "variants": [

                {

                    "id": variant_id,

                    "barcode": gtin,

                }

            ],

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

        # Top-level GraphQL errors

        if data.get("errors"):

            raise ValueError(

                f"Shopify GraphQL error: {data['errors']}"

            )

        result = (

            data.get("data", {})

            .get("productVariantsBulkUpdate", {})

        )

        user_errors = result.get("userErrors") or []

        if user_errors:

            messages = "; ".join(

                error.get("message", "Unknown Shopify error")

                for error in user_errors

            )

            raise ValueError(

                f"Shopify GTIN update failed: {messages}"

            )

        updated_variants = result.get("productVariants") or []

        updated_variant = next(

            (

                variant

                for variant in updated_variants

                if variant.get("id") == variant_id

            ),

            None,

        )

        if not updated_variant:

            raise ValueError(

                "Shopify did not return the updated variant."

            )

        saved_barcode = updated_variant.get("barcode")

        if str(saved_barcode or "").strip() != gtin:

            raise ValueError(

                "Shopify GTIN update did not persist correctly. "

                f"Expected barcode={gtin!r}, "

                f"received barcode={saved_barcode!r}."

            )

        return {

            "success": True,

            "product_id": product_id,

            "variant_id": variant_id,

            "fix_action": "set_gtin",

            "barcode": saved_barcode,

            "message": "Variant GTIN updated successfully.",

        }

    # =================================================================

    # set_mpn (variant-level metafield)

    # =================================================================

    def set_mpn(

        self,

        *,

        product_id: str,

        variant_id: str,

        mpn: str,

        shop_domain: str,

        access_token: str,

        **_: Any,

    ) -> dict[str, Any]:

        """

        Set MPN for a variant via metafield (namespace 'identifiers', key 'mpn').

        """

        if not variant_id:

            raise ValueError("Variant ID is required.")

        if not mpn or not str(mpn).strip():

            raise ValueError("MPN is required.")

        if not shop_domain or not str(shop_domain).strip():

            raise ValueError("Shop domain is required.")

        if not access_token or not str(access_token).strip():

            raise ValueError("Shopify access token is required.")

        mpn = str(mpn).strip()

        shop_domain = str(shop_domain).strip()

        access_token = str(access_token).strip()

        metafields = [

            {

                "ownerId": variant_id,

                "namespace": "identifiers",

                "key": "mpn",

                "type": "single_line_text_field",

                "value": mpn,

            }

        ]

        api_version = "2026-07"

        graphql_url = (

            f"https://{shop_domain}/admin/api/"

            f"{api_version}/graphql.json"

        )

        mutation = """

        mutation SetMpn($metafields: [MetafieldsSetInput!]!) {

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

        variables = {"metafields": metafields}

        response = requests.post(

            graphql_url,

            headers={

                "Content-Type": "application/json",

                "X-Shopify-Access-Token": access_token,

            },

            json={"query": mutation, "variables": variables},

            timeout=30,

        )

        response.raise_for_status()

        data = response.json()

        if data.get("errors"):

            raise ValueError(f"Shopify GraphQL error: {data['errors']}")

        result = data.get("data", {}).get("metafieldsSet", {})

        user_errors = result.get("userErrors") or []

        if user_errors:

            messages = "; ".join(

                e.get("message", "Unknown Shopify error")

                for e in user_errors

            )

            raise ValueError(f"Shopify MPN update failed: {messages}")

        updated_metafields = result.get("metafields") or []

        if not updated_metafields:

            raise ValueError(

                "Shopify did not return the updated MPN metafield."

            )

        return {

            "success": True,

            "product_id": product_id,

            "variant_id": variant_id,

            "fix_action": "set_mpn",

            "metafields": updated_metafields,

            "message": "Variant MPN updated successfully.",

        }

    # =================================================================
    # STORE-WIDE CATALOG CONSISTENCY FIXES
    # =================================================================

    def normalize_option_structure_store_wide(
        self,
        *,
        changes: list[dict[str, Any]],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        if not isinstance(changes, list):
            raise ValueError("Store-wide changes must be provided as a list.")

        if not changes:
            raise ValueError(
                "At least one store-wide option change is required."
            )

        results = []
        failures = []

        for index, change in enumerate(changes):
            product_id_for_error = change.get("product_id") if isinstance(change, dict) else None
            try:
                if not isinstance(change, dict):
                    raise ValueError("Each change must be a JSON object.")
                product_id = str(change.get("product_id") or "").strip()
                option_id = str(change.get("option_id") or "").strip()
                new_name = str(change.get("new_name") or "").strip()

                if not product_id:
                    raise ValueError("product_id is required.")

                if not option_id:
                    raise ValueError("option_id is required.")

                if not new_name:
                    raise ValueError("new_name is required.")

                result = self.rename_product_option(
                    product_id=product_id,
                    option_id=option_id,
                    new_name=new_name,
                    shop_domain=shop_domain,
                    access_token=access_token,
                )

                results.append(
                    {
                        "product_id": product_id,
                        "success": True,
                        "result": result,
                    }
                )

            except Exception as exc:
                failures.append(
                    {
                        "index": index,
                        "product_id": product_id_for_error,
                        "success": False,
                        "error": str(exc),
                    }
                )

        return {
            "success": len(failures) == 0,
            "partial_success": bool(results) and bool(failures),
            "fix_action": "normalize_option_structure_store_wide",
            "total": len(changes),
            "updated": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }

    def normalize_metafield_structure_store_wide(
        self,
        *,
        changes: list[dict[str, Any]],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        if not isinstance(changes, list):
            raise ValueError("Store-wide changes must be provided as a list.")

        if not changes:
            raise ValueError(
                "At least one store-wide metafield change is required."
            )

        results = []
        failures = []

        for index, change in enumerate(changes):
            product_id_for_error = change.get("product_id") if isinstance(change, dict) else None
            try:
                if not isinstance(change, dict):
                    raise ValueError("Each change must be a JSON object.")
                product_id = str(change.get("product_id") or "").strip()
                attributes = change.get("attributes")

                if not product_id:
                    raise ValueError("product_id is required.")

                if not isinstance(attributes, list):
                    raise ValueError("attributes must be a list.")

                if not attributes:
                    raise ValueError(
                        "At least one metafield attribute is required."
                    )

                result = self.set_metafield(
                    product_id=product_id,
                    attributes=attributes,
                    shop_domain=shop_domain,
                    access_token=access_token,
                )

                results.append(
                    {
                        "product_id": product_id,
                        "success": True,
                        "result": result,
                    }
                )

            except Exception as exc:
                failures.append(
                    {
                        "index": index,
                        "product_id": product_id_for_error,
                        "success": False,
                        "error": str(exc),
                    }
                )

        return {
            "success": len(failures) == 0,
            "partial_success": bool(results) and bool(failures),
            "fix_action": "normalize_metafield_structure_store_wide",
            "total": len(changes),
            "updated": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }

    def normalize_attribute_formats_store_wide(
        self,
        *,
        changes: list[dict[str, Any]],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        if not isinstance(changes, list):
            raise ValueError("Store-wide changes must be provided as a list.")

        if not changes:
            raise ValueError(
                "At least one store-wide attribute format change is required."
            )

        results = []
        failures = []

        for index, change in enumerate(changes):
            product_id_for_error = change.get("product_id") if isinstance(change, dict) else None
            try:
                if not isinstance(change, dict):
                    raise ValueError("Each change must be a JSON object.")
                product_id = str(change.get("product_id") or "").strip()
                attributes = change.get("attributes")

                if not product_id:
                    raise ValueError("product_id is required.")

                if not isinstance(attributes, list):
                    raise ValueError("attributes must be a list.")

                if not attributes:
                    raise ValueError("At least one attribute is required.")

                result = self.set_metafield(
                    product_id=product_id,
                    attributes=attributes,
                    shop_domain=shop_domain,
                    access_token=access_token,
                )

                results.append(
                    {
                        "product_id": product_id,
                        "success": True,
                        "result": result,
                    }
                )

            except Exception as exc:
                failures.append(
                    {
                        "index": index,
                        "product_id": product_id_for_error,
                        "success": False,
                        "error": str(exc),
                    }
                )

        return {
            "success": len(failures) == 0,
            "partial_success": bool(results) and bool(failures),
            "fix_action": "normalize_attribute_formats_store_wide",
            "total": len(changes),
            "updated": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }

    def normalize_attribute_units_store_wide(
        self,
        *,
        changes: list[dict[str, Any]],
        shop_domain: str,
        access_token: str,
        **_: Any,
    ) -> dict[str, Any]:
        if not isinstance(changes, list):
            raise ValueError("Store-wide changes must be provided as a list.")

        if not changes:
            raise ValueError(
                "At least one store-wide attribute unit change is required."
            )

        results = []
        failures = []

        for index, change in enumerate(changes):
            product_id_for_error = change.get("product_id") if isinstance(change, dict) else None
            try:
                if not isinstance(change, dict):
                    raise ValueError("Each change must be a JSON object.")
                product_id = str(change.get("product_id") or "").strip()
                attributes = change.get("attributes")

                if not product_id:
                    raise ValueError("product_id is required.")

                if not isinstance(attributes, list):
                    raise ValueError("attributes must be a list.")

                if not attributes:
                    raise ValueError("At least one attribute is required.")

                result = self.set_metafield(
                    product_id=product_id,
                    attributes=attributes,
                    shop_domain=shop_domain,
                    access_token=access_token,
                )

                results.append(
                    {
                        "product_id": product_id,
                        "success": True,
                        "result": result,
                    }
                )

            except Exception as exc:
                failures.append(
                    {
                        "index": index,
                        "product_id": product_id_for_error,
                        "success": False,
                        "error": str(exc),
                    }
                )

        return {
            "success": len(failures) == 0,
            "partial_success": bool(results) and bool(failures),
            "fix_action": "normalize_attribute_units_store_wide",
            "total": len(changes),
            "updated": len(results),
            "failed": len(failures),
            "results": results,
            "failures": failures,
        }
