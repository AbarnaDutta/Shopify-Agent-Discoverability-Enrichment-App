#app/services/audit_engine.py
from __future__ import annotations

import os
from typing import Any

from app.services.report_builder import chunked, merge_reports


def audit_products(
    products: list[dict[str, Any]],
    store_url: str,
    language: str,
    analyzer,
) -> dict[str, Any]:

    if not products:
        raise ValueError("No products were provided for auditing.")

    batch_size = int(os.getenv("MAX_PRODUCTS_PER_BATCH", "5"))

    batches = chunked(products, batch_size)
    batch_reports: list[dict[str, Any]] = []

    for idx, batch in enumerate(batches, start=1):
        print(
            f"[AUDIT] Batch {idx}/{len(batches)} "
            f"({len(batch)} products)"
        )

        result = analyzer.analyze(
            batch,
            store_url,
            language,
        )

        batch_reports.append(result)

    return (
        merge_reports(batch_reports)
        if len(batch_reports) > 1
        else batch_reports[0]
    )