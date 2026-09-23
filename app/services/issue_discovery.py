from __future__ import annotations

from typing import Any

from app.services.issue_registry import (
    get_issue_definition,
    find_issue_definition,
)


def normalize_issue(
    *,
    check_id: str,
    issue: dict[str, Any],
    product_id: str | None = None,
    variant_id: str | None = None,
    field: str | None = None,
    affected_product_ids: list[str] | None = None,
) -> dict[str, Any]:

    issue_type = issue["issue_type"]
    status = issue["status"]

    record = {
        "check_id": check_id,
        "issue_type": issue_type,
        "status": status,
        "description": issue["description"],
        "product_id": product_id,
        "variant_id": variant_id,
        "field": field,
        "affected_product_ids": affected_product_ids or [],
        "scope": None,
        "fix_mode": "unclassified",
        "fix_action": None,
    }

    if status == "existing":
        definition = get_issue_definition(check_id, issue_type)

        if definition is None:
            found = find_issue_definition(issue_type)

            if found is None:
                record["status"] = "new"
                return record

            canonical_check_id, definition = found
            record["check_id"] = canonical_check_id

        fix_mode = definition.get("fix_mode")
        fix_action = definition.get("fix_action")

        if not fix_mode:
            raise ValueError(
                f"Issue {issue_type!r} for check {check_id!r} "
                "has no configured fix_mode"
            )

        if fix_mode != "unsupported" and not fix_action:
            raise ValueError(
                f"Issue {issue_type!r} for check {check_id!r} "
                f"has fix_mode={fix_mode!r} but no fix_action"
            )
        record["scope"] = definition["scope"]
        record["fix_mode"] = fix_mode
        record["fix_action"] = fix_action

    return record