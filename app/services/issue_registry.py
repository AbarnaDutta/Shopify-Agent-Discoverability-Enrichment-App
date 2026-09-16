# app/services/issue_registry.py

ISSUE_TYPES = {

    # ============================================================
    # UCP COMMERCE FLOWS
    # ============================================================

    "stable_ids_urls": {
        "missing_product_id": {
            "scope": "product",
            "fix_mode": "unsupported",
            "fix_action": None,
        },
        "missing_product_url": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_handle",
        },
        "invalid_product_url": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_handle",
        },
    },

    "variant_selection": {
        "missing_option_name": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "rename_product_option",
        },
        "generic_option_name": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "rename_product_option",
        },
        "incomplete_selected_options": {
            "scope": "variant",
            "fix_mode": "approval",
            "fix_action": "fix_variant_options",
        },
        "inconsistent_variant_options": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "fix_variant_options",
        },
    },

    "pricing_clarity": {
        "missing_price": {
            "scope": "variant",
            "fix_mode": "user_input",
            "fix_action": "set_variant_price",
        },
        "zero_price": {
            "scope": "variant",
            "fix_mode": "user_input",
            "fix_action": "set_variant_price",
        },
        "placeholder_price": {
            "scope": "variant",
            "fix_mode": "user_input",
            "fix_action": "set_variant_price",
        },
    },

    "availability_signals": {
        "missing_inventory_signal": {
            "scope": "variant",
            "fix_mode": "unsupported",
            "fix_action": None,
        },
        "ambiguous_buyability": {
            "scope": "variant",
            "fix_mode": "unsupported",
            "fix_action": None,
        },
    },

    "fulfillment_context": {
        "missing_delivery_time": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_fulfillment_information",
        },
        "missing_shipping_methods": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_fulfillment_information",
        },
        "missing_pickup_information": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_fulfillment_information",
        },
        "missing_region_coverage": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_fulfillment_information",
        },
        "incomplete_fulfillment_constraints": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_fulfillment_information",
        },
    },


    # ============================================================
    # MCP KNOWLEDGE
    # ============================================================

    "product_understanding": {
        "missing_product_title": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_title",
        },
        "insufficient_product_description": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_description",
        },
        "missing_target_audience": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_description",
        },
        "missing_included_items": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_description",
        },
        "missing_excluded_items": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_description",
        },
    },

    "comparable_attributes": {
        "missing_product_type": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "set_product_type",
        },
        "missing_structured_attribute": {
            "scope": "product",
            "fix_mode": "user_input",
            "fix_action": "set_metafield",
        },
        "insufficient_comparable_attributes": {
            "scope": "product",
            "fix_mode": "user_input",
            "fix_action": "set_metafield",
        },
    },

    "policy_semantics": {
        "placeholder_in_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "missing_policy_deadline": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "missing_policy_exception": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "missing_policy_region": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "ambiguous_policy_rule": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
    },

    "faq_or_guidance": {
        "missing_faq": {
            "scope": "store",
            "fix_mode": "approval",
            "fix_action": "create_faq",
        },
        "insufficient_shopping_guidance": {
            "scope": "store",
            "fix_mode": "approval",
            "fix_action": "create_faq",
        },
    },

    "product_clarity": {
        "unclear_product_usage": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_description",
        },
        "unclear_included_items": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "update_product_description",
        },
        "unclarified_medical_claim": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "review_product_claim",
        },
        "unclarified_financial_claim": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "review_product_claim",
        },
    },


    # ============================================================
    # CATALOG ENRICHMENT
    # ============================================================

    "identifiers": {
        "missing_sku": {
            "scope": "variant",
            "fix_mode": "approval",
            "fix_action": "generate_sku",
        },
        "missing_gtin": {
            "scope": "variant",
            "fix_mode": "user_input",
            "fix_action": "set_gtin",
        },
        "missing_mpn": {
            "scope": "variant",
            "fix_mode": "user_input",
            "fix_action": "set_mpn",
        },
        "invalid_gtin": {
            "scope": "variant",
            "fix_mode": "user_input",
            "fix_action": "set_gtin",
        },
    },

    "rich_attributes": {
        "missing_required_attribute": {
            "scope": "product",
            "fix_mode": "user_input",
            "fix_action": "set_metafield",
        },
        "unstructured_product_attribute": {
            "scope": "product",
            "fix_mode": "user_input",
            "fix_action": "set_metafield",
        },
    },

    "variant_hygiene": {
        "generic_option_name": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "rename_product_option",
        },
        "default_title_with_real_variations": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "fix_variant_options",
        },
        "inconsistent_option_values": {
            "scope": "product",
            "fix_mode": "approval",
            "fix_action": "fix_variant_options",
        },
    },

    "consistency": {
        "inconsistent_metafield_keys": {
            "scope": "store",
            "fix_mode": "approval",
            "fix_action": "normalize_metafield_structure",
        },
        "inconsistent_attribute_units": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "normalize_attribute_units",
        },
        "inconsistent_attribute_formats": {
            "scope": "store",
            "fix_mode": "approval",
            "fix_action": "normalize_attribute_formats",
        },
    },


    # ============================================================
    # SAFETY & POLICIES
    # ============================================================

    "product_guardrails": {
        "missing_age_limit": {
            "scope": "product",
            "fix_mode": "user_input",
            "fix_action": "set_guardrail_metafield",
        },
        "missing_warning": {
            "scope": "product",
            "fix_mode": "user_input",
            "fix_action": "set_guardrail_metafield",
        },
        "missing_human_review_flag": {
            "scope": "product",
            "fix_mode": "user_input",
            "fix_action": "set_guardrail_metafield",
        },
    },

    "store_guardrails": {
        "missing_age_gating": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "configure_store_guardrail",
        },
        "missing_region_restriction": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "configure_store_guardrail",
        },
        "missing_manual_approval_rule": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "configure_store_guardrail",
        },
    },

    "legal_pages": {
        "missing_privacy_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "missing_refund_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "missing_shipping_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "missing_terms_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "placeholder_privacy_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "placeholder_refund_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "placeholder_shipping_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
        "placeholder_terms_policy": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_policy",
        },
    },

    "contact_brand": {
        "missing_contact_information": {
            "scope": "store",
            "fix_mode": "user_input",
            "fix_action": "update_store_contact",
        },
        "missing_brand_information": {
            "scope": "store",
            "fix_mode": "approval",
            "fix_action": "update_brand_information",
        },
    },
}


def get_issue_definition(check_id: str, issue_type: str) -> dict | None:
    return ISSUE_TYPES.get(check_id, {}).get(issue_type)


def is_valid_issue_type(check_id: str, issue_type: str) -> bool:
    return issue_type in ISSUE_TYPES.get(check_id, {})


def get_supported_issue_types(check_id: str) -> list[str]:
    return list(ISSUE_TYPES.get(check_id, {}).keys())