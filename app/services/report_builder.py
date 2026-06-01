# app/services/report_builder.py
"""FastAPI app for Shopify agent-discoverability enrichments."""

from __future__ import annotations

import datetime as dt
import html
import importlib
import json
import os
import urllib.error
import urllib.request
from typing import Any
from pathlib import Path

from app.core.config import get_app_settings
from app.services.product_fetcher import (
    ShopifyConfig,
    compact_product,
    fetch_products_public,
    normalize_store_url,
)

import tempfile


# Note: FastAPI app wiring was moved to app/main.py to separate frontend
# rendering and analysis logic from the API surface.

# ── exceptions ────────────────────────────────────────────────────────

class LLMQuotaExceededError(Exception):
    """Raised when the LLM provider returns a token / quota exhaustion error."""

class LLMRateLimitError(Exception):
    """Raised when the LLM provider rate-limits the request (retry later)."""

class LLMResponseError(Exception):
    """Raised when the LLM returns an unexpected or unparseable response."""

_QUOTA_SIGNALS = (
    "quota",
    "rate limit",
    "rate_limit",
    "too many requests",
    "resource_exhausted",         
    "insufficient_quota",         
    "billing",
    "exceeded",
    "token limit",
    "context_length_exceeded",   
    "maximum context length",
)

_RATE_SIGNALS = (
    "rate limit",
    "rate_limit",
    "too many requests",
    "retry",
    "slow down",
    "throttl",
)


def _classify_llm_error(message: str, status_code: int | None = None) -> None:
    lower = message.lower()

    if status_code == 429:
        raise LLMRateLimitError(
            "The AI provider is rate-limiting requests right now. "
            "Please wait a few minutes and try again."
        )

    if status_code == 402:
        raise LLMQuotaExceededError(
            "The AI provider billing limit has been reached. "
            "Please check your account quota."
        )

    if any(sig in lower for sig in _QUOTA_SIGNALS):
        raise LLMQuotaExceededError(
            "The AI provider quota or token limit has been exhausted. "
            f"Provider message: {message[:300]}"
        )

    if any(sig in lower for sig in _RATE_SIGNALS):
        raise LLMRateLimitError(
            "The AI provider is rate-limiting requests right now. "
            f"Provider message: {message[:300]}"
        )

def build_prompt(products: list[dict[str, Any]], store_url: str) -> str:
    return f"""
You are an ecommerce data strategist helping a Shopify merchant make products discoverable,
understandable, and safely recommendable by AI agents.

Analyze the product data below and identify enrichments to add. Focus on machine-readable
and user-useful fields that would help shopping agents answer questions, compare products,
match intent, verify fit, and complete purchase decisions.

Return practical recommendations, not generic SEO advice. Include missing structured data,
product attributes, identifiers, policy/context fields, natural-language agent summaries,
variant details, image metadata, FAQs, synonyms/search terms, compatibility/use cases, and
trust signals when relevant.

Store URL: {store_url}

Products:
{json.dumps(products, ensure_ascii=False, indent=2)}
""".strip()


def analyze_with_ollama(products: list[dict[str, Any]], store_url: str, model: str) -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": (
            build_prompt(products, store_url)
            + "\n\nReturn only valid JSON with keys: store_level_recommendations and products."
        ),
        "stream": False,
        "format": "json",
    }
    request = urllib.request.Request(
        os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate"),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        _classify_llm_error(message, error.code)
        raise LLMResponseError(f"Ollama HTTP {error.code}: {message[:300]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            "Could not reach Ollama. Make sure Ollama is installed and running locally."
        ) from error

    text = body.get("response", "")
    if body.get("error"):
        _classify_llm_error(body["error"])
        raise LLMResponseError(f"Ollama error: {body['error'][:300]}")

    try:
        report = json.loads(text)
    except json.JSONDecodeError as error:
        raise LLMResponseError(f"Ollama returned non-JSON output: {text[:500]}") from error

    report.setdefault("provider", "ollama")
    report.setdefault("store_url", store_url)
    return report


def enrichment_report_schema() -> dict[str, Any]:
    recommendation_schema = {
        "type": "object",
        "properties": {
            "priority": {
                "type": "string",
                "enum": ["high", "medium", "low"],
            },
            "enrichment": {"type": "string"},
            "why_it_matters_for_agents": {"type": "string"},
            "example": {"type": "string"},
        },
        "required": [
            "priority",
            "enrichment",
            "why_it_matters_for_agents",
            "example",
        ],
    }
    return {
        "type": "object",
        "properties": {
            "store_level_recommendations": {
                "type": "array",
                "items": recommendation_schema,
            },
            "products": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": ["integer", "string", "null"]},
                        "title": {"type": ["string", "null"]},
                      "agent_summary": {"type": "string"},
                        "missing_enrichments": {
                            "type": "array",
                            "items": recommendation_schema,
                        },
                    },
                    "required": [
                        "product_id",
                        "title",
                      "agent_summary",
                        "missing_enrichments",
                    ],
                },
            },
        },
        "required": ["store_level_recommendations", "products"],
    }


def analyze_with_gemini(products: list[dict[str, Any]], store_url: str, model: str) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env. You can create one in Google AI Studio.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": build_prompt(products, store_url)}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": enrichment_report_schema(),
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        try:
            error_body = json.loads(message)
            detail = error_body.get("error", {}).get("message", message)
        except json.JSONDecodeError:
            detail = message
        _classify_llm_error(detail, error.code)
        raise LLMResponseError(f"Gemini API HTTP {error.code}: {detail[:300]}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Could not reach Gemini API: {error.reason}") from error

    try:
        candidate = body["candidates"][0]
        finish_reason = candidate.get("finishReason", "")
        if finish_reason == "MAX_TOKENS":
            raise LLMQuotaExceededError(
                "Gemini hit the maximum token limit for this response. "
                "Try reducing MAX_PRODUCTS in your .env or switching to a model with a larger context window."
            )
        if finish_reason not in ("STOP", ""):
            raise LLMResponseError(
                f"Gemini returned an unexpected finish reason: {finish_reason}. "
                f"Full response: {json.dumps(body)[:500]}"
            )
        text = candidate["content"]["parts"][0]["text"]
        report = json.loads(text)
    except (KeyError, IndexError, json.JSONDecodeError) as error:
        raise LLMResponseError(
            f"Unexpected Gemini API response structure: {json.dumps(body)[:500]}"
        ) from error

    report.setdefault("provider", "Propero")
    # report.setdefault("model", model)
    report.setdefault("store_url", store_url)
    return report


def analyze_with_openai(products: list[dict[str, Any]], store_url: str, model: str) -> dict[str, Any]:
    try:
        openai_module = importlib.import_module("openai")
        OpenAI = getattr(openai_module, "OpenAI")
        APIStatusError = getattr(openai_module, "APIStatusError", None)
        RateLimitError = getattr(openai_module, "RateLimitError", None)
    except (ImportError, AttributeError) as error:
        raise RuntimeError(
            "Install the optional OpenAI SDK first: pip install openai"
        ) from error

    client = OpenAI()

    try:
        response = client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You return concise JSON for ecommerce enrichment work. "
                        "Prioritize specific, actionable changes."
                    ),
                },
                {"role": "user", "content": build_prompt(products, store_url)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "shopify_agent_discoverability_report",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "store_level_recommendations": {
                                "type": "array",
                                "items": {"$ref": "#/$defs/recommendation"},
                            },
                            "products": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "product_id": {"type": ["integer", "string", "null"]},
                                        "title": {"type": ["string", "null"]},
                                      "agent_summary": {"type": "string"},
                                        "missing_enrichments": {
                                            "type": "array",
                                            "items": {"$ref": "#/$defs/recommendation"},
                                        },
                                    },
                                    "required": [
                                    "product_id",
                                    "title",
                                  "agent_summary",
                                    "missing_enrichments",
                                    ],
                                },
                            },
                        },
                        "required": ["store_level_recommendations", "products"],
                        "$defs": {
                            "recommendation": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "priority": {
                                        "type": "string",
                                        "enum": ["high", "medium", "low"],
                                    },
                                    "enrichment": {"type": "string"},
                                    "why_it_matters_for_agents": {"type": "string"},
                                    "example": {"type": "string"},
                                },
                                "required": [
                                    "priority",
                                    "enrichment",
                                    "why_it_matters_for_agents",
                                    "example",
                            ],
                        }
                        },
                    },
                }
            },
        )
    except Exception as error:
        if RateLimitError and isinstance(error, RateLimitError):
            raise LLMRateLimitError(
                "OpenAI is rate-limiting requests right now. Please wait and try again."
            ) from error
        if APIStatusError and isinstance(error, APIStatusError):
            _classify_llm_error(str(error), getattr(error, "status_code", None))
        _classify_llm_error(str(error))
        raise LLMResponseError(f"OpenAI API error: {str(error)[:300]}") from error

    try:
        report = json.loads(response.output_text)
    except (json.JSONDecodeError, AttributeError) as error:
        raise LLMResponseError(
            f"OpenAI returned unparseable output: {str(response)[:300]}"
        ) from error

    report.setdefault("provider", "openai")
    report.setdefault("store_url", store_url)
    return report


def analyze_products(products: list[dict[str, Any]], store_url: str, provider: str, model: str) -> dict[str, Any]:
    if provider == "gemini":
        return analyze_with_gemini(products, store_url, model)
    if provider == "ollama":
        return analyze_with_ollama(products, store_url, model)
    if provider == "openai":
        return analyze_with_openai(products, store_url, model)
    raise ValueError(f"Unsupported provider: {provider!r}")


def escape_html(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def priority_class(priority: str | None) -> str:
    if priority in {"high", "medium", "low"}:
        return priority
    return "medium"





def render_recommendations(recommendations: list[dict[str, Any]]) -> str:
    if not recommendations:
        return '<p class="muted">No recommendations returned.</p>'

    items = []
    for rec in recommendations:
        priority = priority_class(rec.get("priority"))
        items.append(
            f"""
            <article class="recommendation">
              <div class="recommendation__header">
                <span class="pill pill--{priority}">{escape_html(priority)}</span>
                <h4>{escape_html(rec.get("enrichment"))}</h4>
              </div>
              <p>{escape_html(rec.get("why_it_matters_for_agents"))}</p>
              <div class="example"><strong>Example:</strong> {escape_html(rec.get("example"))}</div>
            </article>
            """
        )
    return "\n".join(items)


def render_executive_summary(report: dict[str, Any], product_reports: list[dict[str, Any]]) -> str:
    # Determine catalog-level counts and products needing attention (by high-priority gaps)
    high_priority_count = sum(
        1
        for product in product_reports
        for rec in product.get("missing_enrichments", [])
        if rec.get("priority") == "high"
    )
    store_recommendations = report.get("store_level_recommendations") or []
    top_store_actions = store_recommendations[:3]

    observations: list[str] = []
    if high_priority_count:
        observations.append(
            f"There are {high_priority_count} high-priority gaps across the catalog, "
            "concentrated in the kinds of fields agents need to recommend products confidently."
        )
    if not observations:
        observations.append(
            "This report summarizes the current catalog readiness and the most useful fixes "
            "to make products easier for AI agents to discover and recommend."
        )

    highlight_cards = [
        ("Catalog size", str(len(product_reports)), "Number of products analyzed."),
        ("High-priority gaps", str(high_priority_count), "Issues most likely to block accurate agent recommendations."),
        ("Store actions", str(len(store_recommendations)), "Catalog-wide improvements that benefit every product."),
    ]

    store_action_items = [
        f"<li><strong>{escape_html(rec.get('enrichment'))}</strong>"
        f"<span>{escape_html(rec.get('why_it_matters_for_agents'))}</span></li>"
        for rec in top_store_actions
    ]

    # Products needing attention: pick those with the most high-priority missing enrichments
    attention_products = sorted(
        product_reports,
        key=lambda p: sum(1 for r in p.get("missing_enrichments", []) if r.get("priority") == "high"),
        reverse=True,
    )[:3]

    attention_items = [
        f"<li><strong>{escape_html(p.get('title') or 'Untitled product')}</strong>"
        f"<span>{sum(1 for r in p.get('missing_enrichments', []) if r.get('priority') == 'high')} high-priority gaps</span></li>"
        for p in attention_products
    ]

    cards_html = "".join(
        f"""
        <article class="summary-card">
          <p class="eyebrow">{escape_html(label)}</p>
          <strong>{escape_html(value)}</strong>
          <p>{escape_html(description)}</p>
        </article>
        """
        for label, value, description in highlight_cards
    )

    return f"""
      <section class="section executive-summary">
        <div class="summary-heading">
          <div>
            <p class="eyebrow">Executive Summary</p>
            <h2>Overall observations</h2>
          </div>
          <p class="summary-intro">{' '.join(observations)}</p>
        </div>
        <div class="summary-grid">
          {cards_html}
        </div>
        <div class="summary-columns">
          <article class="summary-panel">
            <h3>Top store-level actions</h3>
            <ul class="summary-list">
              {''.join(store_action_items) if store_action_items else '<li><span>No store-level recommendations returned.</span></li>'}
            </ul>
          </article>
          <article class="summary-panel">
            <h3>Products needing the most attention</h3>
            <ul class="summary-list">
              {''.join(attention_items) if attention_items else '<li><span>No products returned.</span></li>'}
            </ul>
          </article>
        </div>
      </section>
    """


def render_pdf_html(report: dict[str, Any], products: list[dict[str, Any]], store_url: str) -> str:
    generated_at = dt.datetime.now().strftime("%b %d, %Y %I:%M %p")
    product_reports = report.get("products") or []
    high_priority_count = sum(
        1
        for product in product_reports
        for rec in product.get("missing_enrichments", [])
        if rec.get("priority") == "high"
    )

    product_cards = [
        f"""
        <section class="product-card">
          <div class="product-card__top">
            <div>
              <p class="eyebrow">Product</p>
              <h3>{escape_html(product.get("title") or "Untitled product")}</h3>
              <p class="muted">ID: {escape_html(product.get("product_id"))}</p>
            </div>
          </div>
          <p class="summary">{escape_html(product.get("agent_summary"))}</p>
          <div class="recommendation-list">
            {render_recommendations(product.get("missing_enrichments") or [])}
          </div>
        </section>
        """
        for product in product_reports
    ]

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>AI Agent Discoverability Report</title>
  <style>
    @page {{
      size: A4;
      margin: 18mm 15mm;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      margin: 0;
      color: #18212f;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 11px;
      line-height: 1.5;
      background: #f6f2ea;
    }}
    .report {{
      background: #fffdf8;
      border: 1px solid #ded6c8;
      min-height: 100vh;
    }}
    .hero {{
      padding: 34px 38px 28px;
      color: #f9f4ea;
      background: linear-gradient(135deg, #16302b 0%, #22594f 48%, #b86b3d 100%);
    }}
    .hero h1 {{
      max-width: 680px;
      margin: 10px 0 12px;
      font-size: 34px;
      line-height: 1.05;
      font-weight: 760;
      letter-spacing: 0;
    }}
    .hero p {{
      max-width: 620px;
      margin: 0;
      color: #f2e7d4;
      font-size: 13px;
    }}
    .eyebrow {{
      margin: 0 0 5px;
      color: inherit;
      font-size: 9px;
      font-weight: 750;
      letter-spacing: .08em;
      text-transform: uppercase;
      opacity: .72;
    }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      padding: 18px 38px;
      background: #efe6d8;
      border-bottom: 1px solid #ded6c8;
    }}
    .metric {{
      padding: 12px;
      background: #fffdf8;
      border: 1px solid #d9d0c0;
      border-radius: 8px;
    }}
    .metric strong {{
      display: block;
      margin-top: 2px;
      color: #172a3a;
      font-size: 18px;
      line-height: 1.1;
    }}
    main {{
      padding: 28px 38px 36px;
    }}
    h2 {{
      margin: 0 0 12px;
      color: #172a3a;
      font-size: 19px;
      line-height: 1.2;
    }}
    h3 {{
      margin: 0;
      color: #172a3a;
      font-size: 17px;
      line-height: 1.25;
    }}
    h4 {{
      margin: 0;
      color: #172a3a;
      font-size: 12px;
      line-height: 1.3;
    }}
    .section {{
      margin-bottom: 28px;
    }}
        .executive-summary {{
            break-after: page;
            margin-bottom: 34px;
        }}
        .summary-heading {{
            display: grid;
            grid-template-columns: minmax(220px, 0.95fr) minmax(0, 1.35fr);
            gap: 20px;
            align-items: start;
            margin-bottom: 16px;
        }}
        .summary-intro {{
            margin: 0;
            padding: 14px 16px;
            color: #243246;
            background: #f4efe6;
            border: 1px solid #ded6c8;
            border-radius: 10px;
            font-size: 12px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 14px;
        }}
        .summary-card {{
            padding: 14px;
            background: #ffffff;
            border: 1px solid #ded6c8;
            border-radius: 10px;
            break-inside: avoid;
        }}
        .summary-card strong {{
            display: block;
            margin: 4px 0 8px;
            color: #172a3a;
            font-size: 24px;
            line-height: 1;
        }}
        .summary-card p {{
            margin: 0;
            color: #4b5567;
        }}
        .summary-columns {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }}
        .summary-panel {{
            padding: 14px 15px;
            background: #ffffff;
            border: 1px solid #ded6c8;
            border-radius: 10px;
            break-inside: avoid;
        }}
        .summary-panel h3 {{
            margin-bottom: 10px;
            font-size: 15px;
        }}
        .summary-list {{
            margin: 0;
            padding-left: 18px;
            color: #324150;
        }}
        .summary-list li + li {{
            margin-top: 8px;
        }}
        .summary-list strong {{
            display: block;
            margin-bottom: 1px;
            color: #172a3a;
        }}
        .summary-list span {{
            display: block;
            color: #4b5567;
        }}
    .recommendation-list {{
      display: grid;
      gap: 10px;
    }}
    .recommendation {{
      padding: 12px 13px;
      background: #ffffff;
      border: 1px solid #ded6c8;
      border-radius: 8px;
      break-inside: avoid;
    }}
    .recommendation__header {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
      margin-bottom: 7px;
    }}
    .recommendation p {{
      margin: 0 0 8px;
      color: #3f4a5a;
    }}
    .example {{
      padding: 8px 9px;
      color: #324150;
      background: #f4efe6;
      border-left: 3px solid #c47d52;
      border-radius: 5px;
    }}
    .pill {{
      display: inline-block;
      min-width: 44px;
      padding: 3px 7px;
      border-radius: 999px;
      color: #ffffff;
      font-size: 8px;
      font-weight: 800;
      text-align: center;
      text-transform: uppercase;
      letter-spacing: .05em;
    }}
    .pill--high {{
      background: #b43d31;
    }}
    .pill--medium {{
      background: #b87524;
    }}
    .pill--low {{
      background: #3d756b;
    }}
    .product-card {{
      margin-bottom: 18px;
      padding: 18px;
      background: #ffffff;
      border: 1px solid #ded6c8;
      border-radius: 8px;
      break-inside: avoid;
    }}
    .product-card__top {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
    }}
    .score {{
      width: 62px;
      height: 62px;
      flex: 0 0 62px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      border-radius: 50%;
      color: #ffffff;
    }}
    .score span {{
      font-size: 20px;
      font-weight: 800;
      line-height: 1;
    }}
    .score small {{
      font-size: 8px;
      text-transform: uppercase;
      letter-spacing: .06em;
    }}
    .score--strong {{
      background: #2e7169;
    }}
    .score--fair {{
      background: #b87524;
    }}
    .score--weak, .score--unknown {{
      background: #b43d31;
    }}
    .summary {{
      margin: 0 0 14px;
      color: #3a4757;
      font-size: 12px;
    }}
    .muted {{
      margin: 0;
      color: #667085;
    }}
    .footer {{
      padding: 14px 38px 24px;
      color: #667085;
      border-top: 1px solid #ded6c8;
    }}
  </style>
</head>
<body>
  <div class="report">
    <header class="hero">
      <p class="eyebrow">Shopify AI Agent Readiness</p>
      <h1>AI Agent Discoverability Report</h1>
      <p>{escape_html(store_url)} · Generated {escape_html(generated_at)} · Provider: {escape_html(report.get("provider", "unknown"))} {escape_html(report.get("model", ""))}</p>
    </header>

    <section class="meta-grid">
      <div class="metric"><span class="eyebrow">Products Analyzed</span><strong>{len(products)}</strong></div>
      <div class="metric"><span class="eyebrow">High Priority</span><strong>{high_priority_count}</strong></div>
      <div class="metric"><span class="eyebrow">Store Actions</span><strong>{len(report.get("store_level_recommendations") or [])}</strong></div>
    </section>

    <main>
            {render_executive_summary(report, product_reports)}

      <section class="section">
        <h2>Store-Level Recommendations</h2>
        <div class="recommendation-list">
          {render_recommendations(report.get("store_level_recommendations") or [])}
        </div>
      </section>

      <section class="section">
        <h2>Product Recommendations</h2>
        {"".join(product_cards) if product_cards else '<p class="muted">No product recommendations returned.</p>'}
      </section>
    </main>

    <footer class="footer">
      Generated from Shopify product data. Review recommendations before publishing product or policy changes.
    </footer>
  </div>
</body>
</html>
"""


def write_pdf_report(html_path: str, pdf_path: str) -> bool:
    try:
        weasyprint_module = importlib.import_module("weasyprint")
        HTML = getattr(weasyprint_module, "HTML")
        HTML(filename=html_path).write_pdf(pdf_path)
        return True
    except Exception:
        pass

    # Fallback: Playwright
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(f"file:///{html_path.replace(os.sep, '/')}")
            page.pdf(path=pdf_path, format="A4", margin={
                "top": "18mm", "bottom": "18mm",
                "left": "15mm", "right": "15mm"
            })
            browser.close()
        return True
    except Exception:
        return False

def run_store_analysis(store_url: str) -> dict[str, Any]:
    settings = get_app_settings()
    normalized_store_url = normalize_store_url(store_url)
    config = ShopifyConfig(
        store_url=normalized_store_url,
        api_version=settings["api_version"],
    )
    raw_products = fetch_products_public(normalized_store_url, settings["max_products"])
    products = [compact_product(product, normalized_store_url) for product in raw_products]
    report = None
    if products:
        report = analyze_products(products, normalized_store_url, settings["provider"], settings["model"])

    return {
        "settings": settings,
        "store_url": normalized_store_url,
        "products": products,
        "report": report,
    }


def build_pdf_attachment(report: dict[str, Any], products: list[dict[str, Any]], store_url: str) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        html_path = temp_path / "report.html"
        pdf_path = temp_path / "report.pdf"
        html_path.write_text(render_pdf_html(report, products, store_url), encoding="utf-8")

        if not write_pdf_report(str(html_path), str(pdf_path)):
            raise RuntimeError("PDF conversion is unavailable. Install weasyprint to enable PDF email delivery.")

        return pdf_path.read_bytes(), pdf_path.name


# The API routes were intentionally removed from this module so the package
# `app` can own the FastAPI instance (see app/main.py). This file continues to
# provide the analysis and rendering helpers which can be used by the API or
# invoked directly from a CLI/script.
