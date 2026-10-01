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
    normalize_store_url,
)
from app.services.scoring_rubric import (
    CHECKS, compute_scores, build_product_recommendations, build_store_recommendations,
)
from app.services.issue_registry import (
    ISSUE_TYPES,
    is_valid_issue_type,
    find_issue_definition,
)
from app.services.issue_discovery import normalize_issue
import tempfile

from typing import Protocol
from app.services.deterministic_checks import (
    run_product_deterministic_checks,
    run_store_deterministic_checks,
    check_catalog_consistency,
    check_description_presence,      
    check_product_type_presence,
    STORE_CONTEXT_REQUIRED_CHECKS,
)

from app.services.scoring_rubric import (
    llm_product_check_ids,
    llm_store_check_ids,
)

class LLMAdapter(Protocol):
    """Common interface all LLM adapters must satisfy."""
    def analyze(
        self,
        products: list[dict[str, Any]],
        store_context: dict[str, Any] | None,
        store_url: str,
        language: str,
    ) -> dict[str, Any]:
        ...


class GeminiAdapter:
    def __init__(self, model: str) -> None:
        self.model = model

    def analyze(self, products, store_context, store_url, language="English"):
        return analyze_with_gemini(
            products, store_context, store_url, self.model, language
        )


class BedrockAdapter:
    def __init__(self, model: str = "global.anthropic.claude-opus-4-5-20251101-v1:0") -> None:
        self.model = model

    def analyze(self, products, store_context, store_url, language="English"):
        return analyze_with_bedrock_claude(products, store_context, store_url, self.model, language)


class OpenAIAdapter:
    def __init__(self, model: str) -> None:
        self.model = model

    def analyze(self, products, store_context, store_url, language="English"):
        return analyze_with_openai(products, store_context, store_url, self.model, language)


class OllamaAdapter:
    def __init__(self, model: str) -> None:
        self.model = model

    def analyze(self, products, store_context, store_url, language="English"):
        return analyze_with_ollama(products, store_context, store_url, self.model, language)


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

def _rubric_prompt_block() -> str:
    llm_ids = set(llm_product_check_ids()) | set(llm_store_check_ids())
    lines = []
    for category, checks in CHECKS.items():   
        for c in checks:
            if c["id"] not in llm_ids:
                continue
            scope = "STORE-WIDE (evaluate once for the whole store)" if c["level"] == "store" else "PER-PRODUCT (evaluate for each product)"
            lines.append(f"- [{c['id']}] ({scope}) {c['desc']}")
    return "\n".join(lines)


def build_prompt(
    products: list[dict[str, Any]],
    store_context: dict[str, Any],
    store_url: str,
    language: str = "English",
) -> str:

    issue_registry_block = "\n".join(
        (
            f"- [{check_id}] {issue_type}"
            f" | registered_fix_action: {definition.get('fix_action', 'none')}"
        )
        for check_id, issues in ISSUE_TYPES.items()
        for issue_type, definition in issues.items()
    )

    return f"""
You are an ecommerce data strategist evaluating supplied store and
product data for agentic commerce readiness.

Your task is to evaluate the supplied data ONLY against the FIXED
RUBRIC provided below.

============================================================
PURPOSE OF THIS AUDIT
============================================================

This audit is a MEASUREMENT, not a brainstorm.

Each evaluation must be based only on:

1. the supplied Products Catalogue Payload;
2. the supplied Store Context;
3. the Fixed Rubric;
4. the Issue Registry.

The current evaluation is independent.

Do not assume, infer, remember, reconstruct, or reference any
information outside the current payload and the rules provided in
this prompt.

Do not use information from any earlier evaluation, recommendation,
fix, batch, result, or output.

Do not attempt to determine whether something was previously fixed,
previously reported, previously passed, or previously failed.

Judge only the CURRENT supplied data.

A correct audit has two properties:

1. FAITHFUL

Every finding must correspond to an explicit requirement of the
Fixed Rubric that the supplied data demonstrates is not satisfied.

2. CONVERGENT

When the supplied data satisfies the requirements of a check,
that check must pass.

Do not replace a satisfied requirement with another deficiency
simply because the supplied data could be improved in some other way.

The same supplied payload, Fixed Rubric, and Store Context must
produce the same interpretation.

The purpose is to apply the existing rubric consistently, not to
find as many problems as possible.

A successful audit is allowed to contain fewer issues than a previous
audit, including zero issues for a check. A check does NOT need to
remain PARTIAL or FAIL merely because it was PARTIAL or FAIL before.

The audit must detect real remaining deficiencies when they exist,
but it must not search for replacement deficiencies after a requirement
has become satisfied.

============================================================
STEP 1 — UNDERSTAND THE CURRENT DATA FIRST
============================================================

Before evaluating any check, read and understand the complete
supplied payload.

Consider all supplied information that may be relevant, including:

- product information;
- descriptions;
- product properties;
- structured data;
- attributes;
- metafields;
- options;
- option values;
- variants;
- pricing;
- inventory;
- availability;
- identifiers;
- URLs;
- store information;
- store context;
- any other fields actually supplied in the payload.

Do not use external information to fill gaps.

Do not assume a value exists when it is not present.

Do not assume a field is missing when the same information is
clearly represented elsewhere in the supplied payload.

Understand the complete current data before assigning a verdict
or issue.

============================================================
STEP 2 — EVALUATE ONLY AGAINST THE FIXED RUBRIC
============================================================

For every check defined by the Fixed Rubric:

1. read the exact definition of that check;
2. identify the explicit requirements of that check;
3. inspect the supplied data for evidence relevant to those
   requirements;
4. determine whether the requirements are satisfied;
5. return exactly one verdict:

   "pass"
   "partial"
   "fail"
   "na"

The Fixed Rubric is the sole authority for what a check evaluates.

Do not create additional evaluation criteria.

Do not add requirements that are not explicitly defined by the
current check.

Do not remove requirements that are explicitly defined by the
current check.

Do not transfer a requirement from one check to another.

Do not use general ecommerce best practices as additional scoring
criteria.

Do not compare the supplied data against an imagined ideal,
preferred, richer, or more complete version of the data.

============================================================
VERDICT STABILITY
============================================================

Apply the Fixed Rubric consistently.

For the same:

- supplied data;
- Store Context;
- Fixed Rubric;
- check;

the interpretation must remain the same.

Do not change a check because another check changed.

Do not make one check stricter or more permissive because another
check changed.

Do not compensate for a result in one check by changing another
check.

Do not change a verdict to make results appear balanced.

Do not create an issue to prevent a check from passing.

Do not remove a valid issue to make results appear stable.

Do not introduce a new requirement to explain a different result.

Do not reinterpret the same evidence using a newly imagined rule.

Consistency must come from consistent application of the existing
Fixed Rubric.

A change in one category is NEVER a reason by itself to change
another category.

For example:

- an MCP result must not be changed because Catalog changed;
- a Catalog result must not be changed because Safety changed;
- a Safety result must not be changed because MCP changed;
- a UCP result must not be changed because another category changed.

Only evidence relevant to the current check may change that
check's verdict.

============================================================
CURRENT-STATE REQUIREMENT VERIFICATION
============================================================

Evaluate every requirement from the CURRENT supplied data.

The current payload is intentionally a fresh measurement. It may
reflect changes made since an earlier evaluation, but no earlier
evaluation is provided to you and must not be reconstructed.

If the CURRENT data satisfies a requirement that could previously
have been unsatisfied, treat that requirement as satisfied now.

Do not assume that a previously observed problem still exists.
Do not carry an issue from one evaluation into another.
Do not preserve an issue classification because it appeared before.
Do not infer that a fix failed merely because the current audit
contains another legitimate issue.

The absence of historical context is intentional. Your job is to
measure the current state accurately, not to preserve historical
findings.

============================================================
NO ISSUE SUBSTITUTION
============================================================

The purpose of the audit is NOT to ensure that every check contains
an issue.

When a requirement is satisfied in the CURRENT data, CLOSE that
requirement. Do not search for another problem merely because:

- the same check had an issue before;
- the same product had an issue before;
- the category previously had a lower result;
- a recommendation was previously made;
- a fix was expected to improve the result;
- another issue type exists in the registry;
- another field could theoretically be improved.

Do NOT replace a resolved condition with another issue merely to keep
a check PARTIAL or FAIL.

Do NOT reinterpret unrelated evidence more strictly after a previous
condition is satisfied.

Do NOT search for a weaker, narrower, or alternative deficiency after
the original requirement has been satisfied.

A different issue may still be reported, but ONLY if all of the
following are true:

1. It is independently demonstrated by the CURRENT supplied data.
2. It violates a separate explicit requirement of the CURRENT
   Fixed Rubric.
3. It is semantically distinct from the condition that is now
   satisfied.
4. It would still be a valid issue if the previously observed
   condition had never existed.
5. Its existence does not depend on the fact that another issue
   was previously reported or fixed.

The existence of a previous issue is never evidence for a new issue.
The existence of a previous recommendation is never evidence for a
new issue.
The fact that a check previously failed is never evidence that it
should fail again.

Every active issue must independently earn its existence from the
CURRENT payload and CURRENT Fixed Rubric.

============================================================
NO NEW REQUIREMENTS
============================================================

Do not introduce:

- new evaluation criteria;
- new requirements;
- new scoring conditions;
- new minimum lengths;
- new minimum numbers of fields;
- new minimum numbers of attributes;
- new formatting requirements;
- new standardization requirements;
- new category requirements;
- new best-practice requirements.

Information that could improve the supplied data is not automatically
a scoring deficiency.

A deficiency exists only when the Fixed Rubric explicitly requires
the relevant condition and the supplied evidence demonstrates that
the condition is not satisfied.

============================================================
NO CROSS-CHECK CONTAMINATION
============================================================

Every check is evaluated independently.

Evidence may appear in multiple places in the supplied payload.

That does not allow one check to create or modify requirements
belonging to another check.

Do not transfer between checks:

- requirements;
- deficiencies;
- verdicts;
- issue classifications;
- scoring meaning;
- remediation requirements.

A relationship between two pieces of evidence does not make them
the same requirement.

The issue belongs to the check whose Fixed Rubric actually owns
the violated condition.

A single underlying defect must not be duplicated across multiple
checks merely because related evidence appears in multiple checks.

A problem may be relevant to more than one check only when the
same underlying evidence independently violates an explicit
requirement of each check.

Do not duplicate an issue merely because:

- the same field is visible to another check;
- the same object is referenced by another check;
- the same fix could theoretically be useful elsewhere;
- the same issue_type string exists elsewhere;
- another check has a related concept.

============================================================
CHECK CLOSURE — CURRENT DATA ONLY
============================================================

Evaluate each check using only the CURRENT supplied data.

For each check:

1. identify all explicit applicable requirements;
2. evaluate every applicable requirement;
3. determine whether each requirement is satisfied.

If every applicable requirement is satisfied:

- verdict MUST be "pass";
- issues MUST be [];
- enrichment MUST be "";
- why_it_matters_for_agents MUST be "";
- example MUST be "";

STOP evaluating that check.

Once all explicit requirements of a check are satisfied, that check
is CLOSED for this evaluation.

Do not continue searching for another deficiency.

Do not create a replacement issue.

Do not create an issue because another check contains an issue.

Do not create an issue because an issue type exists in the registry.

Do not create an issue because additional information could improve
the supplied data.

Do not create an issue to prevent the check from becoming PASS.

Only another independently demonstrated violation of another
explicit requirement of the SAME check may produce another issue.

============================================================
REPEATED EVALUATION RULE
============================================================

When the same evidence is supplied again:

- evaluate it against the same Fixed Rubric;
- do not invent a new requirement;
- do not search for a different deficiency;
- do not change the interpretation because the evaluation is being
  repeated;
- do not use any previous output as evidence;
- do not use any previous output as a reason to change the current
  output.

The current payload is the only data being evaluated.

Different evidence may legitimately produce a different verdict or
different issue.

Same evidence under the same rubric should produce the same semantic
interpretation.

============================================================
PASS / PARTIAL / FAIL / NA — STRICT DECISION RULE
============================================================

For every check, make the verdict using ONLY the Fixed Rubric and the
CURRENT supplied data.

Do not use previous evaluations, previous recommendations, previous fixes,
previous batches, other checks, other categories, issue count, issue
severity, or desired score.

STEP 1 — APPLICABILITY

Determine whether the current check applies using ONLY the Fixed Rubric.

If the check does not apply:
    verdict = "na"

Do not invent applicability rules.

------------------------------------------------------------

STEP 2 — EVIDENCE AVAILABILITY

Determine whether the evidence required to evaluate the applicable check
is available in the CURRENT supplied data.

If required evidence is genuinely unavailable AND the Fixed Rubric
permits NA in that situation:
    verdict = "na"

Do NOT treat "some data is incomplete" as automatically meaning NA.

NA means the check cannot be evaluated or does not apply according to the
Fixed Rubric.

If the evidence needed to evaluate the requirement IS available, continue
evaluating the requirement.

------------------------------------------------------------

STEP 3 — REQUIREMENT EVALUATION

Identify every applicable explicit requirement defined by the CURRENT
Fixed Rubric.

For each requirement determine:

- SATISFIED
- NOT SATISFIED
- NOT APPLICABLE

Do not invent requirements.

Do not use general ecommerce knowledge to create requirements.

Do not use the existence of an issue type as evidence of a requirement.

------------------------------------------------------------

STEP 4 — PASS

Return "pass" ONLY when every applicable explicit requirement is
SATISFIED.

If every applicable requirement is satisfied:

- verdict MUST be "pass";
- issues MUST be [];
- enrichment MUST be "";
- why_it_matters_for_agents MUST be "";
- example MUST be "".

STOP evaluating that check.

Do not search for additional improvements.

------------------------------------------------------------

STEP 5 — PARTIAL

Return "partial" when:

- the check is applicable;
- the required evidence needed for evaluation is available;
- at least one applicable explicit requirement is SATISFIED;
- at least one applicable explicit requirement is NOT SATISFIED; AND
- the Fixed Rubric's stated purpose for the check is still meaningfully
  achieved by the supplied data.

PARTIAL means the check is working to some meaningful extent but one or
more explicit requirements remain unsatisfied.

Do NOT convert PARTIAL to FAIL merely because:

- several requirements are unsatisfied;
- several issues exist;
- an issue is severe;
- remediation is difficult;
- remediation requires multiple changes;
- the data could be substantially improved;
- another check failed;
- another category changed;
- the resulting score is low.

Issue count does NOT determine PARTIAL versus FAIL.

Issue severity does NOT determine PARTIAL versus FAIL.

Remediation size does NOT determine PARTIAL versus FAIL.

------------------------------------------------------------

STEP 6 — FAIL

Return "fail" ONLY when ALL of the following are true:

1. The check is applicable.
2. The evidence required to evaluate the relevant requirement is
   available in the CURRENT supplied data.
3. An explicit requirement defined by the Fixed Rubric is NOT SATISFIED.
4. That unsatisfied requirement is fundamental to the purpose of the
   current check as established by the Fixed Rubric.
5. The CURRENT supplied evidence demonstrates that the check's purpose
   is fundamentally not achieved.

FAIL does NOT mean:

- information is missing;
- information could be improved;
- several issues exist;
- many fields are empty;
- the remediation is large;
- the issue severity is high;
- another check failed;
- the category score is low.

Do not infer a "core requirement" from general knowledge.

The Fixed Rubric must establish the requirement and its relevance to the
check.

If the evidence demonstrates a deficiency but the check's stated purpose
is still meaningfully achieved:
    verdict = "partial"

If the evidence needed to establish failure is unavailable and the Fixed
Rubric permits NA:
    verdict = "na"

If failure of the core purpose is not directly demonstrated:
    DO NOT return "fail".

------------------------------------------------------------

STEP 7 — STRICT PARTIAL VS FAIL TEST

Before returning "fail", ask internally:

1. What exact requirement from the Fixed Rubric is not satisfied?
2. What exact CURRENT supplied evidence proves that?
3. Does the Fixed Rubric establish this requirement as fundamental to
   the purpose of the check?
4. Does the CURRENT evidence demonstrate that the check's purpose is
   fundamentally not achieved?

If the answer to 4 is NO:
    return "partial" when the check is still meaningfully achieved.

If the required evidence is unavailable and NA is permitted:
    return "na".

Never return FAIL merely because a requirement is incomplete.

------------------------------------------------------------

STEP 8 — NO MOVING TARGET AFTER A FIX

If the CURRENT supplied data satisfies a requirement that was previously
unsatisfied, treat that requirement as SATISFIED.

Do not preserve the previous deficiency.

Do not search for a replacement deficiency merely because the original
deficiency is now resolved.

Do not make another requirement stricter because the original requirement
was fixed.

Do not create a new issue merely to keep the check PARTIAL or FAIL.

A check is allowed to become PASS after a successful correction.

------------------------------------------------------------

STEP 9 — INDEPENDENT NEW DEFICIENCY

After a requirement is satisfied, another issue may be reported ONLY if:

1. it violates a separate explicit requirement of the CURRENT Fixed
   Rubric;
2. the CURRENT supplied data independently demonstrates that violation;
3. the condition is semantically distinct;
4. it would still be a valid issue even if the previously resolved
   condition had never existed.

The existence of a previous issue or recommendation is NEVER evidence
for a new issue.

------------------------------------------------------------

STEP 10 — SAME INPUT STABILITY

For the same:

- CURRENT supplied data;
- Store Context;
- Fixed Rubric;
- check;

apply the same decision rules.

Do not change PASS/PARTIAL/FAIL/NA merely because the evaluation is being
repeated.

A different verdict is justified only by a genuine difference in the
CURRENT evidence, applicability, or Fixed Rubric.

------------------------------------------------------------

IMPORTANT:

"Requirement not satisfied" and "check fundamentally failed" are NOT
synonymous.

A failed requirement may produce PARTIAL.

A failed fundamental/core requirement may produce FAIL.

Unavailable required evidence may produce NA when the Fixed Rubric
permits NA.

All applicable requirements satisfied produces PASS.

============================================================
PROOF OF DEFECT
============================================================

Apply the following process independently to every check.

A. EXTRACT THE REQUIREMENT

Identify the exact conditions defined by the current check.

Only those conditions count.

B. FIND THE EVIDENCE

Search the supplied payload for evidence relevant to those
conditions.

Evidence may appear in any supplied product field, variant,
option, attribute, metafield, identifier, URL, or store context.

Use the complete supplied data.

C. TEST THE REQUIREMENT

Determine whether the supplied evidence satisfies the exact
requirement.

D. PROVE A DEFECT

A PARTIAL or FAIL is valid only when you can identify BOTH:

1. the exact requirement from the current check that is not
   satisfied;

2. the exact supplied field, value, object, or explicitly absent
   required data that proves it.

If both cannot be identified, do not create a deficiency.

E. FIX TEST — ISSUE-LEVEL, NOT CHECK-LEVEL

For every identified deficiency, determine the smallest concrete change
that would satisfy the SPECIFIC violated requirement represented by that
issue.

Ask:

"If exactly this problem were corrected in the supplied data, would the
specific violated requirement become satisfied?"

If YES:
    the issue is a valid independently supported deficiency.

It is NOT necessary for fixing one issue to make the entire check PASS.

A check may legitimately contain multiple independent deficiencies.

Do NOT invalidate an issue merely because another independent requirement
would remain unsatisfied after this issue is fixed.

A recommendation must address the actual violated requirement and must not
introduce additional requirements.

============================================================
EVIDENCE STANDARD
============================================================

PASS requires affirmative evidence that every applicable explicit
requirement is satisfied.

Do not mark a requirement as PASS merely because the evidence might
possibly be interpreted favorably.

Do not mark a requirement as PARTIAL or FAIL merely because the
data could be improved.

Use the exact wording of the Fixed Rubric and the actual supplied
evidence.

If the supplied data clearly satisfies the requirement, it passes.

If the supplied data clearly demonstrates that the requirement is
not satisfied, report the appropriate PARTIAL or FAIL.

If the supplied data does not demonstrate a violation, do not
invent a deficiency.

Uncertainty is not evidence of failure.

The existence of an issue type in the registry is not evidence
that the issue exists.

============================================================
MISSING OR EMPTY DATA
============================================================

Do not globally interpret:

"field empty = fail"

A missing or empty field matters only when the information represented
by that field is required by the specific Fixed Rubric check.

If the applicable requirement does not require the information,
do not create an issue.

If evidence required to judge a check is genuinely unavailable,
apply the NA rules.

Do not turn lack of evidence into FAIL unless the Fixed Rubric
explicitly makes the supplied source itself a required condition.

============================================================
STRUCTURED DATA AND METAFIELDS
============================================================

Evaluate structured data, attributes, and metafields according to
the actual Fixed Rubric.

A supplied value is evidence that the corresponding information
exists in the supplied data.

Do not automatically reject information because:

- the field is custom;
- the namespace is custom;
- the key is custom;
- the structure differs from another record;
- the field is not a standard definition;
- the information is represented differently elsewhere.

Do not automatically classify information as invalid, insufficient,
unstructured, non-comparable, or incorrect.

Determine whether the supplied information satisfies the exact
requirement of the current Fixed Rubric.

Do not invent a requirement about how data must be represented unless
the Fixed Rubric explicitly requires that representation.

============================================================
CATEGORY-AGNOSTIC EVALUATION
============================================================

Do not assume that all products, stores, or product categories
require the same information.

Do not automatically require any particular:

- attribute;
- field;
- specification;
- instruction;
- policy;
- document;
- identifier;
- metadata;
- structured representation;
- descriptive information.

Only treat information as required when the Fixed Rubric explicitly
requires it for the current check.

Do not infer requirements from:

- product category;
- product type;
- industry;
- common practice;
- ecommerce conventions;
- general recommendations;
- model knowledge.

============================================================
EVIDENCE
============================================================

Evidence must come directly from the supplied payload.

For every verdict, identify the actual supplied:

- field;
- value;
- object;
- attribute;
- metafield;
- option;
- variant;
- identifier;
- URL;
- store context;
- or explicitly absent required evidence.

Do not provide vague evidence such as:

- "the product is incomplete";
- "more information is needed";
- "the catalog is not optimized";
- "the data could be better".

Identify the exact observed evidence.

Do not fabricate evidence.

Do not infer values that are not supplied.

============================================================
ISSUE-DRIVEN VERDICTS
============================================================

For every check marked "partial" or "fail":

1. identify the concrete deficiency causing the verdict;
2. prove that deficiency using the supplied evidence;
3. determine which check owns that deficiency;
4. classify the actual problem before selecting an issue_type;
5. use an existing canonical issue_type when it accurately matches;
6. create a new issue_type only when the problem is genuinely
   distinct and no existing type accurately represents it.

Do not create an issue merely because information could be useful.

Do not create an issue for an optional field.

Do not create an issue for information not required by the current
Fixed Rubric.

Do not create an issue to increase the issue count.

Do not merge distinct deficiencies merely to reduce the issue count.

For PASS and NA:

issues MUST be [].

============================================================
MULTIPLE DISTINCT ISSUES
============================================================

A check may contain multiple distinct issues.

Do not assume:

- one check = one issue;
- one product = one issue;
- one check = one enrichment;
- one enrichment = one issue.

If multiple independent deficiencies are explicitly required by the
current Fixed Rubric and each is supported by the supplied evidence,
return each distinct deficiency separately.

Each distinct issue must have:

- its own issue_type;
- its own description;
- its own affected IDs where applicable;
- its own appropriate remediation.

Do not manufacture additional issues.

Do not split one defect into multiple issues.

Do not merge unrelated defects into one issue.

The number of issues must be determined by the actual evidence and
the Fixed Rubric.

============================================================
NEW ISSUE TYPE THRESHOLD
============================================================

A new issue_type is a LAST RESORT.

Do not create a new issue_type merely because:

- the wording is different;
- the description is more specific;
- the evidence uses a different value;
- an existing issue can be described with different wording;
- another issue_type sounds related;
- the model can think of a more convenient name;
- a different fix_action appears available.

Create a new issue_type ONLY when the underlying semantic defect is
genuinely distinct from every applicable registered issue_type AND
that defect is explicitly required by the CURRENT Fixed Rubric AND
that defect is directly proven by the CURRENT supplied data.

Different wording does not mean different issue.
Different evidence does not automatically mean different issue.
Different product data does not automatically mean different issue.
A different field or object may represent a different issue only when
the Fixed Rubric independently requires that field or object and the
current evidence proves the violation.

Before creating a new issue_type, exhaust the exact semantic matches
available in the current check and the legitimate cross-check reuse
rules below.

============================================================
ISSUE CLASSIFICATION — SEMANTIC OWNERSHIP FIRST
============================================================

For every PARTIAL or FAIL check, identify the actual problem from
the supplied evidence BEFORE selecting an issue_type.

Issue classification is semantic, not name-based.

The following must describe the SAME underlying problem:

- check_id;
- issue_type;
- description;
- evidence;
- affected object;
- affected field;
- affected IDs;
- remediation.

Follow these steps in EXACT order.

------------------------------------------------------------
STEP 1 — IDENTIFY THE ACTUAL PROBLEM
------------------------------------------------------------

First determine:

1. What exactly is wrong?
2. What object is affected?
3. What field or property is affected?
4. What exact supplied value or absence proves the problem?
5. What requirement of the CURRENT check is not satisfied?
6. What change would actually correct that problem?

Do NOT select an issue_type before answering these questions.

The issue_type must describe the actual observed problem.

Do not select an issue_type merely because its name looks similar.

------------------------------------------------------------
STEP 2 — DETERMINE CHECK OWNERSHIP
------------------------------------------------------------

Determine which CURRENT check owns the actual violated condition.

Ownership is determined by:

- the Fixed Rubric;
- the violated requirement;
- the supplied evidence;
- the semantic meaning of the problem.

Do not move a problem to another check because another check has
a similar issue type.

Do not change the current check_id merely to match an issue_type.

The issue must remain under the check whose Fixed Rubric actually
supports the observed deficiency.

------------------------------------------------------------
STEP 3 — CHECK THE CURRENT CHECK'S REGISTRY FIRST
------------------------------------------------------------

Look ONLY at the issue types registered under the CURRENT check first.

Compare the actual observed problem against every registered issue
type under that check.

Ask:

"Does this registered issue type describe the exact same semantic
problem?"

If YES:

- use that exact issue_type;
- status = "existing";
- copy the registered name exactly;
- preserve its semantic meaning;
- use the registered remediation semantics only as a compatibility
  reference;
- do not invent a different meaning for the registered issue.

If NO:

continue to STEP 4.

------------------------------------------------------------
STEP 4 — ISSUE TYPES FROM OTHER CHECKS
------------------------------------------------------------

An issue_type registered under another check MAY be reused under
the CURRENT check ONLY when ALL of the following are true:

1. It describes the EXACT SAME underlying problem.
2. It refers to the SAME affected object.
3. It refers to the SAME affected field or property.
4. It has the SAME semantic meaning.
5. Its registered remediation is compatible with the actual problem.
6. The problem independently violates the CURRENT check's Fixed
   Rubric.
7. Reusing it does not hide, rename, or distort the actual problem.

The existence of the same issue_type elsewhere is NEVER sufficient.

Do NOT reuse an issue_type merely because:

- its name looks similar;
- its wording looks similar;
- the affected data is related;
- the same fix_action exists;
- it would be convenient;
- another check already contains it.

If any semantic condition differs, DO NOT reuse it.

The current check remains the owner.

------------------------------------------------------------
STEP 5 — CREATE A NEW ISSUE TYPE WHEN NEEDED
------------------------------------------------------------

If the actual problem genuinely belongs to the CURRENT check, but:

- no issue type under the CURRENT check accurately describes it; and
- no issue type from another check is an exact semantic match that
  can legitimately be reused;

then CREATE A NEW ISSUE TYPE.

For a new issue:

- status = "new";
- use concise snake_case;
- describe the actual observed problem;
- keep the issue specific to the actual evidence;
- do not force the problem into an existing type;
- do not change the check_id merely to avoid creating a new type.

A new issue_type is correct when the problem is valid for the
CURRENT check but the registry does not contain a suitable semantic
match.

Do not create a new issue type that merely restates an existing one.

------------------------------------------------------------
STEP 6 — NEVER MAP BY NAME OR FIX ACTION ALONE
------------------------------------------------------------

Never perform:

"issue_type exists somewhere -> use it here."

Never perform:

"fix_action exists -> find an issue that can use it."

Always perform:

"understand problem
-> determine affected object
-> determine affected field
-> determine violated requirement
-> determine check ownership
-> compare semantic meaning
-> select exact existing issue type
OR
-> create a genuinely new issue type."

The string/name of an issue_type is not evidence.

The existence of a fix_action is not evidence.

A matching fix_action does not make two issue types semantically
equivalent.

------------------------------------------------------------
STEP 7 — FIX ACTION AS SEMANTIC COMPATIBILITY SIGNAL
------------------------------------------------------------

The application owns the executable fix_action, but the registered
fix_action remains an IMPORTANT semantic compatibility signal during
issue classification.

The application will ultimately resolve the executable fix from:

check_id + issue_type

However, when comparing otherwise similar candidate issue types, the
registered_fix_action may be used to verify whether the candidate
actually corresponds to the observed problem.

Therefore:

- keep registered_fix_action in the Issue Registry context;
- use it as a compatibility check, not as the primary classifier;
- do NOT invent fix_action values;
- do NOT create a new fix_action;
- do NOT return a model-invented fix_action as the classification;
- do NOT select an issue_type solely because its fix_action is
  convenient;
- do NOT change an issue_type solely to obtain a preferred fix_action.

The correct order is:

actual problem
-> affected object/field
-> violated requirement
-> check ownership
-> semantic issue_type match
-> registered_fix_action compatibility check
-> final issue_type

If the registered fix_action is incompatible with the observed
problem, the issue_type is NOT an exact semantic match. Do not force
the classification merely because the name looks similar.

The registry's fix_action does NOT create a requirement and does NOT
prove that an issue exists.

The application remains responsible for assigning the executable
fix_action after receiving the final check_id + issue_type.

------------------------------------------------------------
STEP 8 — OBJECT AND FIELD SEMANTICS
------------------------------------------------------------

Classify the issue according to the actual object and field affected
by the supplied evidence.

The affected object and field must be determined from the CURRENT
payload and the CURRENT requirement.

Do not infer the affected object from the issue_type name.
Do not infer the affected field from a similar issue elsewhere in
the registry.

If an existing issue type describes a different object, field, or
semantic condition, it MUST NOT be reused.

Use these generic semantic distinctions:

1. OBJECT SCOPE

Distinguish correctly between product-level, variant-level,
option-level, field-level, and store-level conditions.

If the evidence identifies a specific nested object or property,
classify the issue according to that actual object.
Do not broaden or narrow the object scope merely to match an
available issue type.

2. FIELD MEANING

Distinguish the actual meaning of the affected field or property.
A field's presence does not prove that its content satisfies the
requirement, and an empty field does not automatically prove failure.

Determine whether the requirement concerns the field's presence,
value, structure, consistency, relationship, or another explicitly
defined property. Use only the meaning established by the Fixed
Rubric.

3. VALUE VS FIELD OR NAME

A problem with the VALUE stored in a field is not automatically a
problem with the FIELD or NAME that contains that value. Likewise,
a problem with a field's structure is not automatically a problem
with the value itself.

Classify the actual semantic defect shown by the payload.

4. MISSING VS PRESENT-BUT-INVALID

A missing value and a present value that fails a structural, semantic,
or quality requirement are different conditions when the Fixed Rubric
distinguishes them.

Do not convert one into the other merely because the remediation may
be similar.

5. EVIDENCE SCOPE

The affected field, object, and IDs must be traceable directly to the
CURRENT payload. Do not infer them from the issue registry, a
previous result, or a convenient remediation.

The selected issue_type must describe this exact semantic condition.

------------------------------------------------------------
STEP 9 — COPY REGISTERED NAMES EXACTLY
------------------------------------------------------------

When an existing issue type is selected:

- copy the registry identifier exactly;
- do not rename it;
- do not shorten it;
- do not expand it;
- do not translate it;
- do not pluralize it;
- do not replace it with a synonym.

A problem already covered by the registry is not new merely because
the description uses different wording.

For a new issue_type, use concise English snake_case describing the
actual problem.

------------------------------------------------------------
STEP 10 — ONE DEFECT, ONE ISSUE
------------------------------------------------------------

One underlying defect must be reported once.

Do not create multiple issue types for the same defect.

Do not duplicate the same defect across checks.

However, genuinely independent deficiencies may be reported as
separate issues when each is explicitly supported by the Fixed
Rubric and current evidence.

------------------------------------------------------------
FINAL ISSUE VALIDATION
------------------------------------------------------------

Before returning every issue, internally verify:

1. What exactly is wrong?
2. What exact evidence proves it?
3. What object is affected?
4. What field is affected?
5. Which requirement is violated?
6. Which check owns that requirement?
7. Does the selected issue_type describe the exact problem?
8. Does the issue_type legitimately apply to this check?
9. If the issue_type exists under another check, is it truly the
   exact same semantic problem?
10. Is the registered remediation compatible with the problem?
11. Are the affected IDs correct and taken directly from the payload?
12. If no existing issue type is an exact semantic match, was a new
    issue_type created under the correct check?
13. If the actual problem were corrected, would this SAME check
    satisfy its existing Fixed Rubric?
14. Am I classifying the problem itself rather than selecting an
    issue_type or fix_action first?
15. Did I avoid creating this issue only because another category
    or check changed?

If any answer is NO, reconsider the classification before returning
the issue.

============================================================
MEASUREMENT OBSERVATIONS
============================================================

For actual measurements found in the supplied product data,
populate measurement_observations.

Each measurement observation MUST contain:

- product_id;
- field;
- raw_value;
- unit;
- dimension.

Use the exact values supplied in the payload.

Do not:

- invent measurements;
- convert values;
- normalize values;
- rewrite raw values;
- decide whether measurements are consistent;
- treat different unit strings as automatically inconsistent.

Preserve the supplied representation.

Do not generate a final consistency verdict unless the Fixed Rubric
explicitly requires one at this evaluation stage.

============================================================
CONSISTENCY OBSERVATIONS
============================================================

If the response schema contains consistency_observations, use them
only as factual observations from the supplied payload.

They must describe only information actually visible in the current
payload.

Do not turn observations into verdicts unless explicitly required
by the Fixed Rubric.

Do not invent a variation.

Do not report a variation that cannot be demonstrated from the
supplied data.

Do not create a consistency issue merely because different values
exist.

Only report an issue when the Fixed Rubric and Issue Registry
explicitly support that classification.

============================================================
SCORING DISCIPLINE
============================================================

Do NOT calculate numerical scores.

Do NOT calculate aggregate readiness.

Do NOT rank products.

Do NOT rank issues.

Do NOT assign scores based on issue count.

Do NOT modify verdicts to achieve a desired numerical result.

Do NOT modify verdicts to make category scores appear balanced.

The application calculates scores separately from the returned
verdicts.

Your responsibility is only to return accurate check-level verdicts,
evidence, issues, and recommendations.

============================================================
FIXED RUBRIC CHECKS
============================================================

{_rubric_prompt_block()}

The Fixed Rubric defines every check that must be evaluated.

Do not invent additional checks.

Do not skip any defined check.

Every defined check must appear in the response.

============================================================
ISSUE REGISTRY
============================================================

The Issue Registry below contains the canonical issue types available
for classification.

Each entry has:

[check_id] issue_type | registered_fix_action

The registered_fix_action is APPLICATION METADATA.

It is NOT an instruction to invent, return, or select a fix_action.

Use the exact issue_type string when an existing registered issue
is selected.

The existence of an issue type does NOT mean that the issue exists.

An issue must first be proven by:

1. the current payload;
2. the current Fixed Rubric;
3. semantic issue classification.

The registry does NOT override the Fixed Rubric.

The registry does NOT create new requirements.

The registry does NOT justify a deficiency.

The registry does NOT determine check ownership by name alone.

{issue_registry_block}

============================================================
AFFECTED VARIANT AND OPTION IDS
============================================================

Every issue MUST include:

- "affected_variant_ids"
- "affected_option_ids"

Rules:

1. Copy IDs exactly as they appear in the supplied payload.
2. Include a variant ID only when the issue actually concerns a
   specific variant.
3. Include an option ID only when the issue actually concerns a
   specific option.
4. If the issue applies to the whole product or store, use [].
5. If the relevant ID is not supplied, use [].
6. Never invent an ID.
7. Never guess an ID.
8. Never shorten or reformat an ID.
9. Never use a title, position, or other value as an ID.
10. Store-level issues must use [] for both fields.

============================================================
RECOMMENDATIONS
============================================================

For every PARTIAL or FAIL check:

- provide a concise human-readable "enrichment";
- provide a 1-2 sentence "why_it_matters_for_agents";
- provide a concrete "example" based only on the supplied data.

Recommendations must address the actual observed deficiency.

Do not create recommendations for deficiencies that do not exist.

Do not create generic recommendations unrelated to the evidence.

Do not recommend information that is not required by the current
Fixed Rubric.

Do not invent missing product or store attributes.

The recommendation must correspond to the actual issue and its
compatible remediation.

Do not make the recommendation broader than the violated
requirement.

For PASS and NA:

- issues MUST be [];
- enrichment MUST be "";
- why_it_matters_for_agents MUST be "";
- example MUST be "".

============================================================
AFFECTED PRODUCT IDS
============================================================

Only include product IDs in affected_product_ids when the supplied
evidence demonstrates that identifiable products are affected by
the relevant store-level or cross-product condition.

Rules:

- use only exact product IDs from the payload;
- never invent product IDs;
- never infer product IDs;
- if no specific products are affected, return [].

For per-product checks, use the product's own identity only when
the response schema requires it.

============================================================
NA VS FAIL — STRICT BOUNDARY
============================================================

NA and FAIL represent different situations.

NA:

Use "na" ONLY when:

- the check genuinely does not apply; OR
- the evidence required to evaluate the check is genuinely unavailable;
- AND the Fixed Rubric permits NA in that situation.

FAIL:

Use "fail" ONLY when:

- the check applies;
- the evidence required to evaluate the relevant requirement is
  available;
- the Fixed Rubric explicitly requires the condition;
- the CURRENT evidence demonstrates that the condition is not satisfied;
- AND failure of that condition means the check's stated purpose is
  fundamentally not achieved.

IMPORTANT:

Do NOT use NA because evidence is merely inconvenient to interpret.

Do NOT use NA because the data is poor when the supplied data is still
sufficient to evaluate the requirement.

Do NOT use FAIL because evidence is unavailable.

Do NOT use FAIL because a field is empty unless the Fixed Rubric makes
that field/value relevant to the current check.

Do NOT use FAIL because information could be improved.

Do NOT use FAIL because several issues exist.

Do NOT use FAIL because another check failed.

Do NOT use FAIL because the category score is low.

If required evidence is unavailable and NA is permitted:
    NA.

If evidence is available and the requirement is not satisfied but the
check's purpose remains meaningfully achieved:
    PARTIAL.

If evidence is available and a fundamental requirement is not satisfied
such that the check's purpose is fundamentally not achieved:
    FAIL.
    
============================================================
LANGUAGE AND OUTPUT
============================================================

Write the entire response strictly in:

{language}

Do not mix languages.

Return ONLY valid JSON.

Do not return:

- markdown;
- code fences;
- explanations outside JSON;
- conversational prose;
- aggregate scores;
- commentary before JSON;
- commentary after JSON.

============================================================
EXACT RESPONSE SHAPE
============================================================

{_expected_response_shape_example()}

Rules applying to the real response:

- Every check defined by the Fixed Rubric must be present.
- Every required product must contain its required check results.
- Every product must contain its required product identity fields.
- Every issue MUST contain:
  - issue_type;
  - status;
  - description.
- Every PARTIAL or FAIL check MUST contain at least one issue.
- Every PASS or NA check MUST contain:
  issues: []
- Evidence must be factual and based only on the supplied payload.
- Never omit a required check.
- Never invent a check.
- Never calculate aggregate scores.
- Never return information outside the required JSON schema.
- Do NOT return fix_action as an LLM-generated classification field.
- The application assigns fix_action from check_id + issue_type
  after receiving this response.

============================================================
CURRENT STORE INFORMATION
============================================================

Store URL:

{store_url}

Store Context:

{json.dumps(store_context, ensure_ascii=False, indent=2)}

============================================================
CURRENT PRODUCTS CATALOGUE PAYLOAD
============================================================

{json.dumps(products, ensure_ascii=False, indent=2)}

============================================================
FINAL INSTRUCTION
============================================================

Evaluate ONLY the current supplied data.

Apply ONLY the Fixed Rubric.

For every check:

current evidence
-> current requirement
-> current verdict.

For every PARTIAL or FAIL:

current evidence
-> actual deficiency
-> affected object/field
-> check ownership
-> semantic issue classification
-> existing exact issue type OR genuinely new issue type
-> evidence-backed recommendation.

The issue classification process MUST happen in that order.

Never reverse this process.

Never start with an issue_type and search for evidence to justify it.

Never start with a fix_action and search for a problem that it can fix.

Never select an issue_type because its name is similar to the
observed problem.

Never select an issue_type because its fix_action is convenient.

Never create a problem merely because the registry contains a
corresponding issue type.

Never create a problem merely because the data could be improved.

Never create a problem merely because another category changed.

Never change a satisfied check into another issue.
Never replace a resolved requirement with a newly invented deficiency.
Never preserve an old issue merely because it existed before.
Never assume a fix failed unless the CURRENT data itself demonstrates
that the relevant requirement remains unsatisfied.

Never transfer requirements between checks.

Never use another check's result as evidence for the current check.

Never use information outside the current payload.

Remember:

The LLM's responsibility is:

evidence
-> requirement
-> verdict
-> actual problem
-> check ownership
-> issue_type
-> description
-> affected IDs
-> recommendation.

The application's responsibility is:

check_id + issue_type
-> registry lookup
-> fix_action.

Do NOT return or invent the final fix_action yourself.

For existing issue types, copy the issue_type exactly as registered.

For genuinely new issues, create a concise snake_case issue_type only
when the current Fixed Rubric and evidence prove that the problem is
real and no existing semantic issue type accurately represents it.

Same evidence + same rubric = same semantic interpretation.

Different evidence may legitimately produce a different issue.

Return ONLY the required JSON.
""".strip()


def analyze_with_ollama(products: list[dict[str, Any]], store_context: dict[str, Any], store_url: str, model: str, language="English") -> dict[str, Any]:
    payload = {
        "model": model,
        "prompt": (
            build_prompt(products, store_context, store_url, language)
            + "\n\nReturn ONLY valid JSON matching the rubric schema: "
              "store_verdicts and products. Each product must contain product_id, title, and verdicts. "
              "Each verdict must contain verdict and evidence, plus enrichment/why_it_matters_for_agents/example "
              "when verdict is partial or fail. Do not return readiness_scores, priorities, or aggregate recommendations."
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


def _check_verdict_schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "verdict": {
                "type": "STRING",
                "enum": ["pass", "partial", "fail", "na"],
            },
            "evidence": {
                "type": "STRING",
            },
            "issues": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "issue_type": {"type": "STRING", "minLength": 1},
                        "status": {"type": "STRING", "enum": ["existing", "new"]},
                        "description": {"type": "STRING", "minLength": 1},
                        "affected_variant_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "affected_option_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                    "required": [
                        "issue_type", "status", "description",
                        "affected_variant_ids", "affected_option_ids",
                    ],
                    "additionalProperties": False,
                },
            },
            "enrichment": {
                "type": "STRING",
                "minLength": 1,
            },
            "why_it_matters_for_agents": {
                "type": "STRING",
                "minLength": 1,
            },
            "example": {
                "type": "STRING",
                "minLength": 1,
            },
        },
        "required": [
            "verdict",
            "evidence",
            "issues",
            "enrichment",
            "why_it_matters_for_agents",
            "example",
        ],
        "additionalProperties": False,
    }

def enrichment_report_schema() -> dict[str, Any]:
    product_check_ids = llm_product_check_ids()

    store_check_ids = llm_store_check_ids()

    return {
        "type": "OBJECT",
        "properties": {
            "store_verdicts": {
                "type": "OBJECT",
                "properties": {cid: _check_verdict_schema() for cid in store_check_ids},
                "required": store_check_ids,
            },
            "products": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "product_id": {"type": "STRING"},
                        "title": {"type": "STRING"},
                        "verdicts": {
                            "type": "OBJECT",
                            "properties": {cid: _check_verdict_schema() for cid in product_check_ids},
                            "required": product_check_ids,
                        },
                    },
                    "required": ["product_id", "title", "verdicts"],
                },
            },
            "consistency_observations": {
                "type": "object",
                "description": "Batch-level factual observations about catalog consistency. Do not include a final consistency verdict.",
                "properties": {
                    "fields_observed": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "option_names": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "product_types": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "format_variations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string"},
                                "formats": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": ["field", "formats"],
                            "additionalProperties": False,
                        },
                    },
                    "issues": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "issue_type": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["existing", "new"],
                                },
                                "field": {"type": "string"},
                                "description": {"type": "string"},
                                "affected_product_ids": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                            "required": [
                                "issue_type",
                                "status",
                                "field",
                                "description",
                                "affected_product_ids",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "fields_observed",
                    "option_names",
                    "product_types",
                    "format_variations",
                    "issues",
                ],
                "additionalProperties": False,
            },
        },
        "required": [
            "store_verdicts",
            "products",
            "consistency_observations",
        ],
    }

def _gemini_consistency_observations_schema() -> dict:
    return {
        "type": "OBJECT",
        "properties": {
            "fields_observed": {
                "type": "OBJECT",
                "properties": {},
                "additionalProperties": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "option_names": {"type": "ARRAY", "items": {"type": "STRING"}},
            "product_types": {"type": "ARRAY", "items": {"type": "STRING"}},
            "format_variations": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "field": {"type": "STRING"},
                        "formats": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                    "required": ["field", "formats"],
                },
            },
            "measurement_observations": {
                "type": "array",
                "description": "Structured observations of actual measurements found in the product batch. These are factual extractions only; they are not consistency verdicts.",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {
                            "type": "string",
                        },
                        "field": {
                            "type": "string",
                        },
                        "raw_value": {
                            "type": "string",
                        },
                        "unit": {
                            "type": "string",
                        },
                        "dimension": {
                            "type": "string",
                        },
                    },
                    "required": [
                        "product_id",
                        "field",
                        "raw_value",
                        "unit",
                        "dimension",
                    ],
                    "additionalProperties": False,
                },
            },
            "issues": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "issue_type": {"type": "STRING"},
                        "status": {"type": "STRING", "enum": ["existing", "new"]},
                        "field": {"type": "STRING"},
                        "description": {"type": "STRING"},
                        "affected_product_ids": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                    "required": ["issue_type", "status", "field", "description", "affected_product_ids"],
                },
            },
        },
        "required": [
            "fields_observed",
            "option_names",
            "product_types",
            "format_variations",
            "measurement_observations",
            "issues",
        ],
    }

def _gemini_verdict_schema() -> dict[str, Any]:
    product_ids = llm_product_check_ids()
    store_ids = llm_store_check_ids()
    return {
        "type": "OBJECT",
        "properties": {
            "store_verdicts": {
                "type": "OBJECT",
                "properties": {cid: _check_verdict_schema() for cid in store_ids},
                "required": store_ids,
            },
            "products": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "product_id": {"type": "STRING"},
                        "title": {"type": "STRING"},
                        "verdicts": {
                            "type": "OBJECT",
                            "properties": {cid: _check_verdict_schema() for cid in product_ids},
                            "required": product_ids,
                        },
                    },
                    "required": ["product_id", "title", "verdicts"],
                },
            },
            "consistency_observations": _gemini_consistency_observations_schema(),  
        },
        "required": ["store_verdicts", "products", "consistency_observations"],
    }

def _expected_response_shape_example() -> str:
    """Literal JSON example of the exact response shape, generated from CHECKS
    so it can't drift from the rubric. Built with json.dumps and inserted into
    the prompt as a variable — never hand-typed literal braces in the f-string."""
    
    product_check_ids = llm_product_check_ids()

    store_check_ids = llm_store_check_ids()

    def _example_check(cid: str) -> dict:
        return {
            "verdict": "partial",
            "evidence": f"<exact field/value observed for {cid}>",
            "issues": [
                {
                    "issue_type": "<canonical_or_new_issue_type>",
                    "status": "existing",
                    "description": "<factual description of the specific issue>",
                    "affected_variant_ids": ["<exact variant id from payload, or empty>"],
                    "affected_option_ids": ["<exact option id from payload, or empty>"],
                }
            ],
            "enrichment": "<short fix name — flat string, not an object>",
            "why_it_matters_for_agents": "<1-2 sentence explanation — flat string>",
            "example": "<concrete fix using this product/store's actual data — flat string>",
        }

    example = {
        "store_verdicts": {cid: _example_check(cid) for cid in store_check_ids[:2]},
        "products": [
            {
                "product_id": "<product_id>",
                "title": "<product title>",
                "verdicts": {cid: _example_check(cid) for cid in product_check_ids[:2]},
            }
        ],
        "consistency_observations": {
            "fields_observed": {"<field_name>": ["<value1>", "<value2>"]},
            "option_names": ["<option_name>"],
            "product_types": ["<product_type>"],
            "format_variations": [{"field": "<field>", "formats": ["<format1>", "<format2>"]}],
            "issues": [
                {
                    "issue_type": "<canonical_or_new_issue_type>",
                    "status": "existing",
                    "field": "<field>",
                    "description": "<factual description>",
                    "affected_product_ids": ["<product_id>"],
                }
            ],
        },
    }
    return json.dumps(example, indent=2, ensure_ascii=False)

def _collect_valid_ids(product: dict | None) -> tuple[set[str], set[str]]:
    if not product:
        return set(), set()
    variant_ids = {
        str(v.get("id") or v.get("variant_id"))
        for v in (product.get("variants") or [])
        if v.get("id") or v.get("variant_id")
    }
    option_ids = {
        str(o.get("id") or o.get("option_id"))
        for o in (product.get("options") or [])
        if o.get("id") or o.get("option_id")
    }
    return variant_ids, option_ids


def _clean_ids(raw: Any, valid: set[str], cid: str, label: str) -> list[str]:
    if not isinstance(raw, list):
        return []
    cleaned = []
    for value in raw:
        value = str(value).strip()
        if value in valid:
            if value not in cleaned:
                cleaned.append(value)
        elif value:
            print(f"[Warning] {cid}: dropping {label} {value!r} — not found in product payload")
    return cleaned

def _extract_verdicts_and_texts(
    product_entry: dict,
    check_ids: list[str],
    raw_product: dict | None = None,
) -> tuple[dict, dict, dict]:

    verdicts, texts, issues = {}, {}, {}
    valid_variant_ids, valid_option_ids = _collect_valid_ids(raw_product)

    raw = product_entry.get("verdicts")
    if not isinstance(raw, dict) or not raw:
        fallback = {
            k: v for k, v in product_entry.items()
            if k not in ("product_id", "title", "verdicts")
        }
        if fallback:
            print("[Warning] 'verdicts' missing/empty — recovered checks from flat sibling keys")
        raw = fallback

    for cid in check_ids:
        entry = raw.get(cid)

        if not isinstance(entry, dict) or not entry:
            print(f"[Warning] LLM omitted check {cid!r} — defaulting to 'na'")
            entry = {
                "verdict": "na", "evidence": "not returned by model", "issues": [],
                "enrichment": "", "why_it_matters_for_agents": "", "example": "",
            }

        enrichment_field = entry.get("enrichment")
        if isinstance(enrichment_field, dict):
            print(f"[Warning] {cid} returned nested enrichment object — flattening")
            nested = enrichment_field
            entry = {**entry}
            entry["enrichment"] = nested.get("name") or nested.get("title") or ""
            if not entry.get("why_it_matters_for_agents"):
                entry["why_it_matters_for_agents"] = nested.get("why_it_matters_for_agents", "")
            if not entry.get("example"):
                entry["example"] = nested.get("example", "")

        verdict = entry.get("verdict")

        if verdict not in ("pass", "partial", "fail", "na"):
            print(f"[Warning] Invalid verdict {verdict!r} for {cid} — defaulting to 'na'")
            verdict = "na"
            entry = {**entry, "verdict": "na"}

        if verdict in ("partial", "fail"):
            required = ("enrichment", "why_it_matters_for_agents", "example")
            for field in required:
                if not entry.get(field):
                    print(f"[Warning] {cid} ({verdict}) missing {field!r} — using placeholder")
                    entry[field] = entry.get(field) or f"Not specified by model for {cid}."

        raw_issues = entry.get("issues", [])
        if not isinstance(raw_issues, list):
            print(f"[Warning] Invalid issues for {cid}: expected a list — treating as empty")
            raw_issues = []

        normalized_issues = []
        for issue in raw_issues:
            if not isinstance(issue, dict):
                print(f"[Warning] Invalid issue entry for {cid} — skipping")
                continue

            issue_type = issue.get("issue_type")
            description = issue.get("description")

            if not issue_type or not isinstance(issue_type, str):
                print(f"[Warning] Issue for {cid} missing/invalid issue_type — skipping")
                continue

            status = "existing" if is_valid_issue_type(cid, issue_type) else "new"

            if not description:
                description = f"Observed issue: {issue_type.replace('_', ' ')}."

            if is_valid_issue_type(cid, issue_type):
                status = "existing"

            else:
                found = find_issue_definition(issue_type)

                if found is not None:
                    canonical_check_id, _ = found
                    status = "existing"

                    print(
                        f"[Issue Mapping] {issue_type!r} "
                        f"from check {cid!r} → canonical check {canonical_check_id!r}"
                    )
                else:
                    status = "new"

                    print(
                        f"[Issue Discovery] New unregistered issue "
                        f"{issue_type!r} under check {cid!r}"
                    )

            normalized_issues.append({
                "issue_type": issue_type,
                "status": status,
                "description": description,
                "affected_variant_ids": _clean_ids(
                    issue.get("affected_variant_ids"), valid_variant_ids, cid, "variant id"),
                "affected_option_ids": _clean_ids(
                    issue.get("affected_option_ids"), valid_option_ids, cid, "option id"),
            })

        if verdict in ("pass", "na") and normalized_issues:
            dropped = [i["issue_type"] for i in normalized_issues]
            print(f"[Warning] {cid} has issues {dropped} but verdict is {verdict} — dropping issues, keeping verdict")
            normalized_issues = []
        if verdict in ("partial", "fail") and normalized_issues:
            has_existing_issue = any(
                issue["status"] == "existing"
                for issue in normalized_issues
            )

            if not has_existing_issue:
                print(
                    f"[Issue Discovery] {cid} has only new/unregistered issues "
                    f"— excluding them from scoring."
                )
                verdict = "na"

        verdicts[cid] = verdict
        texts[cid] = {k: entry.get(k, "") for k in ("enrichment", "why_it_matters_for_agents", "example")}
        issues[cid] = normalized_issues

    return verdicts, texts, issues

def deduplicate_normalized_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple, dict[str, Any]] = {}

    for issue in issues:
        key = (issue.get("product_id"), issue.get("check_id"), issue.get("issue_type"))

        if key not in merged:
            merged[key] = {**issue}
            continue

        for field in ("affected_variant_ids", "affected_option_ids"):
            merged[key][field] = list(dict.fromkeys(
                (merged[key].get(field) or []) + (issue.get(field) or [])
            ))

    return list(merged.values())

def _product_image_url(product: dict | None) -> str | None:
    img = (product or {}).get("image")
    return img.get("src") if isinstance(img, dict) else None


def _variant_display(v: dict, product: dict) -> dict[str, Any]:
    own = (v.get("image") or {}).get("src")
    return {
        "id": v.get("id"),
        "title": v.get("title"),
        "selected_options": v.get("selectedOptions") or [],
        "image_url": own or _product_image_url(product),
        "image_source": "variant" if own else "product",
    }


def _option_display(o: dict) -> dict[str, Any]:
    return {"id": o.get("id"), "name": o.get("name"), "values": o.get("values") or []}


def _enrich_issue(
    issue: dict[str, Any],
    product_lookup: dict[str, dict],
) -> dict[str, Any]:
    product = product_lookup.get(str(issue.get("product_id") or ""))

    if product:
        variants = {str(v.get("id")): v for v in product.get("variants") or []}
        options = {str(o.get("id")): o for o in product.get("options") or []}
        issue["product_title"] = product.get("title")
        issue["product_image_url"] = _product_image_url(product)
        issue["affected_variants"] = [
            _variant_display(variants[vid], product)
            for vid in issue.get("affected_variant_ids") or [] if vid in variants
        ]
        issue["affected_options"] = [
            _option_display(options[oid])
            for oid in issue.get("affected_option_ids") or [] if oid in options
        ]
    else:
        issue.setdefault("affected_variants", [])
        issue.setdefault("affected_options", [])

    # for consistency issues
    enriched_targets = []
    for t in issue.get("targets") or []:
        tp = product_lookup.get(str(t.get("product_id") or ""))
        if not tp:
            continue
        vmap = {str(v.get("id")): v for v in tp.get("variants") or []}
        omap = {str(o.get("id")): o for o in tp.get("options") or []}
        enriched_targets.append({
            "product_id": t["product_id"],
            "product_title": tp.get("title"),
            "product_image_url": _product_image_url(tp),
            "options": [_option_display(omap[i]) for i in t.get("option_ids") or [] if i in omap],
            "variants": [_variant_display(vmap[i], tp) for i in t.get("variant_ids") or [] if i in vmap],
        })
    issue["targets"] = enriched_targets
    return issue

def assemble_report_from_verdicts(
    raw_response: dict[str, Any],
    products: list[dict[str, Any]],
    store_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    
    _product_lookup = {str(p.get("id") or p.get("product_id")): p for p in products}
    consistency_observations = raw_response.get(
        "consistency_observations",
        {}
    )
    # LLM-only verdicts (existing extraction, but only for llm_store_check_ids())
    store_verdicts, store_texts, store_issues = _extract_verdicts_and_texts(
        {"verdicts": raw_response.get("store_verdicts", {})},
        llm_store_check_ids(), 
    )

    
    deterministic_store = run_store_deterministic_checks(store_context)
    for cid, result in deterministic_store.items():
        store_verdicts[cid] = result["verdict"]
        store_texts[cid] = {
            "enrichment": "", "why_it_matters_for_agents": "", "example": "",
        }
        

    normalized_store_issues = []

    for check_id, issue_list in store_issues.items():
        if store_context is None and check_id in STORE_CONTEXT_REQUIRED_CHECKS:
            continue

        for issue in issue_list:
            normalized_store_issues.append(
                normalize_issue(
                    check_id=check_id,
                    issue=issue,
                )
            )

    for cid, result in deterministic_store.items():
        for issue in result.get("issues", []):
            normalized_store_issues.append(
                normalize_issue(
                    check_id=cid,
                    issue=issue,
                )
            )


    # ---------------------------------------------------------
    # DETERMINISTIC CATALOG CONSISTENCY
    # ---------------------------------------------------------

    deterministic_consistency = check_catalog_consistency(
        products,
        consistency_observations.get("measurement_observations"),
    )

    print("\n" + "=" * 80)
    print("[AUDIT DEBUG] DETERMINISTIC CONSISTENCY")
    print("=" * 80)
    print(f"Products supplied: {len(products)}")
    print(f"Verdict: {deterministic_consistency.get('verdict')}")
    print(f"Evidence: {deterministic_consistency.get('evidence')}")
    print(
        f"Affected product IDs: "
        f"{deterministic_consistency.get('affected_product_ids', [])}"
    )
    print(
        f"Issue count: "
        f"{len(deterministic_consistency.get('issues', []))}"
    )
    print(
        json.dumps(
            deterministic_consistency.get("issues", []),
            indent=2,
            ensure_ascii=False,
        )
    )
    print("=" * 80)

    store_verdicts["consistency"] = deterministic_consistency["verdict"]

    store_texts["consistency"] = {
        "enrichment": "",
        "why_it_matters_for_agents": "",
        "example": "",
    }

    for issue in deterministic_consistency.get("issues", []):
        issue_type = issue.get("issue_type")
        description = issue.get("description")

        if not issue_type or not description:
            continue

        status = (
            "existing"
            if is_valid_issue_type("consistency", issue_type)
            else "new"
        )

        normalized_store_issues.append(
            normalize_issue(
                check_id="consistency",
                issue={
                    "issue_type": issue_type,
                    "status": status,
                    "description": description,
                    "targets": issue.get("targets") or [],
                },
                field=issue.get("field"),
                affected_product_ids=(
                    issue.get("affected_product_ids") or []
                ),
            )
        )

    all_product_verdicts = {}
    all_product_texts: dict[str, dict] = {}
    normalized_product_issues = []
    products_out = []

    for p in raw_response.get("products", []):
        pid = p.get("product_id")
        raw_product = _product_lookup.get(str(pid))

        v, t, i = _extract_verdicts_and_texts(p, llm_product_check_ids(), raw_product)

        deterministic = run_product_deterministic_checks(raw_product) if raw_product else {}
        for cid, result in deterministic.items():
            v[cid] = result["verdict"]
            t[cid] = {"enrichment": "", "why_it_matters_for_agents": "", "example": ""}
            i[cid] = result.get("issues", [])

        if raw_product:
            print("\n========== DESCRIPTION DEBUG ==========")
            print("Product:", pid)

            print("BEFORE override:")
            print("  product_understanding =", v.get("product_understanding"))
            print("  product_clarity       =", v.get("product_clarity"))

            empty_desc = check_description_presence(raw_product)

            print("empty_desc result =", empty_desc)

            if empty_desc is not None:
                print(
                        f"OVERRIDING product_understanding: "
                        f"{v.get('product_understanding')} -> {empty_desc['verdict']}"
                    )
                v["product_understanding"] = empty_desc["verdict"]
                t["product_understanding"] = {
                    "enrichment": "Add Product Description",
                    "why_it_matters_for_agents": "Agents need an itemized breakdown of what is included to match customer search intent.",
                    "example": f"Add a description for '{raw_product.get('title')}' specifying what is in the package and who it is for.",
                }
                i["product_understanding"] = [
                    {
                        "issue_type": "insufficient_product_description",
                        "status": "existing",
                        "description": empty_desc.get("evidence", "Product description is empty or a stub."),
                        "affected_variant_ids": [],
                        "affected_option_ids": [],
                    }
                ]

                print(
                    f"OVERRIDING product_clarity: "
                    f"{v.get('product_clarity')} -> {empty_desc['verdict']}"
                )
                v["product_clarity"] = empty_desc["verdict"]
                t["product_clarity"] = {
                    "enrichment": "Add Usage and Care Guidelines",
                    "why_it_matters_for_agents": "Clear instructions prevent customer confusion and returns.",
                    "example": f"Add care, sizing, or how-to-use instructions for '{raw_product.get('title')}'.",
                }
                i["product_clarity"] = [
                    {
                        "issue_type": "insufficient_product_description",
                        "status": "existing",
                        "description": "No product usage, care, or maintenance instructions are provided.",
                        "affected_variant_ids": [],
                        "affected_option_ids": [],
                    }
                ]
            empty_type = check_product_type_presence(raw_product)

            if (
                empty_type is not None
                and v.get("comparable_attributes") == "pass"
            ):
                v["comparable_attributes"] = "partial"
                i["comparable_attributes"] = (
                    i.get("comparable_attributes", [])
                    + empty_type.get("issues", [])
                )
        print("AFTER override:")
        print("  product_understanding =", v.get("product_understanding"))
        print("  product_clarity       =", v.get("product_clarity"))
        print("=======================================\n")
        all_product_verdicts[pid] = v
        all_product_texts[pid] = t
        for check_id, issue_list in i.items():
            for issue in issue_list:
                normalized_product_issues.append(normalize_issue(check_id=check_id, issue=issue, product_id=pid))

        products_out.append({
            "product_id": pid,
            "title": p.get("title"),
            "image_url": (
                raw_product.get("image", {}).get("src")
                if raw_product
                and isinstance(raw_product.get("image"), dict)
                else None
            ),
            "missing_enrichments": build_product_recommendations(
                                        v,
                                        t,
                                        [
                                            {
                                                **issue,
                                                "check_id": check_id,
                                            }
                                            for check_id, issue_list in i.items()
                                            for issue in issue_list
                                        ],
                                    ),
        })
    normalized_product_issues = deduplicate_normalized_issues(normalized_product_issues)
    normalized_product_issues = [_enrich_issue(i, _product_lookup) for i in normalized_product_issues]
    normalized_store_issues = [_enrich_issue(i, _product_lookup) for i in normalized_store_issues]
    scores = compute_scores(all_product_verdicts, store_verdicts)
    store_recs = build_store_recommendations(store_verdicts, store_texts, all_product_verdicts, all_product_texts, normalized_store_issues,)
    print("\n" + "=" * 80)
    print("[AUDIT DEBUG] FINAL ASSEMBLED REPORT")
    print("=" * 80)

    print("[Scores]")
    print(json.dumps(scores, indent=2, ensure_ascii=False))

    print("\n[Store Verdicts]")
    print(json.dumps(store_verdicts, indent=2, ensure_ascii=False))

    print("\n[Store Issues]")
    print(
        f"Count: {len(normalized_store_issues)}"
    )
    print(
        json.dumps(
            normalized_store_issues,
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n[Product Issues]")
    print(
        f"Count: {len(normalized_product_issues)}"
    )

    print("\n[Store Recommendations]")
    print(
        f"Count: {len(store_recs)}"
    )

    print("\n[Consistency Observations — diagnostic only]")
    print(
        json.dumps(
            consistency_observations,
            indent=2,
            ensure_ascii=False,
        )
    )

    print("=" * 80 + "\n")
    return {
        "readiness_scores": scores,
        "store_level_recommendations": store_recs,
        "products": products_out,
        "consistency_observations": consistency_observations,
        "issues": {"store": normalized_store_issues, "products": normalized_product_issues},
    }

def analyze_with_gemini(products: list[dict[str, Any]], store_context: dict[str, Any], store_url: str, model: str, language="English") -> dict[str, Any]:
    _gemini_rate_limit()
    request_id = random.randint(10000, 99999)

    print(f"[Gemini-{request_id}] Starting")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("Set GEMINI_API_KEY in .env. You can create one in Google AI Studio.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = build_prompt(products, store_context, store_url, language)
    
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": _gemini_verdict_schema(),
            "temperature": 0.0,
            "topK": 1,
            "topP": 1.0,
            "seed": 42,
            "thinkingConfig": {
                "thinkingBudget": 0
            },
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
                products, store_context, store_url, fallback_model, language
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
        print(text)

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

    report.setdefault("provider", "gemini")
    report.setdefault("store_url", store_url)
    return report



def analyze_with_bedrock_claude(
    products: list[dict[str, Any]],
    store_context: dict[str, Any],
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

    prompt = build_prompt(products, store_context, store_url, language)

    system = (
        "You are an expert e-commerce data strategist and data engineer. "
        "Analyze the supplied Shopify store context and product batch against ONLY the fixed rubric in the user prompt. "
        "Return ONLY raw JSON matching the requested verdict schema. "
        "Do not calculate readiness scores or generate final recommendations outside each verdict entry. "
        "Every store check must appear in store_verdicts. Every product check must appear in each product's verdicts. "
        "Use pass, partial, fail, or na. Include exact evidence. For partial/fail, include a concrete enrichment, "
        "why_it_matters_for_agents, and example based only on the supplied data. "
        "Never invent product IDs or values. No markdown or prose outside JSON."
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

def _openai_verdict_schema() -> dict[str, Any]:
    product_check_ids = [
        c["id"] for checks in CHECKS.values() for c in checks if c["level"] == "product"
    ]
    store_check_ids = [
        c["id"] for checks in CHECKS.values() for c in checks if c["level"] == "store"
    ]

    verdict = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "partial", "fail", "na"]},
            "evidence": {"type": "string"},
            "enrichment": {"type": "string"},
            "why_it_matters_for_agents": {"type": "string"},
            "example": {"type": "string"},
        },
        "required": ["verdict", "evidence", "enrichment", "why_it_matters_for_agents", "example"],
    }

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "store_verdicts": {
                "type": "object",
                "additionalProperties": False,
                "properties": {cid: verdict for cid in store_check_ids},
                "required": store_check_ids,
            },
            "products": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "product_id": {"type": "string"},
                        "title": {"type": "string"},
                        "verdicts": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {cid: verdict for cid in product_check_ids},
                            "required": product_check_ids,
                        },
                    },
                    "required": ["product_id", "title", "verdicts"],
                },
            },
        },
        "required": ["store_verdicts", "products"],
    }


def analyze_with_openai(
    products: list[dict[str, Any]],
    store_context: dict[str, Any],
    store_url: str,
    model: str,
    language="English",
) -> dict[str, Any]:
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
                        "Return only raw JSON matching the supplied fixed rubric schema. "
                        "Do not calculate scores or generate aggregate recommendations. "
                        "Every store check must be in store_verdicts and every product check must be in each product verdicts. "
                        "Use only evidence present in the supplied store context and product payload. "
                        "Never invent product IDs or values."
                    ),
                },
                {"role": "user", "content": build_prompt(products, store_context, store_url, language)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "shopify_agent_discoverability_verdicts",
                    "strict": True,
                    "schema": _openai_verdict_schema(),
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
    store_context: dict[str, Any],
    store_url: str,
    provider: str,
    model: str,
    language: str = "English",
) -> dict[str, Any]:
    if provider == "gemini":
        return analyze_with_gemini(products, store_context, store_url, model, language)
    if provider == "ollama":
        return analyze_with_ollama(products, store_context, store_url, model, language)
    if provider == "openai":
        return analyze_with_openai(products, store_context, store_url, model, language)
    if provider == "bedrock":
        return analyze_with_bedrock_claude(products, store_context, store_url, model, language)
    raise ValueError(f"Unsupported provider: {provider!r}")

def escape_html(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)





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
        "affects_products":   "Applies to {n} products",
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
        "affects_products":   "Betrifft {n} Produkte",
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
        "affects_products":   "S'applique à {n} produits",
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
        "affects_products":   "Se aplica a {n} productos",
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
        "affects_products":   "{n}件の商品に適用",
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



def render_readiness_scores(
    scores: dict[str, int],
    labels: dict[str, str],
) -> str:

    items = []

    if "overall" in scores:
        items.append(
            (labels["score_overall"], scores["overall"])
        )

    if "ucp_commerce_flows" in scores:
        items.append(
            (labels["score_ucp"], scores["ucp_commerce_flows"])
        )

    if "mcp_knowledge" in scores:
        items.append(
            (labels["score_mcp"], scores["mcp_knowledge"])
        )

    if "catalog_enrichment" in scores:
        items.append(
            (labels["score_catalog"], scores["catalog_enrichment"])
        )

    if "safety_policies" in scores:
        items.append(
            (labels["score_safety"], scores["safety_policies"])
        )

    if not items:
        return ""

    def band(value: int) -> str:
        if value >= 60:
            return "strong"
        if value >= 40:
            return "fair"
        return "weak"

    cards = "".join(
        f"""
        <div class="score-card">
          <div class="score-circle score-circle--{band(value)}">
            <span>{value}</span>
          </div>
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
    .recommendation__header {{ display: flex; align-items: flex-start; gap: 8px; margin-bottom: 7px; flex-wrap: wrap; }}
    .recommendation p {{ margin: 0 0 8px; color: #3f4a5a; }}
    .example {{ padding: 8px 9px; color: #324150; background: #f4efe6; border-left: 3px solid #c47d52; border-radius: 5px; }}
    .pill {{ display: inline-block; min-width: 44px; padding: 3px 7px; border-radius: 999px; color: #ffffff; font-size: 8px; font-weight: 800; text-align: center; text-transform: uppercase; letter-spacing: .05em; }}
    .pill--high {{ background: #b43d31; }} .pill--medium {{ background: #b87524; }} .pill--low {{ background: #3d756b; }}
    .pill--affected {{ background: #17695b; }}
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
      {render_readiness_scores(
            report.get("readiness_scores") or {},
            labels
        )}
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


# ── Agent discovery file readiness ────────
_AGENT_DISCOVERY_PATHS = {
    "agents_md":     "/agents.md",
    "llms_txt":      "/llms.txt",
    "llms_full_txt": "/llms-full.txt",
    "ucp_manifest":  "/.well-known/ucp",
}

_DEFAULT_FILE_MARKERS = (
    "shopify.com/start",
    "this file was automatically generated by shopify",
    "powered by shopify",
)

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
            raw = response.read(200_000) 
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
        "_body": text,  
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

    bodies = {
    key: results[key].get("_body", "")
    for key in results
    }

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
_AGENT_DISCOVERY_TEMPLATE_KEYS = (
    "agents_md",
    "llms_txt",
    "llms_full_txt",
)
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
            if not info.get("mirrors_agents_md"):
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



def _merge_store_verdicts(
    reports: list[dict[str, Any]],
    store_check_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Merge repeated store-level evaluations by majority verdict,
    while preserving all unique issues discovered across batches.
    """
    order = {
        "na": 0,
        "pass": 1,
        "partial": 2,
        "fail": 3,
    }

    merged: dict[str, dict[str, Any]] = {}

    for cid in store_check_ids:
        candidates = []

        for report in reports:
            entry = (report.get("store_verdicts") or {}).get(cid)

            if isinstance(entry, dict) and entry.get("verdict") in order:
                candidates.append(entry)

        if not candidates:
            merged[cid] = {
                "verdict": "fail",
                "evidence": "not returned by model",
                "enrichment": "",
                "why_it_matters_for_agents": "",
                "example": "",
                "issues": [],
            }
            continue

        # -----------------------------
        # 1. Determine final verdict
        # -----------------------------
        counts: dict[str, int] = {}

        for entry in candidates:
            verdict = entry["verdict"]
            counts[verdict] = counts.get(verdict, 0) + 1

        winning_verdict = max(
            counts,
            key=lambda v: (counts[v], order[v]),
        )

        winning_entry = next(
            entry
            for entry in candidates
            if entry.get("verdict") == winning_verdict
        )

        # -----------------------------
        # 2. Collect ALL unique issues
        # -----------------------------
        merged_issues_by_type: dict[str, dict[str, Any]] = {}

        for entry in candidates:
            for issue in entry.get("issues") or []:
                issue_type = issue.get("issue_type")

                if not issue_type:
                    continue

                if issue_type not in merged_issues_by_type:
                    merged_issues_by_type[issue_type] = issue

        merged_issues = list(merged_issues_by_type.values())

        # -----------------------------
        # 3. Preserve winning evidence
        # -----------------------------
        merged[cid] = {
            **winning_entry,
            "issues": merged_issues,
        }

    return merged
def merge_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge raw batch verdicts and consistency observations."""
    store_check_ids = llm_store_check_ids()

    by_id: dict[str, dict[str, Any]] = {}

    for report in reports:
        for product in report.get("products") or []:
            pid = product.get("product_id")
            if pid:
                by_id[str(pid)] = product

    # Merge consistency observations from every product batch.
    merged_consistency = {
        "fields_observed": {},
        "option_names": [],
        "product_types": [],
        "format_variations": [],
        "measurement_observations": [],
        "issues": [],
    }

    for report in reports:
        observations = report.get("consistency_observations") or {}

        # Merge observed field values.
        fields_observed = observations.get("fields_observed") or {}
        for field, values in fields_observed.items():
            if field not in merged_consistency["fields_observed"]:
                merged_consistency["fields_observed"][field] = []

            for value in values or []:
                if value not in merged_consistency["fields_observed"][field]:
                    merged_consistency["fields_observed"][field].append(value)

        # Merge option names.
        for value in observations.get("option_names") or []:
            if value not in merged_consistency["option_names"]:
                merged_consistency["option_names"].append(value)

         # Merge product types.
        for value in observations.get("product_types") or []:
            if value not in merged_consistency["product_types"]:
                merged_consistency["product_types"].append(value)

        # Merge format variations.
        for variation in observations.get("format_variations") or []:
            if variation not in merged_consistency["format_variations"]:
                merged_consistency["format_variations"].append(variation)

        # Merge structured measurement observations.
        for observation in observations.get("measurement_observations") or []:
            if not isinstance(observation, dict):
                continue

            if observation not in merged_consistency["measurement_observations"]:
                merged_consistency["measurement_observations"].append(
                    observation
                )

        # Merge consistency issues across batches.
        consistency_issue_map: dict[tuple[str, str], dict[str, Any]] = {}

        for existing_issue in merged_consistency["issues"]:
            key = (
                str(existing_issue.get("issue_type", "")),
                str(existing_issue.get("field", "")),
            )
            consistency_issue_map[key] = existing_issue

        for issue in observations.get("issues") or []:
            issue_type = str(issue.get("issue_type", "")).strip()
            field = str(issue.get("field", "")).strip()

            key = (issue_type, field)

            if key not in consistency_issue_map:
                consistency_issue_map[key] = {
                    "issue_type": issue_type,
                    "status": issue.get("status", "existing"),
                    "field": field,
                    "description": issue.get("description", ""),
                    "affected_product_ids": [],
                }

            merged_issue = consistency_issue_map[key]

            if (
                not merged_issue.get("description")
                and issue.get("description")
            ):
                merged_issue["description"] = issue["description"]

            if (
                merged_issue.get("status") != "existing"
                and issue.get("status") == "existing"
            ):
                merged_issue["status"] = "existing"

            existing_ids = set(
                str(pid)
                for pid in merged_issue.get("affected_product_ids", []) or []
                if pid
            )

            for pid in issue.get("affected_product_ids", []) or []:
                if pid:
                    existing_ids.add(str(pid))

            merged_issue["affected_product_ids"] = sorted(existing_ids)

        merged_consistency["issues"] = list(
            consistency_issue_map.values()
        )

    return {
        "store_verdicts": _merge_store_verdicts(reports, store_check_ids),
        "products": list(by_id.values()),
        "consistency_observations": merged_consistency,
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