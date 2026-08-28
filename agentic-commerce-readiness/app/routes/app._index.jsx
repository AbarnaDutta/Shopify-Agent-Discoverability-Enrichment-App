// app/routes/app._index.jsx
import { useEffect, useRef, useState } from "react";
import { useFetcher } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import { authenticate } from "../shopify.server";

const BACKEND_URL = "https://geo.properoapps.in/api";

const LABELS = {
  execEyebrow: "Executive Summary",
  obsHigh: (n) => `There are ${n} high-priority gaps across the catalog, concentrated in the kinds of fields agents need to recommend products confidently.`,
  obsDefault: "This report summarizes the current catalog readiness and the most useful fixes to make products easier for AI agents to discover and recommend.",
  cardCatalog: "Catalog size", cardCatalogDesc: "Number of products analyzed.",
  cardGaps: "High-priority gaps", cardGapsDesc: "Issues most likely to block accurate agent recommendations.",
  cardActions: "Store actions", cardActionsDesc: "Catalog-wide improvements that benefit every product.",
  topStore: "Top store-level actions", topProducts: "Products needing the most attention",
  noStoreRecs: "No store-level recommendations returned.", noProducts: "No products returned.",
  gapsLabel: (n) => `${n} high-priority gaps`,
  sectionStore: "Priority Fixes", sectionProducts: "Detailed Product Level Exceptions",
  noRecs: "No structural adjustments needed.", noProductRecs: "No item level errors flagged.",
  productId: "ID:", exampleLabel: "Example:", agentSummaryLabel: "Agent Parsing Context Summary:",
  schemaUpdates: "recommendations", poweredBy: "Powered by Propero",
  verified: "Verified schema data parameters matching standard parser rules.",
  errorTitle: "We couldn't generate your report",
  scoreOverall: "Overall Readiness", scoreUcp: "UCP Commerce Flows", scoreMcp: "MCP Knowledge",
  scoreCatalog: "Catalog Enrichment", scoreSafety: "Safety & Policies",
  ctaHeading: "Want us to make your store agentic-commerce ready?",
  ctaBody: "Our team can implement these fixes for you — from schema and variant cleanup to UCP/MCP-ready storefront data.",
  ctaButton: "Book a Free Consultation",
  agentDiscoveryHeading: "Agent Discovery Files",
  bandReady: "Agent Ready", bandNeedsWork: "Needs Work", bandNotReady: "Not Ready",
  pillHigh: "High Priority", pillMedium: "Medium Priority", pillLow: "Low Priority",
};

const AGENT_DISCOVERY_LABELS = {
  agents_md: "agents.md (canonical agent guide)",
  llms_txt: "llms.txt",
  llms_full_txt: "llms-full.txt",
  ucp_manifest: "/.well-known/ucp (UCP manifest)",
};
const AGENT_DISCOVERY_STATUS = {
  served_custom:  { icon: "✓", cls: "text-[#16a34a]", text: "Served and customized" },
  served_default: { icon: "⚠", cls: "text-[#d97706]", text: "Served — still Shopify's default template" },
  redirects:      { icon: "→", cls: "text-[#d97706]", text: "Redirects to agents.md (expected)" },
  missing:        { icon: "✕", cls: "text-[#dc2626]", text: "Not reachable" },
  unreachable:    { icon: "✕", cls: "text-[#dc2626]", text: "Could not connect" },
};
const AGENT_DISCOVERY_CUSTOMIZATION = {
  default_skeleton: "Shopify default skeleton — mostly boilerplate",
  lightly_customized: "Lightly customized — boilerplate plus some custom content",
  heavily_customized: "Heavily customized — brand/product-specific content",
  empty: "Empty or too thin to classify",
  unknown: "",
};

const ERROR_HINTS = {
  invalid_store_url: "Double-check the URL and make sure it includes the full domain.",
  non_shopify_store: "Confirm the store is built on Shopify and publicly accessible.",
  store_unreachable: "Check that the store is live and publicly accessible, then try again.",
  llm_quota_exceeded: "This is a temporary provider limit. Please wait a few hours and resubmit.",
  llm_rate_limited: "Please wait a few minutes before resubmitting.",
  llm_response_error: "This is usually temporary. Please try again — if it keeps happening, contact support.",
  llm_auth_error: "This is a configuration issue on our end. Please try again later.",
  empty_store: "Check that your products are published and not password-protected.",
  internal_error: "Please try again later or contact us at propero.in",
};

// ── Server ────────────────────────────────────────────────────────────

export const loader = async ({ request }) => {
  const { session } = await authenticate.admin(request);
  if (!session?.shop) {
    throw new Response("Shopify session is missing.", { status: 500 });
  }
  return { shopDomain: session.shop, backendUrl: BACKEND_URL };
};

export const action = async ({ request }) => {
  const { session } = await authenticate.admin(request);
  const shopDomain = session?.shop;
  const accessToken = session?.accessToken;

  if (!shopDomain || !accessToken) {
    return { ok: false, error: "Shopify session is missing." };
  }

  let response;
  try {
    response = await fetch(`${BACKEND_URL}/shopify-app/report-requests`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: "shopify-app@propero.in",
        shop_domain: shopDomain,
        access_token: accessToken,
        language: "English",
      }),
    });
  } catch (err) {
    return { ok: false, error: `Could not reach backend: ${err.message}` };
  }

  const text = await response.text();
  if (!response.ok) {
    return { ok: false, error: `Backend error ${response.status}: ${text}` };
  }

  try {
    return { ok: true, job: JSON.parse(text) };
  } catch {
    return { ok: false, error: "Backend returned an invalid response." };
  }
};

export const headers = (headersArgs) => boundary.headers(headersArgs);

function capitalize(str) {
  if (!str) return "";
  return String(str).charAt(0).toUpperCase() + String(str).slice(1);
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

function priorityDotClass(priority) {
  if (priority === "high") return "bg-[#dc2626]";
  if (priority === "low") return "bg-[#16a34a]";
  return "bg-[#d97706]";
}

function priorityPillClass(priority) {
  if (priority === "high") return "bg-[#fee2e2] text-[#991b1b]";
  if (priority === "low") return "bg-[#d1fae5] text-[#065f46]";
  return "bg-[#fef3c7] text-[#92400e]";
}


function SectionHeader({ children }) {
  return (
    <div className="mb-3.5 flex items-baseline gap-2.5 pl-0.5 text-xs font-extrabold uppercase tracking-[0.08em] text-[var(--acr-black)]">
      <span className="inline-block h-[15px] w-[3px] shrink-0 rounded-sm bg-[var(--acr-amber)]" />
      {children}
    </div>
  );
}

function RecommendationList({ recs }) {
  if (!recs || !recs.length) {
    return <p className="text-[13px] italic text-gray-400">{LABELS.noRecs}</p>;
  }
  return recs.map((r, i) => (
    <div
      key={i}
      className="mb-2.5 rounded-xl border border-[var(--acr-border)] bg-white px-[18px] py-4 shadow-[0_10px_24px_rgba(0,0,0,0.03)] last:mb-0"
    >
      <div className="mb-1.5 flex items-start justify-between gap-2.5">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${priorityDotClass(r.priority)}`} />
          <span className="text-sm font-bold text-[var(--acr-black)]">{r.enrichment}</span>
        </div>
        <span className={`shrink-0 whitespace-nowrap rounded-full px-2.5 py-1 text-[10.5px] font-bold ${priorityPillClass(r.priority)}`}>
          {capitalize(r.priority)}
        </span>
      </div>
      <div className="mb-2.5 ml-[17px] text-[13px] leading-relaxed text-gray-600">
        {r.why_it_matters_for_agents}
      </div>
      <div className="ml-[17px] rounded-r-md border-l-[3px] border-[#cbd5e1] bg-[var(--acr-panel)] px-3.5 py-2 font-mono text-xs text-gray-600">
        <strong>{LABELS.exampleLabel}</strong> {r.example}
      </div>
    </div>
  ));
}

function ReadinessScores({ report }) {
  const s = report.readiness_scores || {};
  const overall = Number.isFinite(s.overall) ? Math.max(0, Math.min(100, Math.round(s.overall))) : 0;
  const band = scoreBand(overall);
  const donutColor = band === "strong" ? "#16a34a" : band === "fair" ? "#d97706" : "#dc2626";

  const barItems = [
    [LABELS.scoreUcp, s.ucp_commerce_flows],
    [LABELS.scoreMcp, s.mcp_knowledge],
    [LABELS.scoreCatalog, s.catalog_enrichment],
    [LABELS.scoreSafety, s.safety_policies],
  ];

  return (
    <div className="grid grid-cols-1 items-center justify-items-center gap-7 border-b border-[#f0ece3] px-6 py-7 md:grid-cols-[150px_1fr] md:justify-items-stretch md:px-10">
      <div className="flex flex-col items-center gap-2">
        <div
          className="relative flex h-[130px] w-[130px] items-center justify-center rounded-full"
          style={{ background: `conic-gradient(${donutColor} ${overall * 3.6}deg, #eee9e0 0deg)` }}
        >
          <div className="absolute inset-3.5 rounded-full bg-white" />
          <div className="relative z-10 text-center">
            <div className={`text-2xl font-extrabold leading-none ${bandTextClass(band)}`}>{overall}%</div>
            <div className="mt-1 text-[11px] font-bold text-gray-400">{bandLabel(overall)}</div>
          </div>
        </div>
        <div className="text-[12.5px] font-semibold text-gray-600">{LABELS.scoreOverall}</div>
      </div>

      <div className="flex w-full flex-col gap-3.5">
        {barItems.map(([label, raw]) => {
          const value = Number.isFinite(raw) ? Math.max(0, Math.min(100, Math.round(raw))) : 0;
          const b = scoreBand(value);
          return (
            <div key={label}>
              <div className="mb-1.5 flex items-baseline justify-between">
                <span className="text-[12.5px] font-bold text-[var(--acr-black)]">{label}</span>
                <span className="text-xs font-bold text-gray-500">{value}/100</span>
              </div>
              <div className="h-[7px] overflow-hidden rounded-full bg-[#eee9e0]">
                <div className={`h-full rounded-full ${bandBarClass(b)}`} style={{ width: `${value}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PriorityPills({ report, products }) {
  const storeRecs = report.store_level_recommendations || [];
  let high = 0, medium = 0, low = 0;
  const tally = (r) => {
    if (r.priority === "high") high++;
    else if (r.priority === "low") low++;
    else medium++;
  };
  storeRecs.forEach(tally);
  products.forEach((p) => (p.missing_enrichments || []).forEach(tally));

  return (
    <div className="flex flex-wrap gap-2.5 px-6 pb-6 pt-4.5 md:px-10">
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[#fee2e2] px-3.5 py-1.5 text-xs font-bold text-[#991b1b]">
        <span className="h-[7px] w-[7px] rounded-full bg-current" />{high} {LABELS.pillHigh}
      </span>
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[#fef3c7] px-3.5 py-1.5 text-xs font-bold text-[#92400e]">
        <span className="h-[7px] w-[7px] rounded-full bg-current" />{medium} {LABELS.pillMedium}
      </span>
      <span className="inline-flex items-center gap-1.5 rounded-full bg-[#d1fae5] px-3.5 py-1.5 text-xs font-bold text-[#065f46]">
        <span className="h-[7px] w-[7px] rounded-full bg-current" />{low} {LABELS.pillLow}
      </span>
    </div>
  );
}

function AgentDiscovery({ report }) {
  const ad = report.agent_discovery;
  if (!ad) return null;
  const files = ad.files || {};
  const templatesCustomized = ad.templates_customized ?? 0;
  const templatesTotal = ad.templates_total ?? 3;
  const recs = ad.recommendations || [];

  return (
    <div>
      <SectionHeader>{LABELS.agentDiscoveryHeading}</SectionHeader>
      <div className="rounded-2xl border border-[var(--acr-border)] bg-white p-6 shadow-[0_20px_40px_rgba(0,0,0,0.04)] md:p-7">
        <p className="mb-2.5 text-xs text-gray-500">{ad.summary || ""}</p>
        <p className="mb-2.5 text-xs text-gray-500">
          Template readiness: {templatesCustomized}/{templatesTotal} customized beyond Shopify's default.
        </p>
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {Object.entries(AGENT_DISCOVERY_LABELS).map(([key, label]) => {
            const info = files[key] || {};
            const s = AGENT_DISCOVERY_STATUS[info.status] || { icon: "○", cls: "text-gray-400", text: "Unknown" };
            let extra = "";
            if (info.status !== "missing" && info.status !== "unreachable") {
              const custText = AGENT_DISCOVERY_CUSTOMIZATION[info.customization] || "";
              if (custText) extra += ` · ${custText}`;
              if (info.mirrors_agents_md) extra += " · mirrors agents.md (no dedicated template)";
            }
            return (
              <div key={key} className="flex items-start gap-2.5 rounded-[10px] border border-[#f0ece3] bg-[var(--acr-panel)] p-3">
                <span className={`w-[18px] shrink-0 text-center text-[13px] font-extrabold ${s.cls}`}>{s.icon}</span>
                <div>
                  <div className="text-xs font-bold text-[var(--acr-black)]">{label}</div>
                  <div className="mt-0.5 text-[11px] text-gray-500">{s.text}{extra}</div>
                </div>
              </div>
            );
          })}
        </div>
        {recs.length > 0 && (
          <>
            <h3 className="mb-2.5 mt-5 text-[13px] font-bold text-[var(--acr-black)]">Shopify-Aligned Recommendations</h3>
            <RecommendationList recs={recs} />
          </>
        )}
      </div>
    </div>
  );
}

function ExecutiveSummary({ report, products }) {
  const storeRecs = report.store_level_recommendations || [];
  const highCount = products.reduce(
    (n, p) => n + (p.missing_enrichments || []).filter((r) => r.priority === "high").length,
    0
  );
  const observation = highCount ? LABELS.obsHigh(highCount) : LABELS.obsDefault;

  const cards = [
    [LABELS.cardCatalog, String(products.length), LABELS.cardCatalogDesc],
    [LABELS.cardGaps, String(highCount), LABELS.cardGapsDesc],
    [LABELS.cardActions, String(storeRecs.length), LABELS.cardActionsDesc],
  ];

  const attentionProducts = [...products]
    .sort(
      (a, b) =>
        (b.missing_enrichments || []).filter((r) => r.priority === "high").length -
        (a.missing_enrichments || []).filter((r) => r.priority === "high").length
    )
    .slice(0, 3);

  return (
    <div>
      <SectionHeader>{LABELS.execEyebrow}</SectionHeader>
      <div className="rounded-2xl border border-[var(--acr-border)] bg-white p-6 shadow-[0_20px_40px_rgba(0,0,0,0.04)] md:p-7">
        <div className="mb-5 rounded-[10px] border border-[#f0ece3] bg-[var(--acr-panel)] px-4 py-3.5 text-[13px] leading-relaxed text-gray-600">
          {observation}
        </div>
        <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-3">
          {cards.map(([label, value, desc]) => (
            <div key={label} className="rounded-[10px] border border-[#f0ece3] bg-[var(--acr-panel)] p-3.5">
              <div className="mb-1.5 text-[9px] font-bold uppercase tracking-[0.08em] text-gray-400">{label}</div>
              <strong className="mb-1 block text-2xl font-extrabold text-[var(--acr-black)]">{value}</strong>
              <p className="text-xs leading-snug text-gray-500">{desc}</p>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div className="rounded-[10px] border border-[#f0ece3] bg-[var(--acr-panel)] p-3.5 md:p-4">
            <h3 className="mb-2.5 text-[13px] font-bold text-[var(--acr-black)]">{LABELS.topStore}</h3>
            <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
              {storeRecs.length ? (
                storeRecs.slice(0, 3).map((r, i) => (
                  <li key={i}>
                    <strong className="mb-0.5 block text-[13px] text-[var(--acr-black)]">{r.enrichment}</strong>
                    <span className="block text-xs leading-snug text-gray-500">{r.why_it_matters_for_agents}</span>
                  </li>
                ))
              ) : (
                <li><span className="block text-xs leading-snug text-gray-500">{LABELS.noStoreRecs}</span></li>
              )}
            </ul>
          </div>
          <div className="rounded-[10px] border border-[#f0ece3] bg-[var(--acr-panel)] p-3.5 md:p-4">
            <h3 className="mb-2.5 text-[13px] font-bold text-[var(--acr-black)]">{LABELS.topProducts}</h3>
            <ul className="m-0 flex list-none flex-col gap-2.5 p-0">
              {attentionProducts.length ? (
                attentionProducts.map((p, i) => {
                  const h = (p.missing_enrichments || []).filter((r) => r.priority === "high").length;
                  return (
                    <li key={i}>
                      <strong className="mb-0.5 block text-[13px] text-[var(--acr-black)]">{p.title || "Untitled product"}</strong>
                      <span className="block text-xs leading-snug text-gray-500">{LABELS.gapsLabel(h)}</span>
                    </li>
                  );
                })
              ) : (
                <li><span className="block text-xs leading-snug text-gray-500">{LABELS.noProducts}</span></li>
              )}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

function ProductAccordion({ products }) {
  const [openIndex, setOpenIndex] = useState(null);
  const totalRecs = products.reduce((n, p) => n + (p.missing_enrichments || []).length, 0);

  return (
    <div>
      <SectionHeader>
        {LABELS.sectionProducts}{" "}
        <span className="font-semibold normal-case tracking-normal text-gray-400">
          · {totalRecs} {LABELS.schemaUpdates}
        </span>
      </SectionHeader>
      {products.length ? (
        products.map((p, i) => {
          const recs = p.missing_enrichments || [];
          const isOpen = openIndex === i;
          return (
            <div
              key={i}
              className="mb-3 overflow-hidden rounded-xl border border-[var(--acr-border)] bg-white shadow-[0_10px_24px_rgba(0,0,0,0.03)] last:mb-0"
            >
              <div
                className="flex cursor-pointer items-center justify-between gap-3 px-[18px] py-4"
                onClick={() => setOpenIndex(isOpen ? null : i)}
              >
                <div className="flex min-w-0 items-start gap-2.5">
                  <div>
                    <span className="text-sm font-bold text-[var(--acr-black)]">{p.title || "Untitled product"}</span>
                    <div className="mt-0.5 text-xs text-gray-400">
                      {LABELS.productId} {p.product_id} · {recs.length} {LABELS.schemaUpdates}
                    </div>
                  </div>
                </div>
                <span className={`shrink-0 text-xs text-gray-400 transition-transform duration-200 ${isOpen ? "rotate-180" : ""}`}>
                  ▼
                </span>
              </div>
              {isOpen && (
                <div className="border-t border-[#f0ece3] bg-[#fdfcfa] px-[18px] pb-5 pt-1">
                  {p.agent_summary && (
                    <div className="my-3.5 rounded-lg border border-[var(--acr-border)] bg-[#f3f1ec] px-4 py-3.5 text-[13px] leading-relaxed text-gray-800">
                      <strong>{LABELS.agentSummaryLabel}</strong>
                      <br />
                      {p.agent_summary}
                    </div>
                  )}
                  <RecommendationList recs={recs} />
                </div>
              )}
            </div>
          );
        })
      ) : (
        <p className="text-[13px] italic text-gray-400">{LABELS.noProductRecs}</p>
      )}
    </div>
  );
}

function ErrorCard({ message, errorType, onRetry }) {
  const hint = ERROR_HINTS[errorType] || ERROR_HINTS.internal_error;
  return (
    <div className="rounded-2xl border border-[#fecaca] bg-[#fff5f5] p-10 text-center">
      <div className="mb-4 text-4xl">⚠️</div>
      <h3 className="mb-3 text-lg font-extrabold text-[#991b1b]">{LABELS.errorTitle}</h3>
      <p className="mx-auto mb-5 max-w-[520px] text-sm leading-relaxed text-[#7f1d1d]">{message}</p>
      <div className="mx-auto mb-5 max-w-[480px] rounded-[10px] border border-gray-200 bg-white px-4 py-3 text-[13px] text-gray-500">
        {hint}
      </div>
      <button
        className="cursor-pointer rounded-full border-none bg-[var(--acr-black)] px-6 py-3 text-sm font-bold text-white hover:bg-[#222222]"
        onClick={onRetry}
      >
        Try again →
      </button>
    </div>
  );
}

function StepRow({ num, label, sub, state, isLast }) {
  const dotStateClasses =
    state === "done"
      ? "bg-[#d1fae5] text-[#065f46] border-[#6ee7b7]"
      : state === "active"
      ? "bg-[#fef3c7] text-[#92400e] border-[#fcd34d]"
      : "bg-gray-100 text-gray-400 border-gray-200";
  const connectorColor =
    state === "done" ? "bg-[#d1fae5]" : state === "active" ? "bg-[#fef3c7]" : "bg-gray-200";

  return (
    <div className="relative flex items-start gap-3.5 py-3.5">
      {!isLast && <span className={`absolute bottom-[-2px] left-[15px] top-10 w-0.5 ${connectorColor}`} />}
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
        <div className={`text-sm font-bold leading-snug ${state === "pending" ? "font-medium text-gray-400" : "text-[var(--acr-black)]"}`}>
          {label}
        </div>
        <div className="mt-0.5 text-xs leading-snug text-gray-500">{sub}</div>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────

const INITIAL_STEPS = { submit: "pending", fetch: "pending", ai: "pending", report: "pending" };

export default function Index({ loaderData }) {
  const { shopDomain, backendUrl } = loaderData;
  const fetcher = useFetcher();

  const [isRunning, setIsRunning] = useState(false);
  const [showSteps, setShowSteps] = useState(false);
  const [steps, setSteps] = useState(INITIAL_STEPS);
  const [aiSub, setAiSub] = useState(
    "This takes 30–120 seconds depending on catalog size — please don't close this tab"
  );
  const [status, setStatus] = useState(null); 
  const [report, setReport] = useState(null);
  const [storeUrl, setStoreUrl] = useState("");
  const [errorInfo, setErrorInfo] = useState(null);

  const pollTimerRef = useRef(null);
  const elapsedTimerRef = useRef(null);
  const pollCountRef = useRef(0);

  function resetSteps() {
    setSteps(INITIAL_STEPS);
    setAiSub("This takes 30–120 seconds depending on catalog size — please don't close this tab");
    pollCountRef.current = 0;
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
  }

  async function pollJob(jobId) {
    pollCountRef.current += 1;
    const count = pollCountRef.current;
    try {
      const res = await fetch(`${backendUrl}/report-requests/${jobId}`);
      if (!res.ok) throw new Error("Could not fetch job status.");
      const data = await res.json();

      if (data.status === "completed") {
        clearInterval(pollTimerRef.current);
        if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
        setSteps({ submit: "done", fetch: "done", ai: "done", report: "done" });
        setStatus({ type: "success", text: "Report ready! A PDF copy has also been sent to your email." });
        setIsRunning(false);
        setReport(data.report);
        setStoreUrl(data.store_url || "");
      } else if (data.status === "failed") {
        clearInterval(pollTimerRef.current);
        if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
        resetSteps();
        setShowSteps(false);
        setStatus(null);
        setIsRunning(false);
        setErrorInfo({
          message: data.error || "Something went wrong. Please try again.",
          errorType: data.error_type || "internal_error",
        });
      } else if (count <= 2) {
        setSteps((s) => ({ ...s, submit: "done", fetch: "active" }));
      } else if (count <= 4) {
        setSteps((s) => ({ ...s, submit: "done", fetch: "done", ai: "active" }));
        if (!elapsedTimerRef.current) {
          let elapsed = 0;
          elapsedTimerRef.current = setInterval(() => {
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
        setSteps((s) => ({ ...s, submit: "done", fetch: "done", ai: "active", report: "pending" }));
      }
    } catch (err) {
      console.warn(err);
    }
  }

  function handleRunAudit() {
    if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    setReport(null);
    setErrorInfo(null);
    setStatus(null);
    setIsRunning(true);
    resetSteps();
    setShowSteps(true);
    setSteps((s) => ({ ...s, submit: "active" }));
    fetcher.submit(null, { method: "post" });
  }

  useEffect(() => {
    if (!fetcher.data) return;
    if (!fetcher.data.ok) {
      setIsRunning(false);
      resetSteps();
      setShowSteps(false);
      setErrorInfo({ message: fetcher.data.error || "Submission failed.", errorType: "internal_error" });
      return;
    }
    const jobId = fetcher.data.job.job_id;
    setSteps((s) => ({ ...s, submit: "done", fetch: "active" }));
    pollTimerRef.current = setInterval(() => pollJob(jobId), 5500);
    pollJob(jobId);
  }, [fetcher.data]);

  useEffect(() => {
    return () => {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    };
  }, []);

  const products = report?.products || [];
  const storeRecs = report?.store_level_recommendations || [];
  const cleanDomain = storeUrl.replace(/https?:\/\/(www\.)?/, "").split("/")[0];
  const now = new Date().toLocaleDateString(undefined, { year: "numeric", month: "2-digit", day: "2-digit" });

  return (
    <div className="rounded-xl bg-[var(--acr-cream)] pb-24 pt-6 text-[var(--acr-black)]">
      <div className="mx-auto max-w-[720px] px-6 pb-5 pt-10 text-center">
        <h1 className="mb-4 text-[clamp(1.8rem,4vw,2.6rem)] font-extrabold leading-[1.15] tracking-[-0.02em] text-[var(--acr-black)]">
          Is your store ready for
          <br />
          <span className="text-[var(--acr-amber)]">Agentic Commerce?</span>
        </h1>
        <p className="mx-auto mb-7 max-w-[560px] text-sm leading-relaxed text-gray-500">
          Instantly scan your Shopify store against the core criteria used by AI shopping engines like ChatGPT,
          Google, and Copilot. Discover what's blocking AI discovery and optimize your catalog for the next
          generation of commerce.
        </p>

        <div className="mx-auto max-w-[560px] rounded-3xl border border-[var(--acr-border)] bg-white p-5 shadow-[0_25px_50px_rgba(0,0,0,0.05),0_2px_10px_rgba(0,0,0,0.03)] md:p-6">
          <div className="flex flex-col items-stretch gap-3.5 md:flex-row md:items-center md:justify-between">
            <div className="text-left">
              <div className="text-[9px] font-bold uppercase tracking-[0.05em] text-gray-400">Shopify Store</div>
              <div className="mt-0.5 text-[15px] font-bold text-[var(--acr-black)]">{shopDomain}</div>
            </div>
            <button
              className="w-full cursor-pointer whitespace-nowrap rounded-full border-none bg-[var(--acr-black)] px-6 py-3.5 text-sm font-bold text-[var(--acr-amber-light)] transition-colors hover:bg-[#222222] disabled:cursor-not-allowed disabled:opacity-60 md:w-auto"
              onClick={handleRunAudit}
              disabled={isRunning}
            >
              {isRunning ? "Running…" : "Run Audit →"}
            </button>
          </div>
        </div>

        <div className="mt-4 flex justify-center gap-5 text-xs text-gray-400">
          <div className="flex items-center gap-1"><span>⚡</span> ~1–3 minutes</div>
          <div className="flex items-center gap-1"><span>📄</span> PDF sent to your email</div>
        </div>

        {showSteps && (
          <div className="mx-auto mt-6 flex max-w-[560px] flex-col">
            <StepRow num="1" state={steps.submit} label="Submitting your store" sub="Validating URL and queuing your request" />
            <StepRow num="2" state={steps.fetch} label="Fetching product catalog" sub="Reading your Shopify store's public product data" />
            <StepRow num="3" state={steps.ai} label="Running AI analysis" sub={aiSub} />
            <StepRow num="4" state={steps.report} label="Generating your report" sub="Building recommendations and sending your PDF" isLast />
          </div>
        )}

        {status && (
          <div
            className={`mx-auto mt-4 flex max-w-[560px] items-center justify-center gap-2.5 rounded-full px-4.5 py-2.5 text-[13px] font-semibold ${
              status.type === "success" ? "bg-[#d1fae5] text-[#065f46]" : "bg-[#fee2e2] text-[#991b1b]"
            }`}
          >
            <span>{status.type === "success" ? "✅" : "❌"}</span>
            <span>{status.text}</span>
          </div>
        )}
      </div>

      {errorInfo && (
        <div className="mx-auto mt-10 max-w-[780px] px-4">
          <ErrorCard message={errorInfo.message} errorType={errorInfo.errorType} onRetry={() => setErrorInfo(null)} />
        </div>
      )}

      {report && (
        <div className="mx-auto mt-10 max-w-[780px] px-4">
          <div className="flex flex-col gap-6">
            <div className="overflow-hidden rounded-[18px] border border-[var(--acr-border)] bg-white shadow-[0_30px_60px_rgba(0,0,0,0.05)]">
              <div className="flex items-start justify-between gap-2.5 bg-[var(--acr-black)] px-8 py-[22px] text-white">
                <div>
                  <div className="text-[19px] font-extrabold tracking-[-0.01em]">{cleanDomain}</div>
                  <div className="mt-1 text-xs text-[#f2b657]">{storeUrl}</div>
                </div>
                <div className="whitespace-nowrap text-xs text-gray-400">{now}</div>
              </div>
              <ReadinessScores report={report} />
              <PriorityPills report={report} products={products} />
            </div>

            <AgentDiscovery report={report} />
            <ExecutiveSummary report={report} products={products} />

            <div>
              <SectionHeader>
                {LABELS.sectionStore}{" "}
                <span className="font-semibold normal-case tracking-normal text-gray-400">· {storeRecs.length}</span>
              </SectionHeader>
              <RecommendationList recs={storeRecs} />
            </div>

            <ProductAccordion products={products} />

            <div className="px-1 pt-5.5 text-center text-xs text-gray-400">
              <div className="mb-2">{LABELS.verified}</div>
              <div>
                <span className="font-bold text-[#22594f]">{LABELS.poweredBy}</span> ·{" "}
                <a className="font-semibold text-[#17695b] no-underline" href="https://www.propero.in" target="_blank" rel="noopener noreferrer">
                  propero.in
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}