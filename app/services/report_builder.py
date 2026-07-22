# app/services/report_builder.py
"""FastAPI app for Shopify agent-discoverability enrichments."""

from __future__ import annotations

import datetime as dt
import difflib
import html
import importlib
import json
import os
import urllib.error
import urllib.request
from typing import Any
from pathlib import Path
import time
from app.core.config import get_app_settings
import random
from app.services.product_fetcher import (
    ShopifyConfig,
    compact_product,
    fetch_products_public,
    normalize_store_url,
    EmptyStoreError,
)

import tempfile

from typing import Protocol

class LLMAdapter(Protocol):
    """Common interface all LLM adapters must satisfy."""
    def analyze(
        self,
        products: list[dict[str, Any]],
        store_url: str,
        language: str,
    ) -> dict[str, Any]:
        ...


class GeminiAdapter:
    def __init__(self, model: str) -> None:
        self.model = model

    def analyze(self, products, store_url, language="English"):
        return analyze_with_gemini(products, store_url, self.model, language)


class BedrockAdapter:
    def __init__(self, model: str = "global.anthropic.claude-opus-4-5-20251101-v1:0") -> None:
        self.model = model

    def analyze(self, products, store_url, language="English"):
        return analyze_with_bedrock_claude(products, store_url, self.model, language)


class OpenAIAdapter:
    def __init__(self, model: str) -> None:
        self.model = model

    def analyze(self, products, store_url, language="English"):
        return analyze_with_openai(products, store_url, self.model, language)


class OllamaAdapter:
    def __init__(self, model: str) -> None:
        self.model = model

    def analyze(self, products, store_url, language="English"):
        return analyze_with_ollama(products, store_url, self.model, language)


def get_llm_adapter(provider: str, model: str) -> LLMAdapter:
    """Factory — returns the correct adapter for the configured provider."""
    if provider == "gemini":
        return GeminiAdapter(model)
    if provider == "bedrock":
        return BedrockAdapter(model)
    if provider == "openai":
        return OpenAIAdapter(model)
    if provider == "ollama":
        return OllamaAdapter(model)
    raise ValueError(f"Unsupported provider: {provider!r}")


def get_bedrock_adapter() -> LLMAdapter:
    """Always returns a Bedrock adapter — used for fallback/load balancing."""
    model = os.getenv(
        "BEDROCK_FALLBACK_MODEL",
        "global.anthropic.claude-opus-4-5-20251101-v1:0",
    )
    return BedrockAdapter(model)

import threading
_gemini_last_call = {"t": 0}
_gemini_lock = threading.Lock()

def _gemini_rate_limit():
    with _gemini_lock:
        wait = 20 - (time.time() - _gemini_last_call["t"])
        if wait > 0:
            print(f"[GeminiRateLimit] Waiting {wait:.1f}s before next call...")
            time.sleep(wait)
        _gemini_last_call["t"] = time.time()


# Note: FastAPI app wiring was moved to app/main.py to separate frontend
# rendering and analysis logic from the API surface.

# ── exceptions ────────────────────────────────────────────────────────

class LLMQuotaExceededError(Exception):
    """Raised when the LLM provider returns a token / quota exhaustion error."""

class LLMRateLimitError(Exception):
    """Raised when the LLM provider rate-limits the request (retry later)."""

class LLMResponseError(Exception):
    """Raised when the LLM returns an unexpected or unparseable response."""

class LLMAuthError(Exception):
    """Raised when the LLM provider rejects the request due to auth / key issues."""

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

_AUTH_SIGNALS = (
    "api key",
    "api_key",
    "leaked",
    "expired", 
    "invalid key",
    "unauthorized",
    "authentication",
    "permission denied",
    "forbidden",
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
    
    if status_code in (400, 403) or any(sig in lower for sig in _AUTH_SIGNALS):
        raise LLMAuthError(
            "The AI provider rejected the request due to an authentication error. "
            "Please contact support."
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

def build_prompt(products: list[dict[str, Any]], store_url: str, language: str = "English") -> str:
    return f"""
You are an ecommerce data strategist helping a Shopify merchant prepare their store for AI commerce
agents that use Shopify's Universal Commerce Protocol (UCP) and Storefront Model Context Protocol (MCP).
Your job is to make products discoverable, understandable, and safely recommendable/actionable by
those agents.

Analyze the raw Shopify product data provided below. Your task is to:
- Assess the store's readiness for agentic commerce (UCP-style agents that search, compare, build
  carts, and create checkouts) and produce numeric readiness scores.
- Identify and generate deep structural data enrichments to help autonomous AI shopping agents answer
  customer queries, compare features, verify fitment, match user intent, and safely execute purchase
  decisions.

Analyze the raw payload attributes and extract/build out:
1. Missing explicit identifiers (e.g., GTIN, MPN, precise global synonyms).
2. Deep variant attributes (e.g., precise material blends, sizing dimensions, exact color tokens),
   and flag any variant hygiene issues that would confuse an agent building a cart (e.g. many
   "Default Title" variants, inconsistent option names like "Option1"/"Custom1", zero-priced or
   placeholder variants).
3. Clear compatibility rules, target use cases, and negative use cases (when NOT to recommend, or
   when an agent should not act without human review).
4. Natural language agent summaries designed specifically to be parsed by LLM search vector indexes.
5. Trust signals, strict policy context, and a machine-readable FAQ map.
6. A `readiness_scores` object with integer scores from 0-100 for:
   - overall: holistic agentic-commerce readiness
   - ucp_commerce_flows: can an agent reliably search, filter, compare, build carts and check out
     using this catalog's structure?
   - mcp_knowledge: how clear/complete is the information an MCP-style agent would need to answer
     shopper questions (policies, FAQs, trust signals) based on what's inferable from this data?
   - catalog_enrichment: depth/consistency of product data (identifiers, variants, descriptions)
   - safety_policies: clarity of negative-use-cases and guardrails for when agents should NOT
     autonomously recommend or transact

CRITICAL CONSTRAINTS:
- Write the entire response, including all values, summaries, and structural examples, strictly in the requested language: {language}.
- Do not mix languages.
- Ensure all numbers use standard floats/integers where applicable, and do not append descriptive text inside clean value arrays.
- readiness_scores values must be plain integers between 0 and 100 (no % sign, no text).

Store URL: {store_url}

Products Catalogue Payload:
{json.dumps(products, ensure_ascii=False, indent=2)}
""".strip()

def analyze_with_ollama(products: list[dict[str, Any]], store_url: str, model: str, language="English") -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": (
            build_prompt(products, store_url, language)
            + "\n\nReturn only valid JSON with keys: readiness_scores, store_level_recommendations and products."
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
        "type": "OBJECT",
        "properties": {
            "priority": {
                "type": "STRING",
                "enum": ["high", "medium", "low"],
            },
            "enrichment":                  {"type": "STRING"},
            "why_it_matters_for_agents":   {"type": "STRING"},
            "example":                     {"type": "STRING"},
        },
        "required": [
            "priority",
            "enrichment",
            "why_it_matters_for_agents",
            "example",
        ],
    }
    readiness_scores_schema = {
        "type": "OBJECT",
        "properties": {
            "overall":             {"type": "INTEGER"},
            "ucp_commerce_flows":  {"type": "INTEGER"},
            "mcp_knowledge":       {"type": "INTEGER"},
            "catalog_enrichment":  {"type": "INTEGER"},
            "safety_policies":     {"type": "INTEGER"},
        },
        "required": [
            "overall",
            "ucp_commerce_flows",
            "mcp_knowledge",
            "catalog_enrichment",
            "safety_policies",
        ],
    }
    return {
        "type": "OBJECT",
        "properties": {
            "readiness_scores": readiness_scores_schema,
            "store_level_recommendations": {
                "type": "ARRAY",
                "items": recommendation_schema,
            },
            "products": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "product_id":          {"type": "STRING"},
                        "title":               {"type": "STRING"},
                        "agent_summary":       {"type": "STRING"},
                        "missing_enrichments": {
                            "type": "ARRAY",
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
        "required": ["readiness_scores", "store_level_recommendations", "products"],
    }


def analyze_with_gemini(products: list[dict[str, Any]], store_url: str, model: str, language="English") -> dict[str, Any]:
    _gemini_rate_limit()
    request_id = random.randint(10000, 99999)

    print(f"[Gemini-{request_id}] Starting")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env. You can create one in Google AI Studio.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = build_prompt(products, store_url, language)
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": enrichment_report_schema(),
         },
    }

    body = None
    last_error = None
    max_attempts = 5
    base_delay = 10
    max_delay = 90
    print("=" * 80)
    print(f"[Gemini-{request_id}] Starting request")
    print(f"[Gemini-{request_id}] Model: {model}")
    print(f"[Gemini-{request_id}] Store: {store_url}")
    print(f"[Gemini-{request_id}] Product count: {len(products)}")
    print(
        f"[Gemini-{request_id}] Prompt length: {len(prompt):,} chars"
    )
    print("=" * 80)

    for attempt in range(max_attempts):
        if attempt > 0:
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += random.uniform(0, min(5, delay * 0.3))
            print(f"[Gemini-{request_id}] Attempt {attempt + 1}/{max_attempts}, waiting {delay:.1f}s after 429/503...")
            time.sleep(delay)
        print(f"[Gemini-{request_id}] Attempt {attempt + 1}/{max_attempts}")
        print(f"[Gemini-{request_id}] Payload size: {len(json.dumps(payload))} bytes")
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
            print(f"[Gemini-{request_id}] HTTP request successful")
            print("=" * 80)
            print(f"[Gemini-{request_id}] RESPONSE")
            print(json.dumps(body, indent=2)[:5000])
            print("=" * 80)
            print(f"[Gemini-{request_id}] Candidate count:", len(body.get("candidates", [])))

            if body.get("candidates"):
                print(
                    f"[Gemini-{request_id}] Finish reason:",
                    body["candidates"][0].get("finishReason")
                )
            last_error = None
            break

        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")

            print("=" * 80)
            print(f"[Gemini-{request_id}] HTTP ERROR]")
            print("Status:", error.code)
            print("Response:")
            print(message)
            print("=" * 80)
            if error.code in (429, 503):
                retry_after = error.headers.get("Retry-After")
                wait_time = int(retry_after) if retry_after else min(max_delay, base_delay * (2 ** attempt))
                last_error = LLMRateLimitError(f"Gemini HTTP {error.code}: {message[:300]}")
                print(f"[Gemini-{request_id}] HTTP {error.code} on attempt {attempt + 1}, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            try:
                detail = json.loads(message).get("error", {}).get("message", message)
            except json.JSONDecodeError:
                detail = message

            _classify_llm_error(detail, error.code)
            raise LLMResponseError(f"Gemini API HTTP {error.code}: {detail[:300]}") from error

        except urllib.error.URLError as error:
            raise RuntimeError(f"Could not reach Gemini API: {error.reason}") from error

    if last_error:
        fallback_model = "global.anthropic.claude-opus-4-5-20251101-v1:0"
        if os.getenv("BEDROCK_FALLBACK_ENABLED", "true").lower() == "true":
            print(
                f"[Gemini-{request_id}] All attempts failed, "
                f"falling back to Bedrock Claude ({fallback_model})..."
            )
            return analyze_with_bedrock_claude(
                products, store_url, fallback_model, language
            )
        raise last_error

    if not body:
        raise LLMResponseError("Gemini API execution finished without returning data payloads.")

    try:
        print(f"[Gemini-{request_id}] Parsing response...")
        print(f"[Gemini-{request_id}] Candidates:", len(body.get("candidates", [])))
        candidate = body["candidates"][0]
        finish_reason = candidate.get("finishReason", "")
        if finish_reason == "MAX_TOKENS":
            raise LLMQuotaExceededError(
                "Gemini hit the maximum token limit for this response. "
                "Try reducing MAX_PRODUCTS_PER_BATCH in your .env or switching to a model with a larger context window."
            )
        if finish_reason not in ("STOP", ""):
            raise LLMResponseError(
                f"Gemini returned an unexpected finish reason: {finish_reason}. "
                f"Full response: {json.dumps(body)[:500]}"
            )
        text = candidate["content"]["parts"][0]["text"]

        print("RAW RESPONSE:")
        print(text[:3000])

        try:
            report = json.loads(text)
        except json.JSONDecodeError:
            raise LLMResponseError(
                f"Gemini returned plain text instead of JSON:\n{text[:1000]}"
            )
    except (KeyError, IndexError, json.JSONDecodeError) as error:
        raise LLMResponseError(
            f"Unexpected Gemini API response structure: {json.dumps(body)[:500]}"
        ) from error

    report.setdefault("provider", "Propero")
    report.setdefault("store_url", store_url)
    
    return report

def analyze_with_bedrock_claude(
    products: list[dict[str, Any]],
    store_url: str,
    model: str = "global.anthropic.claude-opus-4-5-20251101-v1:0",
    language: str = "English",
) -> dict[str, Any]:
    bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK")
    region = "ap-south-1"

    if not bearer_token:
        raise LLMAuthError(
            "AWS_BEARER_TOKEN_BEDROCK is not set. "
            "Please add it to your .env file."
        )

    url = (
        f"https://bedrock-runtime.{region}.amazonaws.com"
        f"/model/{model}/invoke"
    )

    prompt = build_prompt(products, store_url, language)

    system = (
       "You are an expert e-commerce data strategist and data engineer. "
    "Your job is to analyze raw Shopify product data catalogs and return structured, "
    "highly actionable JSON enrichments to make products perfectly discoverable by AI shopping agents. "
    "You must prioritize specific, technical, machine-readable attributes (like exact dimensions, materials, "
    "GTIN/MPN identifiers, precise compatibility mappings, and structured FAQs). "
    "Do not include generic marketing fluff or standard SEO advice. "
    "You must return ONLY a raw JSON object that strictly adheres to the requested JSON schema. "
    "Do not include any markdown formatting, backticks (```json), or introductory/concluding prose text."
    "Return ONLY valid JSON matching this exact schema — no markdown, no preamble:\n"
        '{"readiness_scores": {"overall": 0, "ucp_commerce_flows": 0, "mcp_knowledge": 0, '
        '"catalog_enrichment": 0, "safety_policies": 0}, '
        '"store_level_recommendations": [{"priority": "high|medium|low", '
        '"enrichment": "...", "why_it_matters_for_agents": "...", "example": "..."}], '
        '"products": [{"product_id": "...", "title": "...", "agent_summary": "...", '
        '"missing_enrichments": [{"priority": "...", "enrichment": "...", '
        '"why_it_matters_for_agents": "...", "example": "..."}]}]} '
        "readiness_scores values are integers 0-100."
    )

    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8000,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {bearer_token}",
        },
        method="POST",
    )
    print(f"[Bedrock] Starting request | model: {model} | products: {len(products)} | store: {store_url}")

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode("utf-8"))
        print(f"[Bedrock] Request completed successfully")
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")
        print(f"[Bedrock] HTTP {error.code}: {message[:300]}")
        if error.code == 429:
            raise LLMRateLimitError(
                "AWS Bedrock is rate-limiting requests. Please try again shortly."
            ) from error
        if error.code in (401, 403):
            raise LLMAuthError(
                "AWS Bedrock rejected the bearer token. Check AWS_BEARER_TOKEN_BEDROCK."
            ) from error
        raise LLMResponseError(
            f"Bedrock HTTP {error.code}: {message[:300]}"
        ) from error
    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Could not reach Bedrock endpoint: {error.reason}"
        ) from error

    try:
        text = body["content"][0]["text"].strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        report = json.loads(text)
    except (KeyError, IndexError) as error:
        raise LLMResponseError(
            f"Unexpected Bedrock response structure: {str(body)[:300]}"
        ) from error
    except json.JSONDecodeError as error:
        raise LLMResponseError(
            f"Bedrock returned non-JSON: {text[:500]}"
        ) from error

    report.setdefault("provider", "Propero")
    report.setdefault("store_url", store_url)
    return report

def analyze_with_openai(products: list[dict[str, Any]], store_url: str, model: str, language="English") -> dict[str, Any]:
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
                {"role": "user", "content": build_prompt(products, store_url, language)},
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
                            "readiness_scores": {"$ref": "#/$defs/readiness_scores"},
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
                        "required": ["readiness_scores", "store_level_recommendations", "products"],
                        "$defs": {
                            "readiness_scores": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "overall": {"type": "integer"},
                                    "ucp_commerce_flows": {"type": "integer"},
                                    "mcp_knowledge": {"type": "integer"},
                                    "catalog_enrichment": {"type": "integer"},
                                    "safety_policies": {"type": "integer"},
                                },
                                "required": [
                                    "overall",
                                    "ucp_commerce_flows",
                                    "mcp_knowledge",
                                    "catalog_enrichment",
                                    "safety_policies",
                                ],
                            },
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


def analyze_products(
    products: list[dict[str, Any]],
    store_url: str,
    provider: str,
    model: str,
    language: str = "English",
) -> dict[str, Any]:
    if provider == "gemini":
        return analyze_with_gemini(products, store_url, model, language)
    if provider == "ollama":
        return analyze_with_ollama(products, store_url, model, language)
    if provider == "openai":
        return analyze_with_openai(products, store_url, model, language)
    if provider == "bedrock":
        return analyze_with_bedrock_claude(products, store_url, model, language)
    raise ValueError(f"Unsupported provider: {provider!r}")

def escape_html(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


_READINESS_KEYS = (
    "overall",
    "ucp_commerce_flows",
    "mcp_knowledge",
    "catalog_enrichment",
    "safety_policies",
)


def normalize_readiness_scores(raw: Any) -> dict[str, int]:
    """Clamp/validate readiness scores from an LLM response; fills gaps with 0."""
    raw = raw if isinstance(raw, dict) else {}
    scores: dict[str, int] = {}
    for key in _READINESS_KEYS:
        try:
            value = int(round(float(raw.get(key, 0))))
        except (TypeError, ValueError):
            value = 0
        scores[key] = max(0, min(100, value))
    return scores


def priority_class(priority: str | None) -> str:
    if priority in {"high", "medium", "low"}:
        return priority
    return "medium"

# ── PDF label translations ────────────────────────────────────────────────

_PDF_LABELS: dict[str, dict[str, str]] = {
    "English": {
        "eyebrow":            "Shopify Agentic Commerce Readiness",
        "title":              "Agentic Commerce Readiness Report",
        "meta_products":      "Products Analyzed",
        "meta_high":          "High Priority",
        "meta_actions":       "Store Actions",
        "score_overall":      "Overall Readiness",
        "score_ucp":          "UCP Commerce Flows",
        "score_mcp":          "MCP Knowledge",
        "score_catalog":      "Catalog Enrichment",
        "score_safety":       "Safety & Policies",
        "cta_heading":        "Want us to make your store agentic-commerce ready?",
        "cta_body":           "Our team can implement these fixes for you — from schema and variant cleanup to UCP/MCP-ready storefront data.",
        "cta_button":         "Book a Free Consultation",
        "exec_eyebrow":       "Executive Summary",
        "exec_heading":       "Overall observations",
        "obs_high":           "{n} high-priority gaps across the catalog, concentrated in the kinds of fields agents need to recommend products confidently.",
        "obs_default":        "This report summarizes the current catalog readiness and the most useful fixes to make products easier for AI agents to discover and recommend.",
        "card_catalog":       "Catalog size",
        "card_catalog_desc":  "Number of products analyzed.",
        "card_gaps":          "High-priority gaps",
        "card_gaps_desc":     "Issues most likely to block accurate agent recommendations.",
        "card_actions":       "Store actions",
        "card_actions_desc":  "Catalog-wide improvements that benefit every product.",
        "top_store":          "Top store-level actions",
        "top_products":       "Products needing the most attention",
        "no_store_recs":      "No store-level recommendations returned.",
        "no_products":        "No products returned.",
        "gaps_label":         "{n} high-priority gaps",
        "section_store":      "Store-Level Recommendations",
        "section_products":   "Product Recommendations",
        "no_recs":            "No recommendations returned.",
        "no_product_recs":    "No product recommendations returned.",
        "product_eyebrow":    "Product",
        "product_id":         "ID:",
        "example_label":      "Example:",
        "provider_label":     "Provider:",
        "generated_label":    "Generated",
        "footer":             "Generated from Shopify product data. Review recommendations before publishing product or policy changes.",
        "powered_by": "Powered by Propero",
    },
    "German": {
        "eyebrow":            "Shopify Agentic-Commerce-Bereitschaft",
        "title":              "Agentic-Commerce-Bereitschaftsbericht",
        "meta_products":      "Analysierte Produkte",
        "meta_high":          "Hohe Priorität",
        "meta_actions":       "Shop-Maßnahmen",
        "score_overall":      "Gesamtbereitschaft",
        "score_ucp":          "UCP-Handelsabläufe",
        "score_mcp":          "MCP-Wissen",
        "score_catalog":      "Katalog-Anreicherung",
        "score_safety":       "Sicherheit & Richtlinien",
        "cta_heading":        "Möchten Sie, dass wir Ihren Shop agentic-commerce-bereit machen?",
        "cta_body":           "Unser Team kann diese Korrekturen für Sie umsetzen — von Schema- und Variantenbereinigung bis zu UCP/MCP-fähigen Shop-Daten.",
        "cta_button":         "Kostenlose Beratung buchen",
        "exec_eyebrow":       "Zusammenfassung",
        "exec_heading":       "Allgemeine Beobachtungen",
        "obs_high":           "{n} Lücken mit hoher Priorität im Katalog, konzentriert auf Felder, die Agenten für sichere Produktempfehlungen benötigen.",
        "obs_default":        "Dieser Bericht fasst die aktuelle Katalogbereitschaft und die nützlichsten Verbesserungen zusammen, um Produkte für KI-Agenten leichter auffindbar zu machen.",
        "card_catalog":       "Kataloggröße",
        "card_catalog_desc":  "Anzahl der analysierten Produkte.",
        "card_gaps":          "Lücken mit hoher Priorität",
        "card_gaps_desc":     "Probleme, die präzise Agentenempfehlungen am ehesten blockieren.",
        "card_actions":       "Shop-Maßnahmen",
        "card_actions_desc":  "Katalogweite Verbesserungen, die allen Produkten zugutekommen.",
        "top_store":          "Wichtigste Shop-Maßnahmen",
        "top_products":       "Produkte mit dem größten Handlungsbedarf",
        "no_store_recs":      "Keine Shop-Empfehlungen zurückgegeben.",
        "no_products":        "Keine Produkte zurückgegeben.",
        "gaps_label":         "{n} Lücken mit hoher Priorität",
        "section_store":      "Shop-weite Empfehlungen",
        "section_products":   "Produktempfehlungen",
        "no_recs":            "Keine Empfehlungen zurückgegeben.",
        "no_product_recs":    "Keine Produktempfehlungen zurückgegeben.",
        "product_eyebrow":    "Produkt",
        "product_id":         "ID:",
        "example_label":      "Beispiel:",
        "provider_label":     "Anbieter:",
        "generated_label":    "Erstellt",
        "footer":             "Erstellt aus Shopify-Produktdaten. Empfehlungen vor der Veröffentlichung von Produkt- oder Richtlinienänderungen prüfen.",
        "powered_by":          "Bereitgestellt von Propero",
    },
    "French": {
        "eyebrow":            "Préparation Shopify au commerce agentique",
        "title":              "Rapport de préparation au commerce agentique",
        "meta_products":      "Produits analysés",
        "meta_high":          "Priorité haute",
        "meta_actions":       "Actions boutique",
        "score_overall":      "Préparation globale",
        "score_ucp":          "Flux de commerce UCP",
        "score_mcp":          "Connaissances MCP",
        "score_catalog":      "Enrichissement du catalogue",
        "score_safety":       "Sécurité et politiques",
        "cta_heading":        "Vous voulez que nous rendions votre boutique prête pour le commerce agentique ?",
        "cta_body":           "Notre équipe peut mettre en œuvre ces corrections pour vous — du nettoyage des schémas et variantes aux données boutique compatibles UCP/MCP.",
        "cta_button":         "Réserver une consultation gratuite",
        "exec_eyebrow":       "Résumé exécutif",
        "exec_heading":       "Observations générales",
        "obs_high":           "{n} lacunes hautement prioritaires dans le catalogue, concentrées sur les champs dont les agents ont besoin pour recommander des produits en toute confiance.",
        "obs_default":        "Ce rapport résume l'état de préparation du catalogue et les corrections les plus utiles pour faciliter la découverte des produits par les agents IA.",
        "card_catalog":       "Taille du catalogue",
        "card_catalog_desc":  "Nombre de produits analysés.",
        "card_gaps":          "Lacunes prioritaires",
        "card_gaps_desc":     "Problèmes susceptibles de bloquer les recommandations précises des agents.",
        "card_actions":       "Actions boutique",
        "card_actions_desc":  "Améliorations à l'échelle du catalogue bénéficiant à tous les produits.",
        "top_store":          "Principales actions boutique",
        "top_products":       "Produits nécessitant le plus d'attention",
        "no_store_recs":      "Aucune recommandation boutique retournée.",
        "no_products":        "Aucun produit retourné.",
        "gaps_label":         "{n} lacunes prioritaires",
        "section_store":      "Recommandations au niveau boutique",
        "section_products":   "Recommandations produits",
        "no_recs":            "Aucune recommandation retournée.",
        "no_product_recs":    "Aucune recommandation produit retournée.",
        "product_eyebrow":    "Produit",
        "product_id":         "ID :",
        "example_label":      "Exemple :",
        "provider_label":     "Fournisseur :",
        "generated_label":    "Généré le",
        "footer":             "Généré à partir des données produits Shopify. Vérifiez les recommandations avant de publier des modifications de produits ou de politiques.",
        "powered_by":         "Propulsé par Propero",
    },
    "Spanish": {
        "eyebrow":            "Preparación de Shopify para el comercio agéntico",
        "title":              "Informe de preparación para el comercio agéntico",
        "meta_products":      "Productos analizados",
        "meta_high":          "Alta prioridad",
        "meta_actions":       "Acciones de tienda",
        "score_overall":      "Preparación general",
        "score_ucp":          "Flujos de comercio UCP",
        "score_mcp":          "Conocimiento MCP",
        "score_catalog":      "Enriquecimiento del catálogo",
        "score_safety":       "Seguridad y políticas",
        "cta_heading":        "¿Quiere que preparemos su tienda para el comercio agéntico?",
        "cta_body":           "Nuestro equipo puede implementar estas mejoras por usted — desde la limpieza de esquemas y variantes hasta datos de tienda compatibles con UCP/MCP.",
        "cta_button":         "Reservar una consulta gratuita",
        "exec_eyebrow":       "Resumen ejecutivo",
        "exec_heading":       "Observaciones generales",
        "obs_high":           "{n} brechas de alta prioridad en el catálogo, concentradas en los campos que los agentes necesitan para recomendar productos con confianza.",
        "obs_default":        "Este informe resume la preparación actual del catálogo y las correcciones más útiles para facilitar el descubrimiento de productos por agentes IA.",
        "card_catalog":       "Tamaño del catálogo",
        "card_catalog_desc":  "Número de productos analizados.",
        "card_gaps":          "Brechas de alta prioridad",
        "card_gaps_desc":     "Problemas que probablemente bloqueen las recomendaciones precisas de los agentes.",
        "card_actions":       "Acciones de tienda",
        "card_actions_desc":  "Mejoras a nivel de catálogo que benefician a todos los productos.",
        "top_store":          "Principales acciones de tienda",
        "top_products":       "Productos que requieren más atención",
        "no_store_recs":      "No se devolvieron recomendaciones de tienda.",
        "no_products":        "No se devolvieron productos.",
        "gaps_label":         "{n} brechas de alta prioridad",
        "section_store":      "Recomendaciones a nivel de tienda",
        "section_products":   "Recomendaciones de productos",
        "no_recs":            "No se devolvieron recomendaciones.",
        "no_product_recs":    "No se devolvieron recomendaciones de productos.",
        "product_eyebrow":    "Producto",
        "product_id":         "ID:",
        "example_label":      "Ejemplo:",
        "provider_label":     "Proveedor:",
        "generated_label":    "Generado",
        "footer":             "Generado a partir de datos de productos de Shopify. Revise las recomendaciones antes de publicar cambios en productos o políticas.",
        "powered_by":         "Desarrollado por Propero",
    },
    "Japanese": {
        "eyebrow":            "Shopifyエージェント型コマース対応状況",
        "title":              "エージェント型コマース対応レポート",
        "meta_products":      "分析済み商品数",
        "meta_high":          "高優先度",
        "meta_actions":       "ストア施策",
        "score_overall":      "総合対応度",
        "score_ucp":          "UCPコマースフロー",
        "score_mcp":          "MCPナレッジ",
        "score_catalog":      "カタログの充実度",
        "score_safety":       "安全性とポリシー",
        "cta_heading":        "ストアをエージェント型コマース対応にしませんか？",
        "cta_body":           "スキーマやバリアントの整備からUCP/MCP対応のストアデータ構築まで、私たちのチームが対応いたします。",
        "cta_button":         "無料相談を予約する",
        "exec_eyebrow":       "エグゼクティブサマリー",
        "exec_heading":       "全体的な所見",
        "obs_high":           "カタログ全体に{n}件の高優先度のギャップがあり、エージェントが自信を持って商品を推薦するために必要なフィールドに集中しています。",
        "obs_default":        "このレポートは現在のカタログの準備状況と、AIエージェントによる商品発見を促進するための最も有益な改善点をまとめています。",
        "card_catalog":       "カタログサイズ",
        "card_catalog_desc":  "分析した商品数。",
        "card_gaps":          "高優先度のギャップ",
        "card_gaps_desc":     "エージェントの正確な推薦をブロックする可能性が最も高い問題。",
        "card_actions":       "ストア施策",
        "card_actions_desc":  "すべての商品に恩恵をもたらすカタログ全体の改善。",
        "top_store":          "主要なストアレベルの施策",
        "top_products":       "最も注意が必要な商品",
        "no_store_recs":      "ストアの推薦事項はありません。",
        "no_products":        "商品が返されませんでした。",
        "gaps_label":         "{n}件の高優先度ギャップ",
        "section_store":      "ストアレベルの推薦事項",
        "section_products":   "商品推薦事項",
        "no_recs":            "推薦事項はありません。",
        "no_product_recs":    "商品推薦事項はありません。",
        "product_eyebrow":    "商品",
        "product_id":         "ID：",
        "example_label":      "例：",
        "provider_label":     "プロバイダー：",
        "generated_label":    "生成日時",
        "footer":             "Shopify商品データから生成されました。商品やポリシーの変更を公開する前に推薦事項を確認してください。",
        "powered_by":         "Propero提供",
    },
}


def _get_labels(language: str) -> dict[str, str]:
    """Return the label map for the given language, falling back to English."""
    return _PDF_LABELS.get(language, _PDF_LABELS["English"])


def render_recommendations(
    recommendations: list[dict[str, Any]],
    labels: dict[str, str],
) -> str:
    if not recommendations:
        return f'<p class="muted">{escape_html(labels["no_recs"])}</p>'

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
              <div class="example">
                <strong>{escape_html(labels["example_label"])}</strong>
                {escape_html(rec.get("example"))}
              </div>
            </article>
            """
        )
    return "\n".join(items)


def render_executive_summary(
    report: dict[str, Any],
    product_reports: list[dict[str, Any]],
    labels: dict[str, str],
) -> str:
    high_priority_count = sum(
        1
        for product in product_reports
        for rec in product.get("missing_enrichments", [])
        if rec.get("priority") == "high"
    )
    store_recommendations = report.get("store_level_recommendations") or []
    top_store_actions = store_recommendations[:3]

    if high_priority_count:
        observation = labels["obs_high"].replace("{n}", str(high_priority_count))
    else:
        observation = labels["obs_default"]

    highlight_cards = [
        (labels["card_catalog"],  str(len(product_reports)),       labels["card_catalog_desc"]),
        (labels["card_gaps"],     str(high_priority_count),        labels["card_gaps_desc"]),
        (labels["card_actions"],  str(len(store_recommendations)), labels["card_actions_desc"]),
    ]

    store_action_items = [
        f"<li><strong>{escape_html(rec.get('enrichment'))}</strong>"
        f"<span>{escape_html(rec.get('why_it_matters_for_agents'))}</span></li>"
        for rec in top_store_actions
    ]

    attention_products = sorted(
        product_reports,
        key=lambda p: sum(
            1 for r in p.get("missing_enrichments", []) if r.get("priority") == "high"
        ),
        reverse=True,
    )[:3]

    attention_items = [
        f"<li><strong>{escape_html(p.get('title') or 'Untitled product')}</strong>"
        f"<span>{labels['gaps_label'].replace('{n}', str(sum(1 for r in p.get('missing_enrichments', []) if r.get('priority') == 'high')))}</span></li>"
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

    no_store = f"<li><span>{escape_html(labels['no_store_recs'])}</span></li>"
    no_prod  = f"<li><span>{escape_html(labels['no_products'])}</span></li>"

    return f"""
      <section class="section executive-summary">
        <div class="summary-heading">
          <div>
            <p class="eyebrow">{escape_html(labels["exec_eyebrow"])}</p>
            <h2>{escape_html(labels["exec_heading"])}</h2>
          </div>
          <p class="summary-intro">{escape_html(observation)}</p>
        </div>
        <div class="summary-grid">{cards_html}</div>
        <div class="summary-columns">
          <article class="summary-panel">
            <h3>{escape_html(labels["top_store"])}</h3>
            <ul class="summary-list">
              {"".join(store_action_items) if store_action_items else no_store}
            </ul>
          </article>
          <article class="summary-panel">
            <h3>{escape_html(labels["top_products"])}</h3>
            <ul class="summary-list">
              {"".join(attention_items) if attention_items else no_prod}
            </ul>
          </article>
        </div>
      </section>
    """



def render_readiness_scores(scores: dict[str, int], labels: dict[str, str]) -> str:
    items = [
        (labels["score_overall"], scores.get("overall", 0)),
        (labels["score_ucp"], scores.get("ucp_commerce_flows", 0)),
        (labels["score_mcp"], scores.get("mcp_knowledge", 0)),
        (labels["score_catalog"], scores.get("catalog_enrichment", 0)),
        (labels["score_safety"], scores.get("safety_policies", 0)),
    ]

    def band(value: int) -> str:
        if value >= 70:
            return "strong"
        if value >= 40:
            return "fair"
        return "weak"

    cards = "".join(
        f"""
        <div class="score-card">
          <div class="score-circle score-circle--{band(value)}"><span>{value}</span></div>
          <p class="score-card__label">{escape_html(label)}</p>
        </div>
        """
        for label, value in items
    )
    return f'<section class="section readiness-scores">{cards}</section>'


def render_pdf_html(
    report: dict[str, Any],
    products: list[dict[str, Any]],
    store_url: str,
    language: str = "English",     
) -> str:
    labels = _get_labels(language)
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
              <p class="eyebrow">{escape_html(labels["product_eyebrow"])}</p>
              <h3>{escape_html(product.get("title") or "Untitled product")}</h3>
              <p class="muted">{escape_html(labels["product_id"])} {escape_html(product.get("product_id"))}</p>
            </div>
          </div>
          <p class="summary">{escape_html(product.get("agent_summary"))}</p>
          <div class="recommendation-list">
            {render_recommendations(product.get("missing_enrichments") or [], labels)}
          </div>
        </section>
        """
        for product in product_reports
    ]

    no_product_recs = f'<p class="muted">{escape_html(labels["no_product_recs"])}</p>'

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{escape_html(labels["title"])}</title>
  <style>
    @page {{ size: A4; margin: 18mm 15mm; }}
    * {{ box-sizing: border-box; }}
    @font-face {{
      font-family: 'NotoSansCJK';
      src: local('Noto Sans CJK JP'), local('NotoSansCJK-Regular');
    }}
    body {{ margin: 0; color: #18212f; font-family: 'NotoSansCJK', Inter, "Noto Sans CJK JP", "Noto Sans CJK SC", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-size: 11px; line-height: 1.5; background: #f6f2ea; }}
    .report {{ background: #fffdf8; border: 1px solid #ded6c8; min-height: 100vh; }}
    .hero {{ padding: 34px 38px 28px; color: #f9f4ea; background: linear-gradient(135deg, #16302b 0%, #22594f 48%, #b86b3d 100%); }}
    .hero h1 {{ max-width: 680px; margin: 10px 0 12px; font-size: 34px; line-height: 1.05; font-weight: 760;letter-spacing: 0; }}
    .hero p {{ max-width: 620px; margin: 0; color: #f2e7d4; font-size: 13px; }}
    .eyebrow {{ margin: 0 0 5px; color: inherit; font-size: 9px; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; opacity: .72; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; padding: 18px 38px; background: #efe6d8; border-bottom: 1px solid #ded6c8; }}
    .metric {{ padding: 12px; background: #fffdf8; border: 1px solid #d9d0c0; border-radius: 8px; }}
    .metric strong {{ display: block; margin-top: 2px; color: #172a3a; font-size: 18px; line-height: 1.1; }}
    main {{ padding: 28px 38px 36px; }}
    h2 {{ margin: 0 0 12px; color: #172a3a; font-size: 19px; line-height: 1.2; }}
    h3 {{ margin: 0; color: #172a3a; font-size: 17px; line-height: 1.25; }}
    h4 {{ margin: 0; color: #172a3a; font-size: 12px; line-height: 1.3; }}
    .section {{ margin-bottom: 28px; }}
    .executive-summary {{ break-after: page; margin-bottom: 34px; }}
    .summary-heading {{ display: grid; grid-template-columns: minmax(220px, 0.95fr) minmax(0, 1.35fr); gap: 20px; align-items: start; margin-bottom: 16px; }}
    .summary-intro {{ margin: 0; padding: 14px 16px; color: #243246; background: #f4efe6; border: 1px solid #ded6c8; border-radius: 10px; font-size: 12px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin-bottom: 14px; }}
    .summary-card {{ padding: 14px; background: #ffffff; border: 1px solid #ded6c8; border-radius: 10px; break-inside: avoid; }}
    .summary-card strong {{ display: block; margin: 4px 0 8px; color: #172a3a; font-size: 24px; line-height: 1; }}
    .summary-card p {{ margin: 0; color: #4b5567; }}
    .summary-columns {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .summary-panel {{ padding: 14px 15px; background: #ffffff; border: 1px solid #ded6c8; border-radius: 10px; break-inside: avoid; }}
    .summary-panel h3 {{ margin-bottom: 10px; font-size: 15px; }}
    .summary-list {{ margin: 0; padding-left: 18px; color: #324150; }}
    .summary-list li + li {{ margin-top: 8px; }}
    .summary-list strong {{ display: block; margin-bottom: 1px; color: #172a3a; }}
    .summary-list span {{ display: block; color: #4b5567; }}
    .recommendation-list {{ display: grid; gap: 10px; }}
    .recommendation {{ padding: 12px 13px; background: #ffffff; border: 1px solid #ded6c8; border-radius: 8px; break-inside: avoid; }}
    .recommendation__header {{ display: flex; align-items: flex-start; gap: 8px; margin-bottom: 7px; }}
    .recommendation p {{ margin: 0 0 8px; color: #3f4a5a; }}
    .example {{ padding: 8px 9px; color: #324150; background: #f4efe6; border-left: 3px solid #c47d52; border-radius: 5px; }}
    .pill {{ display: inline-block; min-width: 44px; padding: 3px 7px; border-radius: 999px; color: #ffffff; font-size: 8px; font-weight: 800; text-align: center; text-transform: uppercase; letter-spacing: .05em; }}
    .pill--high {{ background: #b43d31; }} .pill--medium {{ background: #b87524; }} .pill--low {{ background: #3d756b; }}
    .product-card {{ margin-bottom: 18px; padding: 18px; background: #ffffff; border: 1px solid #ded6c8; border-radius: 8px; break-inside: avoid; }}
    .product-card__top {{ display: flex; justify-content: space-between; gap: 16px; margin-bottom: 12px; }}
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
    .summary {{ margin: 0 0 14px; color: #3a4757; font-size: 12px; }}
    .muted {{ margin: 0; color: #667085; }}
    .readiness-scores {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin-bottom: 30px; }}
    .score-card {{ display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 12px 6px; background: #ffffff; border: 1px solid #ded6c8; border-radius: 10px; break-inside: avoid; }}
    .score-circle {{ width: 56px; height: 56px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #ffffff; }}
    .score-circle span {{ font-size: 18px; font-weight: 800; }}
    .score-circle--strong {{ background: #2e7169; }}
    .score-circle--fair {{ background: #b87524; }}
    .score-circle--weak {{ background: #b43d31; }}
    .score-card__label {{ margin: 0; font-size: 9px; font-weight: 700; text-align: center; color: #4b5567; text-transform: uppercase; letter-spacing: .03em; line-height: 1.3; }}
    .af-list {{ display: grid; gap: 8px; }}
    .af-row {{ display: flex; align-items: flex-start; gap: 10px; padding: 10px 12px; background: #ffffff; border: 1px solid #ded6c8; border-radius: 8px; break-inside: avoid; }}
    .af-icon {{ font-size: 13px; font-weight: 800; width: 18px; text-align: center; flex-shrink: 0; }}
    .af-name {{ font-weight: 700; color: #172a3a; font-size: 12px; }}
    .af-desc {{ color: #4b5567; font-size: 11px; margin-top: 2px; }}
    .cta-block {{ margin-top: 10px; padding: 22px 26px; background: linear-gradient(135deg, #16302b 0%, #22594f 60%, #b86b3d 130%); border-radius: 12px; color: #f9f4ea; text-align: center; break-inside: avoid; }}
    .cta-block h3 {{ color: #f9f4ea; font-size: 16px; margin-bottom: 8px; }}
    .cta-block p {{ margin: 0 auto 16px; max-width: 520px; font-size: 12px; color: #f2e7d4; }}
    .cta-button {{ display: inline-block; padding: 11px 26px; background: #ffffff; color: #16302b; border-radius: 100px; font-size: 13px; font-weight: 800; text-decoration: none; }}
    .footer {{ padding: 14px 38px 24px; color: #667085; border-top: 1px solid #ded6c8; }}
  </style>
</head>
<body>
  <div class="report">
    <header class="hero">
      <p class="eyebrow">{escape_html(labels["eyebrow"])}</p>
      <h1>{escape_html(labels["title"])}</h1>
      <p>{escape_html(store_url)} · {escape_html(labels["generated_label"])} {escape_html(generated_at)} · {escape_html(labels["provider_label"])} {escape_html(report.get("provider", "unknown"))} {escape_html(report.get("model", ""))}</p>
    </header>
    <section class="meta-grid">
      <div class="metric"><span class="eyebrow">{escape_html(labels["meta_products"])}</span><strong>{len(products)}</strong></div>
      <div class="metric"><span class="eyebrow">{escape_html(labels["meta_high"])}</span><strong>{high_priority_count}</strong></div>
      <div class="metric"><span class="eyebrow">{escape_html(labels["meta_actions"])}</span><strong>{len(report.get("store_level_recommendations") or [])}</strong></div>
    </section>
    <main>
      {render_readiness_scores(normalize_readiness_scores(report.get("readiness_scores")), labels)}
      {render_agent_discovery(report.get("agent_discovery"), labels)}
      {render_executive_summary(report, product_reports, labels)}
      <section class="section">
        <h2>{escape_html(labels["section_store"])}</h2>
        <div class="recommendation-list">
          {render_recommendations(report.get("store_level_recommendations") or [], labels)}
        </div>
      </section>
      <section class="section">
        <h2>{escape_html(labels["section_products"])}</h2>
        {"".join(product_cards) if product_cards else no_product_recs}
      </section>
    </main>
    <footer class="footer">
        <div>{escape_html(labels["footer"])}</div>
        <div style="margin-top:8px;font-weight:600;color:#22594f;">
            {escape_html(labels["powered_by"])} • 
            <a href="https://www.propero.in"style="color:#17695b;text-decoration:none">propero.in</a>
        </div>
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

def chunked(items: list[Any], size: int) -> list[list[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


# ── Agent discovery file readiness (Shopify's May 2026 rollout) ────────
# Shopify now auto-serves /agents.md (canonical), /llms.txt and
# /llms-full.txt (mirror/redirect to agents.md by default), and a
# /.well-known/ucp manifest on every storefront. Existence isn't the
# signal anymore — every merchant has these. Customization is.

_AGENT_DISCOVERY_PATHS = {
    "agents_md":     "/agents.md",
    "llms_txt":      "/llms.txt",
    "llms_full_txt": "/llms-full.txt",
    "ucp_manifest":  "/.well-known/ucp",
}

# Markers that indicate Shopify's stock template hasn't been customized.
_DEFAULT_FILE_MARKERS = (
    "shopify.com/start",
    "this file was automatically generated by shopify",
    "powered by shopify",
)

# Structural fingerprints of Shopify's shipped agents.md.liquid default —
# per Shopify's docs, the stock template is a generic UCP/MCP protocol
# reference, not brand- or product-specific content. The more of these
# that appear, the more the body still looks like the unedited default.
_BOILERPLATE_SIGNATURES = (
    "agent instructions —",
    "commerce protocol (ucp)",
    "this store implements the universal commerce protocol for agent-driven commerce",
    "read-only browsing",
)

_POLICY_WORDS = ("shipping", "return", "refund", "privacy", "warranty")
_BRAND_WORDS = ("we specialize", "our brand", "about us", "founded", "our mission", "our story")
_GUIDANCE_WORDS = ("shopping guidance", "how to shop", "recommend", "best for", "ideal for")
_PRODUCT_PATH_WORDS = ("/products/", "/collections/", "/pages/")
_HERO_WORDS = ("best seller", "bestseller", "hero product", "top collection", "flagship")

_MIRROR_SIMILARITY_THRESHOLD = 0.9


def _agent_discovery_base_url(store_url: str) -> str:
    """
    Build a bare origin URL (scheme + host, no path/query) for agent-discovery
    probes. Deliberately independent of normalize_store_url(), which is tuned
    for locating a store's product feed and may reject/rewrite custom domains
    (e.g. domesticappliances.philips.co.in) in ways that break here.
    """
    from urllib.parse import urlparse

    candidate = (store_url or "").strip()
    parsed = urlparse(candidate)
    if not parsed.scheme:
        parsed = urlparse(f"https://{candidate}")
    if not parsed.netloc:
        raise ValueError(f"Could not parse a host from store_url: {store_url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


# A real browser UA. Some storefronts sit behind a WAF/CDN (Akamai,
# Cloudflare, Shopify's own bot protection) that silently blocks or
# challenges requests carrying an obviously-scripted User-Agent — which
# would make every one of these checks look "missing" even though a
# person's browser (or a competitor's tool) can load the same file fine.
_AGENT_DISCOVERY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _fetch_agent_discovery_url(url: str, timeout: int = 15) -> dict[str, Any]:
    """GET a single agent-discovery URL and classify what came back."""
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": _AGENT_DISCOVERY_UA,
            "Accept": "text/plain, text/markdown, application/json, */*;q=0.8",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            final_url = response.geturl()
            status = response.status
            raw = response.read(200_000)  # these are meant to be small text files
    except urllib.error.HTTPError as error:
        return {
            "status": "missing",
            "http_status": error.code,
            "final_url": url,
            "word_count": 0,
            "looks_customized": False,
            "_body": "",
        }
    except urllib.error.URLError:
        return {
            "status": "unreachable",
            "http_status": None,
            "final_url": url,
            "word_count": 0,
            "looks_customized": False,
            "_body": "",
        }

    text = raw.decode("utf-8", errors="replace")
    lower = text.lower()
    word_count = len(text.split())
    looks_default = any(marker in lower for marker in _DEFAULT_FILE_MARKERS) or word_count < 25
    redirected = final_url.rstrip("/") != url.rstrip("/")

    if status >= 400:
        state = "missing"
    elif redirected:
        state = "redirects"
    elif looks_default:
        state = "served_default"
    else:
        state = "served_custom"

    return {
        "status": state,
        "http_status": status,
        "final_url": final_url,
        "word_count": word_count,
        "looks_customized": state == "served_custom",
        "_body": text,  # stripped out before the result leaves check_agent_discovery_readiness
    }


def _classify_customization(text: str, word_count: int) -> str:
    """
    Classify how far a file's body has moved from Shopify's shipped
    agents.md.liquid default: empty, a mostly-untouched default skeleton,
    lightly customized (boilerplate plus some added content), or heavily
    customized (boilerplate rephrased/removed, real brand/product content).
    """
    if word_count < 25:
        return "empty"
    lower = text.lower()
    signature_hits = sum(1 for sig in _BOILERPLATE_SIGNATURES if sig in lower)
    if signature_hits >= 2 and word_count < 150:
        return "default_skeleton"
    if signature_hits >= 2 and word_count >= 150:
        return "lightly_customized"
    if signature_hits <= 1 and word_count >= 60:
        return "heavily_customized"
    return "lightly_customized"


def _check_content_quality(role: str, lower_text: str) -> dict[str, bool]:
    """Per-file content-quality checks matching Shopify's stated intent for each file."""
    if role == "agents_md":
        return {
            "mentions_ucp_mcp": (
                "ucp" in lower_text or "mcp" in lower_text or "model context protocol" in lower_text
            ),
            "policy_links": any(w in lower_text for w in _POLICY_WORDS),
            "brand_identity": any(w in lower_text for w in _BRAND_WORDS),
            "shopping_guidance": any(w in lower_text for w in _GUIDANCE_WORDS),
        }
    if role == "llms_txt":
        return {"links_to_agents_md": "agents.md" in lower_text}
    if role == "llms_full_txt":
        return {
            "mentions_products_or_collections": any(w in lower_text for w in _PRODUCT_PATH_WORDS),
            "mentions_hero_or_bestsellers": any(w in lower_text for w in _HERO_WORDS),
        }
    return {}


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _build_agent_discovery_recommendations(results: dict[str, Any]) -> list[dict[str, str]]:
    """
    Shopify-aligned recommendations (same shape as store_level_recommendations,
    so they render through the existing render_recommendations()/renderRecommendations()
    UI) based on agents.md.liquid / llms.txt.liquid / llms-full.txt.liquid intent.
    """
    recs: list[dict[str, str]] = []
    agents = results.get("agents_md", {})
    llms = results.get("llms_txt", {})
    llms_full = results.get("llms_full_txt", {})

    if agents.get("customization") == "default_skeleton":
        recs.append({
            "priority": "high",
            "enrichment": "Customize your agents.md canonical guide",
            "why_it_matters_for_agents": (
                "agents.md currently reads like a generic UCP/MCP protocol reference rather than "
                "brand-specific guidance. Shopping agents rely on this file to understand how to "
                "represent your store, not just how to connect to it."
            ),
            "example": (
                "Add sections to templates/agents.md.liquid covering brand identity, target audience, "
                "hero products and key use-cases, and the policies that matter most to your buyers."
            ),
        })
    else:
        quality = agents.get("quality") or {}
        if quality and not quality.get("policy_links"):
            recs.append({
                "priority": "medium",
                "enrichment": "Link store policies from agents.md",
                "why_it_matters_for_agents": (
                    "Agents need policy context (shipping, returns, refunds) to answer shopper "
                    "questions confidently and avoid recommending purchases that violate store terms."
                ),
                "example": "Add a 'Policies' section to agents.md linking your shipping, return, and refund pages.",
            })
        if quality and not quality.get("brand_identity"):
            recs.append({
                "priority": "medium",
                "enrichment": "Add a brand identity section to agents.md",
                "why_it_matters_for_agents": (
                    "Without brand context, agents fall back on generic product data and can't explain "
                    "what makes your store distinct or who it's for."
                ),
                "example": "Describe your niche, target audience, and what sets your products apart.",
            })
        if quality and not quality.get("shopping_guidance"):
            recs.append({
                "priority": "low",
                "enrichment": "Add shopping guidance to agents.md",
                "why_it_matters_for_agents": (
                    "A 'how to shop this store' section helps agents match shopper intent to the right "
                    "products instead of guessing from catalog data alone."
                ),
                "example": "Add headings like 'Best For' or 'Shopping Guidance' describing ideal use-cases per category.",
            })

    if llms.get("mirrors_agents_md"):
        recs.append({
            "priority": "medium",
            "enrichment": "Give llms.txt a dedicated brand-summary template",
            "why_it_matters_for_agents": (
                "llms.txt currently just mirrors agents.md — no separate llms.txt.liquid template is "
                "defined, so agents get the full protocol reference instead of a quick brand map."
            ),
            "example": (
                "Create templates/llms.txt.liquid with a 2-3 paragraph brand overview and a link to /agents.md."
            ),
        })

    if llms_full.get("mirrors_agents_md"):
        recs.append({
            "priority": "medium",
            "enrichment": "Give llms-full.txt dedicated deep product context",
            "why_it_matters_for_agents": (
                "llms-full.txt currently just mirrors agents.md, so agents miss the deeper hero-product "
                "and collection context Shopify intends this file for."
            ),
            "example": (
                "Create templates/llms-full.txt.liquid describing 3-5 hero products, key collections, "
                "and supporting pages like size guides or gifting info."
            ),
        })

    return recs


def check_agent_discovery_readiness(store_url: str) -> dict[str, Any]:
    """
    Checks Shopify's native AI-agent discovery surfaces: /agents.md
    (canonical since the May 2026 rollout), /llms.txt and /llms-full.txt
    (mirror agents.md unless the merchant defines dedicated
    llms.txt.liquid / llms-full.txt.liquid templates), and the
    /.well-known/ucp manifest for Universal Commerce Protocol discovery.

    Goes beyond reachability: classifies each text file as still-default,
    lightly customized, or heavily customized against Shopify's shipped
    agents.md.liquid boilerplate; detects whether llms.txt/llms-full.txt
    are just mirroring agents.md (no dedicated template) or serving their
    own distinct role per Shopify's docs; and runs content-quality checks
    (UCP/MCP references, policy links, brand identity, shopping guidance,
    hero-product/collection mentions) to produce Shopify-aligned fix
    recommendations rather than a bare presence/absence checklist.
    """
    base = normalize_store_url(store_url).rstrip("/")
    results: dict[str, Any] = {}
    for key, path in _AGENT_DISCOVERY_PATHS.items():
        results[key] = _fetch_agent_discovery_url(base + path)

    bodies = {key: results[key].pop("_body", "") for key in results}

    for key in ("agents_md", "llms_txt", "llms_full_txt"):
        info = results[key]
        body = bodies.get(key, "")
        if info["status"] not in ("missing", "unreachable"):
            info["customization"] = _classify_customization(body, info["word_count"])
            info["quality"] = _check_content_quality(key, body.lower())
        else:
            info["customization"] = "unknown"
            info["quality"] = {}

    agents_body = bodies.get("agents_md", "")
    results["llms_txt"]["mirrors_agents_md"] = (
        _similarity(agents_body, bodies.get("llms_txt", "")) > _MIRROR_SIMILARITY_THRESHOLD
    )
    results["llms_full_txt"]["mirrors_agents_md"] = (
        _similarity(agents_body, bodies.get("llms_full_txt", "")) > _MIRROR_SIMILARITY_THRESHOLD
    )

    served_count = sum(
        1 for r in results.values()
        if r["status"] in ("served_custom", "served_default", "redirects")
    )
    customized_count = sum(1 for r in results.values() if r["looks_customized"])
    templates_customized = sum(
        1 for key in ("agents_md", "llms_txt", "llms_full_txt")
        if results[key].get("customization") == "heavily_customized"
        and not results[key].get("mirrors_agents_md", False)
    )

    recommendations = _build_agent_discovery_recommendations(results)

    return {
        "checked_at": dt.datetime.now().isoformat(),
        "files": results,
        "canonical_served": results["agents_md"]["status"] != "missing",
        "any_customized": customized_count > 0,
        "templates_customized": templates_customized,
        "templates_total": 3,
        "recommendations": recommendations,
        "summary": (
            f"{served_count}/{len(results)} agent-discovery endpoints reachable, "
            f"{templates_customized}/3 templates customized beyond Shopify's default "
            f"(agents.md / llms.txt / llms-full.txt role separation)."
        ),
    }


_AGENT_DISCOVERY_LABELS = {
    "agents_md":     "agents.md (canonical agent guide)",
    "llms_txt":      "llms.txt",
    "llms_full_txt": "llms-full.txt",
    "ucp_manifest":  "/.well-known/ucp (UCP manifest)",
}

_AGENT_DISCOVERY_STATUS = {
    "served_custom":  ("✓", "Served and customized"),
    "served_default": ("⚠", "Served — still Shopify's default template"),
    "redirects":      ("→", "Redirects to agents.md (expected for llms.txt/llms-full.txt)"),
    "missing":        ("✕", "Not reachable"),
    "unreachable":    ("✕", "Could not connect"),
}

_CUSTOMIZATION_LABELS = {
    "default_skeleton":   "Shopify default skeleton — mostly boilerplate",
    "lightly_customized": "Lightly customized — boilerplate plus some custom content",
    "heavily_customized": "Heavily customized — brand/product-specific content",
    "empty":              "Empty or too thin to classify",
    "unknown":            "Not evaluated",
}


def render_agent_discovery(agent_discovery: dict[str, Any] | None, labels: dict[str, str]) -> str:
    if not agent_discovery:
        return ""
    files = agent_discovery.get("files", {})
    rows = []
    for key, label in _AGENT_DISCOVERY_LABELS.items():
        info = files.get(key, {})
        icon, text = _AGENT_DISCOVERY_STATUS.get(info.get("status"), ("○", "Unknown"))
        extra = ""
        if info.get("status") not in ("missing", "unreachable"):
            cust_text = _CUSTOMIZATION_LABELS.get(info.get("customization"), "")
            if cust_text:
                extra += f" · {cust_text}"
            if info.get("mirrors_agents_md"):
                extra += " · mirrors agents.md (no dedicated template)"
        rows.append(
            f"""
            <div class="af-row">
              <span class="af-icon">{escape_html(icon)}</span>
              <div>
                <div class="af-name">{escape_html(label)}</div>
                <div class="af-desc">{escape_html(text)}{escape_html(extra)}</div>
              </div>
            </div>
            """
        )

    recommendations = agent_discovery.get("recommendations") or []
    recs_html = ""
    if recommendations:
        recs_html = f"""
          <h3 style="margin:16px 0 10px;">Shopify-Aligned Recommendations</h3>
          <div class="recommendation-list">{render_recommendations(recommendations, labels)}</div>
        """

    templates_customized = agent_discovery.get("templates_customized", 0)
    templates_total = agent_discovery.get("templates_total", 3)

    return f"""
      <section class="section agent-discovery">
        <h2>Agent Discovery Files</h2>
        <p class="muted">{escape_html(agent_discovery.get("summary", ""))}</p>
        <p class="muted">Template readiness: {templates_customized}/{templates_total} customized beyond Shopify's default.</p>
        <div class="af-list">{"".join(rows)}</div>
        {recs_html}
      </section>
    """



def merge_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    merged = {
        "readiness_scores": {},
        "store_level_recommendations": [],
        "products": [],
    }

    score_totals = {key: 0 for key in _READINESS_KEYS}
    score_counts = {key: 0 for key in _READINESS_KEYS}

    for report in reports:
        merged["store_level_recommendations"].extend(
            report.get("store_level_recommendations") or []
        )
        merged["products"].extend(report.get("products") or [])

        batch_scores = normalize_readiness_scores(report.get("readiness_scores"))
        if report.get("readiness_scores"):
            for key in _READINESS_KEYS:
                score_totals[key] += batch_scores[key]
                score_counts[key] += 1

    merged["readiness_scores"] = {
        key: round(score_totals[key] / score_counts[key]) if score_counts[key] else 0
        for key in _READINESS_KEYS
    }

    seen_store = set()
    deduped_store = []
    for rec in merged["store_level_recommendations"]:
        key = (
            rec.get("priority"),
            rec.get("enrichment"),
            rec.get("why_it_matters_for_agents"),
            rec.get("example"),
        )
        if key in seen_store:
            continue
        seen_store.add(key)
        deduped_store.append(rec)

    merged["store_level_recommendations"] = deduped_store
    return merged

def run_store_analysis(store_url: str, language: str = "English") -> dict[str, Any]:
    settings = get_app_settings()
    max_products = settings["max_products"]
    raw_products = fetch_products_public(store_url, max_products)

    if not raw_products:
        raise EmptyStoreError(
            f"'{store_url}' appears to be a Shopify store but has no publicly "
            "visible products. The catalogue may be password-protected, "
            "set to draft, or not yet published."
        )

    products = [compact_product(p, store_url) for p in raw_products]

    try:
        agent_discovery = check_agent_discovery_readiness(store_url)
    except Exception as error:
        import traceback
        print(f"[AgentDiscovery] check failed for {store_url!r}: {error}")
        traceback.print_exc()
        agent_discovery = None

    provider = settings["provider"]
    model = settings["model"]

    if provider != "gemini":
        report = analyze_products(products, store_url, provider, model, language)
    else:
        batch_size = int(os.getenv("MAX_PRODUCTS_PER_BATCH", "5"))
        batches = chunked(products, batch_size)

        batch_reports = []

        for idx, batch in enumerate(batches, start=1):
            print("=" * 80)
            print(f"[Gemini] Batch {idx}/{len(batches)}")
            print(f"[Gemini] Products in batch: {len(batch)}")

            for product in batch:
                print(
                    f"  - {product.get('title')} "
                    f"(ID: {product.get('id')})"
                )

            start = time.time()

            result = analyze_products(
                batch,
                store_url,
                provider,
                model,
                language,
            )

            print(
                f"[Gemini] Batch {idx} completed in "
                f"{time.time() - start:.2f}s"
            )

            batch_reports.append(result)

        report = merge_reports(batch_reports)

    report.setdefault("provider", provider)
    report.setdefault("model", model)
    report.setdefault("store_url", store_url)
    report["agent_discovery"] = agent_discovery

    return {
        "settings": settings,
        "store_url": store_url,
        "products": products,
        "report": report,
    }

def build_pdf_attachment(
    report: dict[str, Any],
    products: list[dict[str, Any]],
    store_url: str,
    language: str = "English",
) -> tuple[bytes, str]:
    from urllib.parse import urlparse
    domain = urlparse(store_url).netloc.replace("www.", "")
    date_str = dt.datetime.now().strftime("%Y-%m-%d")
    pdf_filename = f"Propero_AI_Report_{domain}_{date_str}.pdf"

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        html_path = temp_path / "report.html"
        pdf_path  = temp_path / pdf_filename
        html_path.write_text(
            render_pdf_html(report, products, store_url, language),
            encoding="utf-8",
        )
        if not write_pdf_report(str(html_path), str(pdf_path)):
            raise RuntimeError(
                "PDF conversion is unavailable. Install weasyprint to enable PDF email delivery."
            )
        return pdf_path.read_bytes(), pdf_filename
# The API routes were intentionally removed from this module so the package
# `app` can own the FastAPI instance (see app/main.py). This file continues to
# provide the analysis and rendering helpers which can be used by the API or
# invoked directly from a CLI/script.