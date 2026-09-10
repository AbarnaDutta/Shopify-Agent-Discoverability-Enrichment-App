//agentic-commerce-readiness/app/routes/app.products_.$id.jsx
import { useEffect, useState } from "react";
import {
  useNavigate,
  useSearchParams,
  useRouteLoaderData,
} from "react-router";
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  AlertCircle,
  Package,
} from "lucide-react";

function getProductStatus(product) {
  const issues = product?.missing_enrichments || [];

  const hasHigh = issues.some((item) => item.priority === "high");
  const hasOtherIssues = issues.some(
    (item) => item.priority === "medium" || item.priority === "low"
  );

  if (hasHigh) {
    return {
      label: "Critical",
      text: "text-red-700",
      bg: "bg-red-50",
      ring: "border-red-200",
      icon: AlertOctagon,
      blurb:
        "AI shopping agents may misrepresent or fail to recommend this product until high-priority gaps are fixed.",
    };
  }

  if (hasOtherIssues) {
    return {
      label: "Needs Attention",
      text: "text-orange-700",
      bg: "bg-orange-50",
      ring: "border-orange-200",
      icon: AlertTriangle,
      blurb:
        "This product is discoverable, but addressing the remaining gaps will improve how confidently agents can act on it.",
    };
  }

  return {
    label: "Ready",
    text: "text-[var(--app-green)]",
    bg: "bg-green-50",
    ring: "border-green-200",
    icon: CheckCircle2,
    blurb: "This product currently meets the checks included in the audit.",
  };
}

function SeverityBadge({ priority }) {
  if (priority === "high") {
    return (
      <span className="rounded-full bg-red-50 px-2.5 py-1 text-[10px] font-bold text-red-700">
        High
      </span>
    );
  }

  if (priority === "low") {
    return (
      <span className="rounded-full bg-green-50 px-2.5 py-1 text-[10px] font-bold text-[var(--app-green)]">
        Low
      </span>
    );
  }

  return (
    <span className="rounded-full bg-orange-50 px-2.5 py-1 text-[10px] font-bold text-orange-700">
      Medium
    </span>
  );
}

function IssueRow({ issue }) {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <SeverityBadge priority={issue.priority} />
          </div>

          <h3 className="text-sm font-bold text-[var(--app-text)]">
            {issue.enrichment || "Missing enrichment"}
          </h3>

          {issue.why_it_matters_for_agents && (
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--app-muted)]">
              {issue.why_it_matters_for_agents}
            </p>
          )}

          {issue.example && (
            <div className="mt-3 rounded-lg border-l-2 border-[var(--app-orange)] bg-white px-3 py-2 font-mono text-[11px] text-[var(--app-muted)]">
              {issue.example}
            </div>
          )}
        </div>

        <AlertCircle
          size={17}
          className={
            issue.priority === "high"
              ? "shrink-0 text-red-600"
              : "shrink-0 text-[var(--app-orange)]"
          }
        />
      </div>
    </div>
  );
}

export default function ProductDetails() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { shopDomain } = useRouteLoaderData("routes/app");

  const id = searchParams.get("id");

  const [report, setReport] = useState(null);

  useEffect(() => {
    if (!shopDomain || !id) return;

    let cancelled = false;

    const loadProduct = async () => {
      try {
        const response = await fetch(
          `https://geo.properoapps.in/api/products/detail?shop_domain=${encodeURIComponent(
            shopDomain
          )}&product_id=${encodeURIComponent(id)}`
        );

        if (response.status === 404) {
          if (!cancelled) setReport(null);
          return;
        }

        if (!response.ok) {
          throw new Error(`Failed to load product: ${response.status}`);
        }

        const data = await response.json();

        if (!cancelled) setReport(data.product);
      } catch (error) {
        console.error("Failed to load product:", error);
        if (!cancelled) setReport(null);
      }
    };

    loadProduct();

    return () => {
      cancelled = true;
    };
  }, [shopDomain, id]);

  const product = report;

  if (!report) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] px-5 py-10 md:px-8">
        <div className="mx-auto max-w-5xl">
          <button
            type="button"
            onClick={() => navigate("/app/products")}
            className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-[var(--app-green)]"
          >
            <ArrowLeft size={17} />
            Back to Products
          </button>

          <div className="rounded-2xl border border-[var(--app-border)] bg-white px-6 py-16 text-center">
            <Package size={30} className="mx-auto mb-4 text-[var(--app-muted)]" />

            <h1 className="text-xl font-extrabold text-[var(--app-green)]">
              No Previous Audit Data
            </h1>

            <p className="mx-auto mt-2 max-w-md text-sm text-[var(--app-muted)]">
              This product has not been included in any completed audit for this
              store.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const status = getProductStatus(product);
  const StatusIcon = status.icon;
  const issues = product.missing_enrichments || [];

  const highIssues = issues.filter((issue) => issue.priority === "high").length;
  const mediumIssues = issues.filter((issue) => issue.priority === "medium").length;
  const lowIssues = issues.filter((issue) => issue.priority === "low").length;

  return (
    <div className="min-h-screen bg-[var(--app-bg)] px-5 py-8 text-[var(--app-text)] md:px-8">
      <div className="mx-auto max-w-6xl">
        <button
          type="button"
          onClick={() => navigate("/app/products")}
          className="mb-4 inline-flex items-center gap-2 text-sm font-bold text-[var(--app-green)] transition-opacity hover:opacity-70"
        >
          <ArrowLeft size={17} />
          Back to Products
        </button>

        {/* Hero card — image + title on the left, status (real, derived)
            on the right in place of the mockup's fabricated numeric gauge */}
        <div className="mb-6 rounded-2xl border border-[var(--app-border)] bg-white p-6 md:p-8">
          <div className="flex flex-col gap-8 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-6">
              <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-2xl border border-[var(--app-border)] bg-[var(--app-bg)] sm:h-28 sm:w-28">
                <Package size={36} className="text-[var(--app-muted)]" />
              </div>

              <div className="min-w-0">
                <div className="mb-1.5 text-[10px] font-extrabold uppercase tracking-[0.1em] text-[var(--app-orange)]">
                  Product Health
                </div>
                <h1 className="text-xl font-extrabold text-[var(--app-text)] md:text-2xl">
                  {product.title || "Untitled product"}
                </h1>
                <p className="mt-2 max-w-md text-xs leading-relaxed text-[var(--app-muted)]">
                  {status.blurb}
                </p>
              </div>
            </div>

            <div
              className={`flex shrink-0 flex-col items-center justify-center gap-1.5 rounded-2xl border-2 ${status.ring} bg-[var(--app-bg)] p-5`}
              style={{ minWidth: 132 }}
            >
              <StatusIcon size={30} className={status.text} />
              <span className={`text-sm font-extrabold ${status.text}`}>{status.label}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Left column — only real fields: product ID and issue counts */}
          <div className="space-y-6 lg:col-span-1">
            <div className="rounded-2xl border border-[var(--app-border)] bg-white p-5">
              <h3 className="mb-4 border-b border-[var(--app-border)] pb-2 text-xs font-bold uppercase tracking-wider text-[var(--app-text)]">
                Product Information
              </h3>

              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between border-b border-[var(--app-bg)] py-1">
                  <span className="font-medium text-[var(--app-muted)]">Product ID:</span>
                  <span className="max-w-[60%] truncate text-right font-mono font-semibold text-[var(--app-text)]">
                    {product.product_id || "Unavailable"}
                  </span>
                </div>

                <div className="flex items-center justify-between py-1">
                  <span className="font-medium text-[var(--app-muted)]">Total issues:</span>
                  <span className="font-bold text-[var(--app-text)]">{issues.length}</span>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--app-border)] bg-white p-5">
              <h3 className="mb-4 border-b border-[var(--app-border)] pb-2 text-xs font-bold uppercase tracking-wider text-[var(--app-text)]">
                Issue Breakdown
              </h3>

              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[var(--app-muted)]">High priority</span>
                  <span className="font-extrabold text-red-700">{highIssues}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[var(--app-muted)]">Medium priority</span>
                  <span className="font-extrabold text-orange-700">{mediumIssues}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[var(--app-muted)]">Low priority</span>
                  <span className="font-extrabold text-[var(--app-green)]">{lowIssues}</span>
                </div>
              </div>
            </div>

            {product.agent_summary && (
              <div className="rounded-2xl border border-[var(--app-border)] bg-white p-5">
                <h3 className="mb-3 border-b border-[var(--app-border)] pb-2 text-xs font-bold uppercase tracking-wider text-[var(--app-text)]">
                  Agent Parsing Context
                </h3>
                <p className="rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] p-3 text-xs leading-relaxed text-[var(--app-text)]">
                  {product.agent_summary}
                </p>
              </div>
            )}
          </div>

          {/* Right column — issues list */}
          <div className="lg:col-span-2">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-bold text-[var(--app-text)]">
                Issues ({issues.length})
              </h2>
              <span className="text-xs text-[var(--app-muted)]">
                Resolve these to elevate product readiness
              </span>
            </div>

            {issues.length > 0 ? (
              <div className="flex flex-col gap-3">
                {issues.map((issue, index) => (
                  <IssueRow key={`${issue.enrichment || "issue"}-${index}`} issue={issue} />
                ))}
              </div>
            ) : (
              <div className="rounded-2xl border border-green-100 bg-green-50 p-10 text-center">
                <CheckCircle2 size={30} className="mx-auto mb-3 text-[var(--app-green)]" />
                <h3 className="text-sm font-extrabold text-[var(--app-green)]">
                  All checks passed
                </h3>
                <p className="mx-auto mt-1.5 max-w-sm text-xs text-[var(--app-muted)]">
                  This product currently meets the checks included in the audit.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}