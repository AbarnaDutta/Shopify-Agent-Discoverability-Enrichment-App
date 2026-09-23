#app/services/audit_engine.py
from __future__ import annotations

from typing import Any
import time

from app.services.product_fetcher import compact_product
from app.services.report_builder import (
    LLMAdapter,
    get_llm_adapter,
    get_bedrock_adapter,
    merge_reports,
    assemble_report_from_verdicts,
)

from app.services.scoring_rubric import CHECKS


class AuditRunResult:
    def __init__(
        self,
        *,
        products: list[dict[str, Any]],
        report: dict[str, Any],
        provider: str,
        model: str,
        product_count: int,
        batches: int,
        duration_s: float,
    ):
        self.products = products
        self.report = report
        self.provider = provider
        self.model = model
        self.product_count = product_count
        self.batches = batches
        self.duration_s = duration_s


def _chunk(items: list[dict[str, Any]], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def audit_products(
    *,
    raw_products,
    store_context,
    store_url,
    provider,
    model,
    language="English",
    batch_size=5,
    fallback_to_bedrock=True,
    analyzer=None,
) -> AuditRunResult:
    started = time.time()

    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")

    products = raw_products
    batches = list(_chunk(products, batch_size))

    if not batches:
        raise ValueError("No products supplied for audit")

    analyzer: LLMAdapter = analyzer or get_llm_adapter(provider, model)
    used_provider = provider
    used_model = getattr(analyzer, "model", model)
    reports: list[dict[str, Any]] = []

    for index, batch in enumerate(batches, start=1):
        print("=" * 80)
        print(f"[Audit] Batch {index}/{len(batches)}")
        print(f"[Audit] Provider: {used_provider} | Model: {used_model}")
        print(f"[Audit] Products: {len(batch)}")

        batch_started = time.time()

        try:
            print(f"[DEBUG] Sending batch {index} to Gemini")
            print(f"[DEBUG] Batch product count: {len(batch)}")
            print(f"[DEBUG] Product IDs: {[p.get('id') for p in batch]}")

            result = analyzer.analyze(
                batch,
                store_context or {},
                store_url,
                language,
            )

            print(f"[DEBUG] Gemini returned successfully for batch {index}")
            import json

            print(f"[DEBUG] Batch {index} product count: {len(batch)}")

            for p in batch:
                print(
                    f"[DEBUG] Product: {p.get('id')} | "
                    f"title={p.get('title', '')[:80]} | "
                    f"json_size={len(json.dumps(p, ensure_ascii=False))} chars"
                )

            print(
                f"[DEBUG] Batch {index} total product JSON size: "
                f"{len(json.dumps(batch, ensure_ascii=False))} chars"
            )

            print(
                f"[DEBUG] Store context JSON size: "
                f"{len(json.dumps(store_context or {}, ensure_ascii=False))} chars"
            )

        except Exception as e:
            import traceback

            print(f"[DEBUG] Gemini exception type: {type(e).__name__}")
            print(f"[DEBUG] Gemini exception: {e}")
            traceback.print_exc()

            if not fallback_to_bedrock or used_provider == "bedrock":
                raise

            print("[Audit] Primary provider failed; falling back to Bedrock for this batch.")

            analyzer = get_bedrock_adapter()
            used_provider = "bedrock"
            used_model = getattr(analyzer, "model", "unknown")

            result = analyzer.analyze(
                batch,
                store_context or {},
                store_url,
                language,
            )

            print("[Audit] Primary provider failed; falling back to Bedrock for this batch.")
            analyzer = get_bedrock_adapter()
            used_provider = "bedrock"
            used_model = getattr(analyzer, "model", "unknown")
            result = analyzer.analyze(
                batch,
                store_context or {},
                store_url,
                language,
            )

        reports.append(result)
        print(f"[Audit] Batch completed in {time.time() - batch_started:.2f}s")

    raw_report = merge_reports(reports)

    report = assemble_report_from_verdicts(
        raw_report,
        products=products,         
        store_context=store_context, 
    )

    report["provider"] = used_provider
    report["model"] = used_model
    report["store_url"] = store_url

    return AuditRunResult(
        products=products,
        report=report,
        provider=used_provider,
        model=used_model,
        product_count=len(products),
        batches=len(batches),
        duration_s=round(time.time() - started, 2),
    )
