// app/routes/app._index.jsx
import { Fragment, useEffect, useRef, useState } from "react";
import { useFetcher, useNavigate } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { authenticate } from "../shopify.server";

const BACKEND_URL = "https://geo.properoapps.in/api";

const LABELS = {
  scoreOverall: "Overall Readiness",
  scoreUcp: "UCP Commerce Flows",
  scoreMcp: "MCP Knowledge",
  scoreCatalog: "Catalog Enrichment",
  scoreSafety: "Safety & Policies",

  bandReady: "Agent Ready",
  bandNeedsWork: "Needs Work",
  bandNotReady: "Not Ready",

  pillHigh: "High Priority",
  pillMedium: "Medium",
  pillLow: "Low",

  errorTitle: "We couldn't generate your report",
};

const ERROR_HINTS = {
  invalid_store_url:
    "Double-check the URL and make sure it includes the full domain.",
  non_shopify_store:
    "Confirm the store is built on Shopify and publicly accessible.",
  store_unreachable:
    "Check that the store is live and publicly accessible, then try again.",
  llm_quota_exceeded:
    "This is a temporary provider limit. Please wait a few hours and resubmit.",
  llm_rate_limited:
    "Please wait a few minutes before resubmitting.",
  llm_response_error:
    "This is usually temporary. Please try again — if it keeps happening, contact support.",
  llm_auth_error:
    "This is a configuration issue on our end. Please try again later.",
  empty_store:
    "Check that your products are published and not password-protected.",
  internal_error:
    "Please try again later or contact us at propero.in",
};

// ── Server ────────────────────────────────────────────────────────────

export const loader = async ({ request }) => {
  const { session } = await authenticate.admin(request);

  if (!session?.shop) {
    throw new Response("Shopify session is missing.", {
      status: 500,
    });
  }

  return {
    shopDomain: session.shop,
    backendUrl: BACKEND_URL,
  };
};

export const action = async ({ request }) => {
  const { session } = await authenticate.admin(request);

  const shopDomain = session?.shop;
  const accessToken = session?.accessToken;

  if (!shopDomain || !accessToken) {
    return {
      ok: false,
      error: "Shopify session is missing.",
    };
  }

  let response;

  try {
    response = await fetch(
      `${BACKEND_URL}/shopify-app/report-requests`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email: "shopify-app@propero.in",
          shop_domain: shopDomain,
          access_token: accessToken,
          language: "English",
        }),
      }
    );
  } catch (err) {
    return {
      ok: false,
      error: `Could not reach backend: ${err.message}`,
    };
  }

  const responseText = await response.text();

  if (!response.ok) {
    return {
      ok: false,
      error: `Backend error ${response.status}: ${responseText}`,
    };
  }

  try {
    return {
      ok: true,
      job: JSON.parse(responseText),
    };
  } catch {
    return {
      ok: false,
      error: "Backend returned an invalid response.",
    };
  }
};

export const headers = (headersArgs) =>
  boundary.headers(headersArgs);

// ── Helpers ──────────────────────────────────────────────────────────

function normalizeAuditReport(data) {
  if (!data || typeof data !== "object") {
    return null;
  }

  const raw =
    data.readiness_scores ||
    data.dimension_scores ||
    data.audit?.readiness_scores ||
    data.audit?.dimension_scores ||
    {};

  const toScore = (value) => {
    const number = Number(value);

    return Number.isFinite(number)
      ? Math.max(0, Math.min(100, Math.round(number)))
      : null;
  };

  const ucp = toScore(raw.ucp_commerce_flows);
  const mcp = toScore(raw.mcp_knowledge);
  const catalog = toScore(raw.catalog_enrichment);
  const safety = toScore(raw.safety_policies);

  const storedOverall = toScore(
    data.overall_score ??
      data.audit?.overall_score ??
      raw.overall
  );

  const dimensionValues = [
    ucp,
    mcp,
    catalog,
    safety,
  ].filter((value) => value !== null);

  const calculatedOverall = dimensionValues.length
    ? Math.round(
        dimensionValues.reduce(
          (sum, value) => sum + value,
          0
        ) / dimensionValues.length
      )
    : 0;

  return {
    ...data,
    readiness_scores: {
      overall:
        storedOverall !== null
          ? storedOverall
          : calculatedOverall,
      ucp_commerce_flows: ucp ?? 0,
      mcp_knowledge: mcp ?? 0,
      catalog_enrichment: catalog ?? 0,
      safety_policies: safety ?? 0,
    },
  };
}

function capitalize(value) {
  if (!value) return "";

  return (
    String(value).charAt(0).toUpperCase() +
    String(value).slice(1)
  );
}

function scoreBand(value) {
  if (value >= 70) return "strong";
  if (value >= 40) return "fair";
  return "weak";
}

function bandLabel(value) {
  if (value >= 70) return LABELS.bandReady;
  if (value >= 40) return LABELS.bandNeedsWork;
  return LABELS.bandNotReady;
}

function bandTextClass(band) {
  if (band === "strong") return "text-[#16a34a]";
  if (band === "fair") return "text-[#d97706]";
  return "text-[#dc2626]";
}

function bandBarClass(band) {
  if (band === "strong") return "bg-[#16a34a]";
  if (band === "fair") return "bg-[#d97706]";
  return "bg-[#dc2626]";
}

function getScoreStatus(value) {
  if (value >= 70) return "READY";
  if (value >= 40) return "NEEDS IMPROVEMENT";
  if (value >= 30) return "NEEDS ATTENTION";
  return "CRITICAL";
}

function getScoreTone(value) {
  if (value >= 70) {
    return {
      text: "text-[#008060]",
      border: "border-[#008060]",
      bar: "bg-[#008060]",
      badge: "bg-[#E3F1ED] text-[#008060]",
    };
  }

  if (value >= 40) {
    return {
      text: "text-[#9A6700]",
      border: "border-[#FFB100]",
      bar: "bg-[#FFB100]",
      badge: "bg-[#FFF4D6] text-[#9A6700]",
    };
  }

  return {
    text: "text-[#D72C0D]",
    border: "border-[#D72C0D]",
    bar: "bg-[#D72C0D]",
    badge: "bg-[#FFF0EF] text-[#D72C0D]",
  };
}

/*
 * IMPORTANT:
 * Issue counts and Priority Issues use the same product-level
 * missing_enrichments data used by the Issues page.
 */
function getIssueRows(report, products) {
  const issueRows = [];

  (products || []).forEach((product) => {
    (product.missing_enrichments || []).forEach(
      (rec, index) => {
        issueRows.push({
          key: `product-${
            product.product_id || "unknown"
          }-${index}`,

          priority: String(
            rec.priority || "medium"
          ).toLowerCase(),

          enrichment:
            rec.enrichment ||
            "Missing enrichment",

          why_it_matters_for_agents:
            rec.why_it_matters_for_agents || "",

          example: rec.example || "",

          affectedProducts: [product],

          affectedLabel:
            product.title ||
            product.product_id ||
            "Product",
        });
      }
    );
  });

  return issueRows;
}

function getIssueCounts(report, products) {
  const issueRows = getIssueRows(
    report,
    products
  );

  return issueRows.reduce(
    (counts, issue) => {
      if (issue.priority === "high") {
        counts.high += 1;
      } else if (issue.priority === "low") {
        counts.low += 1;
      } else {
        counts.medium += 1;
      }

      return counts;
    },
    {
      high: 0,
      medium: 0,
      low: 0,
    }
  );
}

// ── Error ─────────────────────────────────────────────────────────────

function ErrorCard({
  message,
  errorType,
  onRetry,
}) {
  const hint =
    ERROR_HINTS[errorType] ||
    ERROR_HINTS.internal_error;

  return (
    <div className="rounded-2xl border border-[#fecaca] bg-[#fff5f5] p-10 text-center">
      <div className="mb-4 text-4xl">⚠️</div>

      <h3 className="mb-3 text-lg font-extrabold text-[#991b1b]">
        {LABELS.errorTitle}
      </h3>

      <p className="mx-auto mb-5 max-w-[520px] text-sm leading-relaxed text-[#7f1d1d]">
        {message}
      </p>

      <div className="mx-auto mb-5 max-w-[480px] rounded-[10px] border border-gray-200 bg-white px-4 py-3 text-[13px] text-gray-500">
        {hint}
      </div>

      <button
        type="button"
        className="cursor-pointer rounded-full border-none bg-[var(--acr-black)] px-6 py-3 text-sm font-bold text-white hover:bg-[#222222]"
        onClick={onRetry}
      >
        Try again →
      </button>
    </div>
  );
}

// ── Audit progress ────────────────────────────────────────────────────

function StepRow({
  num,
  label,
  sub,
  state,
  isLast,
}) {
  const dotStateClasses =
    state === "done"
      ? "bg-[#d1fae5] text-[#065f46] border-[#6ee7b7]"
      : state === "active"
        ? "bg-[#fef3c7] text-[#92400e] border-[#fcd34d]"
        : "bg-gray-100 text-gray-400 border-gray-200";

  const connectorColor =
    state === "done"
      ? "bg-[#d1fae5]"
      : state === "active"
        ? "bg-[#fef3c7]"
        : "bg-gray-200";

  return (
    <div className="relative flex items-start gap-3.5 py-3.5">
      {!isLast && (
        <span
          className={`absolute bottom-[-2px] left-[15px] top-10 w-0.5 ${connectorColor}`}
        />
      )}

      <div
        className={`relative z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-[13px] font-bold ${dotStateClasses}`}
      >
        {state === "done" ? (
          "✓"
        ) : state === "active" ? (
          <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
        ) : (
          num
        )}
      </div>

      <div className="pt-1">
        <div
          className={`text-sm leading-snug ${
            state === "pending"
              ? "font-medium text-gray-400"
              : "font-bold text-[var(--acr-black)]"
          }`}
        >
          {label}
        </div>

        <div className="mt-0.5 text-xs leading-snug text-gray-500">
          {sub}
        </div>
      </div>
    </div>
  );
}

// ── Score cards ───────────────────────────────────────────────────────

function OverviewScoreCard({
  label,
  value,
  description,
}) {
  const score = Math.max(
    0,
    Math.min(
      100,
      Math.round(Number(value) || 0)
    )
  );

  const tone = getScoreTone(score);

  return (
    <div
      className={`min-h-[235px] rounded-2xl border border-[#E1E3E5] border-l-4 bg-white p-5 shadow-[0_2px_8px_rgba(0,0,0,0.04)] ${tone.border}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="text-sm font-bold text-[#6D7175]">
          {label}
        </div>

        <span
          className={`rounded-md px-2.5 py-1 text-xs font-bold ${tone.badge}`}
        >
          {score} / 100
        </span>
      </div>

      <div
        className={`mt-4 text-sm font-extrabold ${tone.text}`}
      >
        {getScoreStatus(score)}
      </div>

      <p className="mt-2 min-h-[48px] text-sm leading-relaxed text-[#6D7175]">
        {description}
      </p>

      <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-[#EEF0F1]">
        <div
          className={`h-full rounded-full ${tone.bar}`}
          style={{
            width: `${score}%`,
          }}
        />
      </div>
    </div>
  );
}

// ── Overall readiness ─────────────────────────────────────────────────

function OverallReadiness({
  report,
  issueCounts,
  onViewIssues,
}) {
  const scores =
    report?.readiness_scores || {};

  const overall = Math.max(
    0,
    Math.min(
      100,
      Math.round(Number(scores.overall) || 0)
    )
  );

  const circumference =
    2 * Math.PI * 66;

  const dashOffset =
    circumference -
    (overall / 100) * circumference;

  const summary =
    overall >= 70
      ? "Your store has a strong foundation for AI-powered shopping agents and commerce flows."
      : overall >= 40
        ? "Your store has a solid starting point, with several opportunities to improve product discoverability and agent readiness."
        : "Your store has several opportunities to improve product discoverability, structured catalog information, agent instructions, and commerce flows.";

  return (
    <section className="rounded-2xl border border-[#E1E3E5] bg-white px-8 py-8 shadow-[0_2px_8px_rgba(0,0,0,0.04)]">
      <div className="grid grid-cols-1 items-center gap-8 md:grid-cols-[180px_1fr]">
        <div className="flex justify-center">
          <div className="relative h-[155px] w-[155px]">
            <svg
              className="h-full w-full -rotate-90"
              viewBox="0 0 160 160"
              aria-hidden="true"
            >
              <circle
                cx="80"
                cy="80"
                r="66"
                fill="none"
                stroke="#EEF0F1"
                strokeWidth="12"
              />

              <circle
                cx="80"
                cy="80"
                r="66"
                fill="none"
                stroke="#FFB100"
                strokeWidth="12"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={dashOffset}
              />
            </svg>

            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-4xl font-extrabold leading-none text-[#202223]">
                {overall}
              </span>

              <span className="mt-1 text-sm font-semibold text-[#6D7175]">
                / 100
              </span>
            </div>
          </div>
        </div>

        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-[#FFD38A] bg-[#FFF7E8] px-3.5 py-1.5 text-sm font-semibold text-[#9A6700]">
            <span>
              {overall < 70 ? "⚠" : "✓"}
            </span>

            {overall < 70
              ? "Catalog & Discovery Gaps Detected"
              : "Agentic Commerce Ready"}
          </span>

          <h2 className="mt-5 text-[26px] font-extrabold leading-tight tracking-tight text-[#202223]">
            Your store is {overall}% ready for agentic commerce
          </h2>

          <p className="mt-4 max-w-[760px] text-base leading-relaxed text-[#6D7175]">
            {summary}
          </p>

          <div className="mt-6 flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-6 text-sm font-semibold">
              <span className="inline-flex items-center gap-2 text-[#202223]">
                <span className="h-2.5 w-2.5 rounded-full bg-[#D72C0D]" />
                {issueCounts.high} High Priority
              </span>

              <span className="inline-flex items-center gap-2 text-[#202223]">
                <span className="h-2.5 w-2.5 rounded-full bg-[#FFB100]" />
                {issueCounts.medium} Medium
              </span>

              <span className="inline-flex items-center gap-2 text-[#202223]">
                <span className="h-2.5 w-2.5 rounded-full bg-[#6D7175]" />
                {issueCounts.low} Low
              </span>
            </div>

            <button
              type="button"
              onClick={onViewIssues}
              className="cursor-pointer border-0 bg-transparent text-sm font-bold text-[#008060] hover:underline"
            >
              View Priority Issues →
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Priority Issues ────────────────────────────────────────────────────

function SeverityBadge({ priority }) {
  const styles =
    priority === "high"
      ? "border-[#FFC9C5] bg-[#FFF0EF] text-[#D72C0D]"
      : priority === "low"
        ? "border-[#E1E3E5] bg-[#F1F2F3] text-[#6D7175]"
        : "border-[#FFE0A3] bg-[#FFF5E5] text-[#8A6116]";

  const dot =
    priority === "high"
      ? "bg-[#D72C0D]"
      : priority === "low"
        ? "bg-[#6D7175]"
        : "bg-[#FFB100]";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${styles}`}
    >
      <span
        className={`h-2 w-2 rounded-full ${dot}`}
      />

      {capitalize(priority)}
    </span>
  );
}

function PriorityIssues({
  report,
  products,
  onViewAll,
}) {
  const issueRows = getIssueRows(
    report,
    products
  );

  const highPriorityIssues =
    issueRows.filter(
      (issue) => issue.priority === "high"
    );

  const [expandedKey, setExpandedKey] =
    useState(null);

  return (
    <section className="overflow-hidden rounded-2xl border border-[#E1E3E5] bg-white shadow-[0_2px_8px_rgba(0,0,0,0.04)]">
      <div className="flex items-center justify-between gap-4 border-b border-[#E1E3E5] px-6 py-5">
        <div>
          <h2 className="text-base font-bold tracking-tight text-[#202223]">
            Priority Issues
          </h2>

          <p className="mt-1 text-sm text-[#6D7175]">
            High-priority issues from the latest audit.
          </p>
        </div>

        <button
          type="button"
          onClick={onViewAll}
          className="shrink-0 cursor-pointer border-0 bg-transparent text-sm font-semibold text-[#008060] hover:underline"
        >
          View all issues →
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] border-collapse text-left">
          <thead className="bg-[#F8F9FA]">
            <tr className="border-b border-[#E1E3E5] text-[11px] font-bold uppercase tracking-wide text-[#6D7175]">
              <th className="px-7 py-4">
                Severity
              </th>

              <th className="px-7 py-4">
                Issue
              </th>

              <th className="px-7 py-4">
                Affected
              </th>

              <th className="px-7 py-4 text-right">
                Action
              </th>
            </tr>
          </thead>

          <tbody>
            {highPriorityIssues.length > 0 ? (
              highPriorityIssues.map((issue) => {
                const isExpanded =
                  expandedKey === issue.key;

                return (
                  <Fragment key={issue.key}>
                    <tr className="border-b border-[#E1E3E5] last:border-b-0">
                      <td className="px-7 py-5 align-top">
                        <SeverityBadge
                          priority={issue.priority}
                        />
                      </td>

                      <td className="px-7 py-5 align-top">
                        <div className="text-sm font-semibold text-[#202223]">
                          {issue.enrichment}
                        </div>
                      </td>

                      <td className="px-7 py-5 align-top text-sm font-semibold text-[#202223]">
                        {issue.affectedLabel}
                      </td>

                      <td className="px-7 py-5 text-right align-top">
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedKey(
                              isExpanded
                                ? null
                                : issue.key
                            )
                          }
                          className="cursor-pointer border-0 bg-transparent px-0 text-sm font-semibold text-[#008060] hover:underline"
                        >
                          View Issue{" "}
                          {isExpanded
                            ? "⌃"
                            : "⌄"}
                        </button>
                      </td>
                    </tr>

                    {isExpanded && (
                      <tr>
                        <td
                          colSpan={4}
                          className="border-t border-[#F1F2F3] bg-[#FAFAFA] px-7 py-5"
                        >
                          {issue.why_it_matters_for_agents && (
                            <div>
                              <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                                Summary
                              </div>

                              <p className="text-sm leading-relaxed text-[#4a5568]">
                                {
                                  issue.why_it_matters_for_agents
                                }
                              </p>
                            </div>
                          )}

                          {issue.example && (
                            <div className="mt-4">
                              <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                                Example
                              </div>

                              <div className="rounded-lg border-l-2 border-[#c47d52] bg-white px-4 py-3 font-mono text-xs leading-relaxed whitespace-pre-line text-[#6D7175]">
                                {issue.example}
                              </div>
                            </div>
                          )}

                          {issue.affectedProducts.length >
                            0 && (
                            <div className="mt-4">
                              <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                                Affected products
                              </div>

                              <div className="flex flex-wrap gap-2">
                                {issue.affectedProducts.map(
                                  (product) => (
                                    <span
                                      key={
                                        product.product_id
                                      }
                                      className="rounded-full border border-[#E1E3E5] bg-white px-3 py-1.5 text-xs font-semibold text-[#202223]"
                                    >
                                      {product.title ||
                                        product.product_id}
                                    </span>
                                  )
                                )}
                              </div>
                            </div>
                          )}

                          {issue.affectedProducts.length ===
                            0 && (
                            <div className="mt-4 text-xs font-medium text-[#6D7175]">
                              This is a store-wide issue.
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })
            ) : (
              <tr>
                <td
                  colSpan={4}
                  className="px-6 py-12 text-center text-sm text-[#6D7175]"
                >
                  No high-priority issues found in the latest audit.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

// ── Store Health Summary ───────────────────────────────────────────────

function StoreHealthSummary({
  report,
  products,
}) {
  const affectedProducts =
    products.filter(
      (product) =>
        (product.missing_enrichments || [])
          .length > 0
    ).length;

  const resolved = Number(
    report?.issues_resolved ??
      report?.resolved_issues ??
      report?.health_summary?.issues_resolved ??
      0
  );

  const cards = [
    {
      label: "PRODUCTS ANALYZED",
      value:
        products.length.toLocaleString(),
      description:
        "Complete catalog scanned via Shopify Admin API",
      valueClass: "text-[#202223]",
    },
    {
      label: "PRODUCTS AFFECTED",
      value:
        affectedProducts.toLocaleString(),
      description:
        "Requires catalog enrichment or schema fixes",
      valueClass: "text-[#D72C0D]",
    },
    {
      label: "ISSUES RESOLVED",
      value: resolved.toLocaleString(),
      description:
        resolved > 0
          ? `${resolved} issues resolved since your previous audit.`
          : "No issues resolved since your previous audit.",
      valueClass: "text-[#008060]",
    },
  ];

  return (
    <section>
      <div className="mb-4 flex items-center justify-between px-0.5">
        <h2 className="text-base font-bold text-[#202223]">
          Store Health Summary
        </h2>

        <span className="text-sm text-[#6D7175]">
          Canonical Audit Baseline
        </span>
      </div>

      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {cards.map((card) => (
          <div
            key={card.label}
            className="rounded-2xl border border-[#E1E3E5] bg-white px-6 py-7 shadow-[0_2px_8px_rgba(0,0,0,0.04)]"
          >
            <div className="text-sm font-bold text-[#6D7175]">
              {card.label}
            </div>

            <div
              className={`mt-2 text-3xl font-extrabold tracking-tight ${card.valueClass}`}
            >
              {card.value}
            </div>

            <p className="mt-2 text-xs leading-relaxed text-[#6D7175]">
              {card.description}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────

const INITIAL_STEPS = {
  submit: "pending",
  fetch: "pending",
  ai: "pending",
  report: "pending",
};

export default function Index({
  loaderData,
}) {
  const {
    shopDomain,
    backendUrl,
  } = loaderData;

  const navigate = useNavigate();
  const fetcher = useFetcher();

  const [isRunning, setIsRunning] =
    useState(false);

  const [showSteps, setShowSteps] =
    useState(false);

  const [steps, setSteps] =
    useState(INITIAL_STEPS);

  const [aiSub, setAiSub] = useState(
    "This takes 30–120 seconds depending on catalog size — please don't close this tab"
  );

  const [status, setStatus] =
    useState(null);

  const [report, setReport] =
    useState(null);

  const [storeUrl, setStoreUrl] =
    useState("");

  const [errorInfo, setErrorInfo] =
    useState(null);

  const pollTimerRef =
    useRef(null);

  const elapsedTimerRef =
    useRef(null);

  const pollCountRef =
    useRef(0);

  function resetSteps() {
    setSteps(INITIAL_STEPS);

    setAiSub(
      "This takes 30–120 seconds depending on catalog size — please don't close this tab"
    );

    pollCountRef.current = 0;

    if (elapsedTimerRef.current) {
      clearInterval(
        elapsedTimerRef.current
      );

      elapsedTimerRef.current = null;
    }
  }

  async function pollJob(jobId) {
    pollCountRef.current += 1;

    const count =
      pollCountRef.current;

    try {
      const response = await fetch(
        `${backendUrl}/report-requests/${jobId}`
      );

      if (!response.ok) {
        throw new Error(
          "Could not fetch job status."
        );
      }

      const data =
        await response.json();

      if (data.status === "completed") {
        if (pollTimerRef.current) {
          clearInterval(
            pollTimerRef.current
          );

          pollTimerRef.current = null;
        }

        if (elapsedTimerRef.current) {
          clearInterval(
            elapsedTimerRef.current
          );

          elapsedTimerRef.current = null;
        }

        setSteps({
          submit: "done",
          fetch: "done",
          ai: "done",
          report: "done",
        });

        setStatus({
          type: "success",
          text: "Report ready! A PDF copy has also been sent to your email.",
        });

        setIsRunning(false);

        try {
          const latestResponse =
            await fetch(
              `${backendUrl}/audits/latest?shop_domain=${encodeURIComponent(
                shopDomain
              )}`
            );

          if (!latestResponse.ok) {
            throw new Error(
              "Could not load the completed audit from database."
            );
          }

          const latestData =
            await latestResponse.json();

          const latestReport =
            normalizeAuditReport(
              latestData
            );

          setReport(latestReport);

          setStoreUrl(
            latestData.store_url ||
              latestData.audit?.store_url ||
              `https://${shopDomain}`
          );
        } catch (error) {
          console.warn(
            "Could not load completed audit from database:",
            error
          );

          const fallbackReport =
            normalizeAuditReport(
              data.report
            );

          setReport(fallbackReport);

          setStoreUrl(
            data.store_url ||
              `https://${shopDomain}`
          );
        }

        return;
      }

      if (data.status === "failed") {
        if (pollTimerRef.current) {
          clearInterval(
            pollTimerRef.current
          );

          pollTimerRef.current = null;
        }

        if (elapsedTimerRef.current) {
          clearInterval(
            elapsedTimerRef.current
          );

          elapsedTimerRef.current = null;
        }

        resetSteps();
        setShowSteps(false);
        setStatus(null);
        setIsRunning(false);

        setErrorInfo({
          message:
            data.error ||
            "Something went wrong. Please try again.",
          errorType:
            data.error_type ||
            "internal_error",
        });

        return;
      }

      if (count <= 2) {
        setSteps((current) => ({
          ...current,
          submit: "done",
          fetch: "active",
        }));
      } else if (count <= 4) {
        setSteps((current) => ({
          ...current,
          submit: "done",
          fetch: "done",
          ai: "active",
        }));

        if (!elapsedTimerRef.current) {
          let elapsed = 0;

          elapsedTimerRef.current =
            setInterval(() => {
              elapsed += 5;

              setAiSub(
                elapsed < 30
                  ? "Analyzing products with AI… please keep this tab open"
                  : elapsed < 60
                    ? `Still working… ${elapsed}s elapsed — larger catalogs take up to 2 minutes`
                    : `Almost there… ${elapsed}s elapsed — nearly done, hang tight!`
              );
            }, 5000);
        }
      } else {
        setSteps((current) => ({
          ...current,
          submit: "done",
          fetch: "done",
          ai: "active",
          report: "pending",
        }));
      }
    } catch (error) {
      console.warn(
        "Audit polling error:",
        error
      );
    }
  }

  function handleRunAudit() {
    if (pollTimerRef.current) {
      clearInterval(
        pollTimerRef.current
      );

      pollTimerRef.current = null;
    }

    setErrorInfo(null);
    setStatus(null);
    setIsRunning(true);

    resetSteps();
    setShowSteps(true);

    setSteps((current) => ({
      ...current,
      submit: "active",
    }));

    fetcher.submit(null, {
      method: "post",
    });
  }

  useEffect(() => {
    if (!fetcher.data) return;

    if (!fetcher.data.ok) {
      setIsRunning(false);
      resetSteps();
      setShowSteps(false);

      setErrorInfo({
        message:
          fetcher.data.error ||
          "Submission failed.",
        errorType: "internal_error",
      });

      return;
    }

    const jobId =
      fetcher.data?.job?.job_id;

    if (!jobId) {
      setIsRunning(false);
      setShowSteps(false);

      setErrorInfo({
        message:
          "Backend did not return a valid audit job.",
        errorType: "internal_error",
      });

      return;
    }

    setSteps((current) => ({
      ...current,
      submit: "done",
      fetch: "active",
    }));

    if (pollTimerRef.current) {
      clearInterval(
        pollTimerRef.current
      );
    }

    pollTimerRef.current =
      setInterval(
        () => pollJob(jobId),
        5500
      );

    pollJob(jobId);
  }, [fetcher.data]);

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(
          pollTimerRef.current
        );
      }

      if (elapsedTimerRef.current) {
        clearInterval(
          elapsedTimerRef.current
        );
      }
    };
  }, []);

  useEffect(() => {
    if (!shopDomain) return;

    let cancelled = false;

    async function loadLatestAudit() {
      try {
        const response = await fetch(
          `${backendUrl}/audits/latest?shop_domain=${encodeURIComponent(
            shopDomain
          )}`
        );

        if (response.status === 404) {
          if (!cancelled) {
            setReport(null);
          }

          return;
        }

        if (!response.ok) {
          throw new Error(
            `Failed to load latest audit: ${response.status}`
          );
        }

        const data =
          await response.json();

        if (cancelled) return;

        const latestReport =
          normalizeAuditReport(data);

        setReport(latestReport);

        setStoreUrl(
          data.store_url ||
            data.audit?.store_url ||
            `https://${shopDomain}`
        );
      } catch (error) {
        if (!cancelled) {
          console.warn(
            "Could not load the latest audit from database:",
            error
          );
        }
      }
    }

    loadLatestAudit();

    return () => {
      cancelled = true;
    };
  }, [backendUrl, shopDomain]);

  const products =
    report?.products || [];

  const scores =
    report?.readiness_scores || {};

  const issueCounts =
    getIssueCounts(
      report,
      products
    );

  const cleanDomain = (
    storeUrl || `https://${shopDomain}`
  )
    .replace(
      /https?:\/\/(www\.)?/,
      ""
    )
    .split("/")[0];

  const now =
    new Date().toLocaleDateString(
      undefined,
      {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }
    );

  return (
    <div className="min-h-screen rounded-xl bg-[var(--acr-cream)] pb-24 pt-6 text-[var(--acr-black)]">

      {/* ── Audit launcher ─────────────────────────────────────── */}

      <div className="mx-auto px-0 pb-4 pt-0">
        <div className="rounded-2xl border border-[#E1E3E5] bg-white px-8 py-7 shadow-[0_2px_8px_rgba(0,0,0,0.04)]">
          <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">

            <div>
              <div className="mb-2 text-[13px] font-extrabold uppercase tracking-[0.14em] text-[#E87500]">
                AGENTIC COMMERCE READINESS
              </div>

              <h1 className="text-[28px] font-extrabold leading-tight tracking-[-0.02em] text-[#111111]">
                Shopify Store Audit
              </h1>

              <div className="mt-2 text-[17px] text-[#5F6F85]">
                https://{shopDomain}
              </div>
            </div>

            <button
              type="button"
              className="w-full shrink-0 cursor-pointer rounded-full border-none bg-[#111111] px-8 py-4 text-base font-bold text-white transition-colors hover:bg-[#222222] disabled:cursor-not-allowed disabled:opacity-60 md:w-auto"
              onClick={handleRunAudit}
              disabled={isRunning}
            >
              {isRunning
                ? "Running…"
                : "Run Audit"}
            </button>
          </div>
        </div>
      </div>

      {showSteps && (
        <div className="mx-auto max-w-[900px] px-6 pb-2">
          <div className="flex flex-col text-left">

            <StepRow
              num="1"
              state={steps.submit}
              label="Submitting your store"
              sub="Validating URL and queuing your request"
            />

            <StepRow
              num="2"
              state={steps.fetch}
              label="Fetching product catalog"
              sub="Reading your Shopify store's public product data"
            />

            <StepRow
              num="3"
              state={steps.ai}
              label="Running AI analysis"
              sub={aiSub}
            />

            <StepRow
              num="4"
              state={steps.report}
              label="Generating your report"
              sub="Building recommendations and sending your PDF"
              isLast
            />

          </div>
        </div>
      )}

      {status && (
        <div
          className={`mx-auto mt-3 flex max-w-[900px] items-center justify-center gap-2.5 rounded-full px-4.5 py-2.5 text-[13px] font-semibold ${
            status.type === "success"
              ? "bg-[#d1fae5] text-[#065f46]"
              : "bg-[#fee2e2] text-[#991b1b]"
          }`}
        >
          <span>
            {status.type === "success"
              ? "✅"
              : "❌"}
          </span>

          <span>
            {status.text}
          </span>
        </div>
      )}

      {/* ── Error ───────────────────────────────────────────────── */}

      {errorInfo && (
        <div className="mx-auto mt-6 max-w-[1100px] px-6">
          <ErrorCard
            message={errorInfo.message}
            errorType={errorInfo.errorType}
            onRetry={() =>
              setErrorInfo(null)
            }
          />
        </div>
      )}

      {/* ── Actual audit dashboard ─────────────────────────────── */}

      {report && (
        <div className="mx-auto mt-8 max-w-[1400px] px-4 md:px-6">
          <div className="space-y-8">

            <OverallReadiness
              report={report}
              issueCounts={issueCounts}
              onViewIssues={() =>
                navigate("/app/issues")
              }
            />

            <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">

              <OverviewScoreCard
                label="UCP COMMERCE FLOWS"
                value={
                  scores.ucp_commerce_flows
                }
                description="Improve agent access to commerce and checkout flows."
              />

              <OverviewScoreCard
                label="MCP KNOWLEDGE"
                value={
                  scores.mcp_knowledge
                }
                description="Make store and product knowledge easier for AI agents to understand."
              />

              <OverviewScoreCard
                label="CATALOG ENRICHMENT"
                value={
                  scores.catalog_enrichment
                }
                description="Add structured product information such as identifiers, specifications and product types."
              />

              <OverviewScoreCard
                label="SAFETY & POLICIES"
                value={
                  scores.safety_policies
                }
                description="Improve policy, delivery and agent-facing safety information."
              />

            </div>

            <PriorityIssues
              report={report}
              products={products}
              onViewAll={() =>
                navigate("/app/issues")
              }
            />

            <StoreHealthSummary
              report={report}
              products={products}
            />

            <div className="px-1 pt-2 text-center text-xs text-gray-400">
              <div>
                {cleanDomain} · {now}
              </div>
            </div>

          </div>
        </div>
      )}

      {/* ── Empty state ─────────────────────────────────────────── */}

      {!report &&
        !isRunning &&
        !errorInfo && (
          <div className="mx-auto mt-8 max-w-[900px] px-6">
            <div className="rounded-2xl border border-[#E1E3E5] bg-white px-8 py-16 text-center shadow-[0_2px_8px_rgba(0,0,0,0.04)]">

              <h2 className="text-xl font-bold text-[#202223]">
                Run your first audit
              </h2>

              <p className="mx-auto mt-2 max-w-[520px] text-sm leading-relaxed text-[#6D7175]">
                Scan your Shopify catalog to see
                your agentic commerce readiness,
                priority issues, and store health
                summary.
              </p>

            </div>
          </div>
        )}

    </div>
  );
}