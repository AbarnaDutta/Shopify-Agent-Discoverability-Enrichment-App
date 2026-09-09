import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Package,
  ExternalLink,
} from "lucide-react";

const STORAGE_KEY = "acr_latest_report";

function getProductScore(product) {
  if (typeof product?.readiness_score === "number") {
    return Math.max(0, Math.min(100, Math.round(product.readiness_score)));
  }

  if (typeof product?.score === "number") {
    return Math.max(0, Math.min(100, Math.round(product.score)));
  }

  const issues = product?.missing_enrichments || [];

  if (!issues.length) return 100;

  const high = issues.filter((item) => item.priority === "high").length;
  const medium = issues.filter((item) => item.priority === "medium").length;
  const low = issues.filter((item) => item.priority === "low").length;

  return Math.max(0, Math.min(100, 100 - high * 20 - medium * 10 - low * 5));
}

function getScoreStatus(score) {
  if (score >= 80) {
    return {
      label: "Ready",
      text: "text-[var(--app-green)]",
      bg: "bg-green-50",
    };
  }

  if (score >= 50) {
    return {
      label: "Needs Work",
      text: "text-orange-700",
      bg: "bg-orange-50",
    };
  }

  return {
    label: "Not Ready",
    text: "text-red-700",
    bg: "bg-red-50",
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

            {issue.category && (
              <span className="rounded-full bg-[var(--app-orange-light)] px-2.5 py-1 text-[10px] font-semibold text-[var(--app-green)]">
                {issue.category}
              </span>
            )}
          </div>

          <h3 className="text-sm font-bold text-[var(--app-text)]">
            {issue.enrichment ||
              issue.title ||
              issue.name ||
              issue.field ||
              "Missing enrichment"}
          </h3>

          {(issue.why_it_matters_for_agents || issue.description) && (
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--app-muted)]">
              {issue.why_it_matters_for_agents || issue.description}
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

function InfoItem({ label, value }) {
  return (
    <div>
      <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
        {label}
      </div>

      <div className="break-words text-sm font-semibold text-[var(--app-text)]">
        {value || "Not available"}
      </div>
    </div>
  );
}

export default function ProductDetails() {
  const navigate = useNavigate();
  const { id } = useParams();

  const [report, setReport] = useState(null);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);

      if (stored) {
        setReport(JSON.parse(stored));
      }
    } catch (error) {
      console.warn("Could not load stored audit report.", error);
    }
  }, []);

  const product = useMemo(() => {
    const products = report?.products || [];

    return products.find(
      (item) =>
        String(item.product_id || item.id) === String(decodeURIComponent(id || ""))
    );
  }, [report, id]);

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
            <Package
              size={30}
              className="mx-auto mb-4 text-[var(--app-muted)]"
            />

            <h1 className="text-xl font-extrabold text-[var(--app-green)]">
              No audit report available
            </h1>

            <p className="mx-auto mt-2 max-w-md text-sm text-[var(--app-muted)]">
              Run an audit from the Dashboard first to view product details.
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!product) {
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
            <h1 className="text-xl font-extrabold text-[var(--app-green)]">
              Product not found
            </h1>

            <p className="mt-2 text-sm text-[var(--app-muted)]">
              This product is not present in the latest audit report.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const score = getProductScore(product);
  const scoreStatus = getScoreStatus(score);
  const issues = product.missing_enrichments || [];

  const highIssues = issues.filter(
    (issue) => issue.priority === "high"
  ).length;

  const mediumIssues = issues.filter(
    (issue) => issue.priority === "medium"
  ).length;

  const lowIssues = issues.filter(
    (issue) => issue.priority === "low"
  ).length;

  const productUrl =
    product.url ||
    product.product_url ||
    product.online_store_url ||
    "";

  return (
    <div className="min-h-screen bg-[var(--app-bg)] px-5 py-8 text-[var(--app-text)] md:px-8">
      <div className="mx-auto max-w-5xl">
        {/* Back */}
        <button
          type="button"
          onClick={() => navigate("/app/products")}
          className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-[var(--app-green)] transition-opacity hover:opacity-70"
        >
          <ArrowLeft size={17} />
          Back to Products
        </button>

        {/* Product header */}
        <div className="mb-6 overflow-hidden rounded-2xl border border-[var(--app-border)] bg-white">
          <div className="flex flex-col gap-6 p-6 md:flex-row md:items-center md:p-8">
            <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-[var(--app-border)] bg-[var(--app-bg)]">
              {product.image_url || product.image ? (
                <img
                  src={product.image_url || product.image}
                  alt={product.title || ""}
                  className="h-full w-full object-cover"
                />
              ) : (
                <Package
                  size={32}
                  className="text-[var(--app-muted)]"
                />
              )}
            </div>

            <div className="min-w-0 flex-1">
              <div className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.1em] text-[var(--app-orange)]">
                Product Details
              </div>

              <h1 className="text-2xl font-extrabold tracking-tight text-[var(--app-green)] md:text-3xl">
                {product.title || "Untitled product"}
              </h1>

              <p className="mt-1.5 text-xs text-[var(--app-muted)]">
                Product ID: {product.product_id || product.id || "Unavailable"}
              </p>

              {productUrl && (
                <a
                  href={productUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-[var(--app-green)]"
                >
                  View product
                  <ExternalLink size={13} />
                </a>
              )}
            </div>

            <div className="shrink-0 rounded-2xl border border-[var(--app-border)] bg-[var(--app-bg)] p-5 text-center">
              <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
                Readiness
              </div>

              <div className={`mt-1 text-4xl font-extrabold ${scoreStatus.text}`}>
                {score}
              </div>

              <div
                className={`mt-1 inline-flex rounded-full px-3 py-1 text-[10px] font-bold ${scoreStatus.bg} ${scoreStatus.text}`}
              >
                {scoreStatus.label}
              </div>
            </div>
          </div>
        </div>

        {/* Summary */}
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-2xl border border-red-100 bg-white p-5">
            <div className="text-xs font-bold text-[var(--app-muted)]">
              High Priority
            </div>

            <div className="mt-1 text-2xl font-extrabold text-red-700">
              {highIssues}
            </div>
          </div>

          <div className="rounded-2xl border border-orange-100 bg-white p-5">
            <div className="text-xs font-bold text-[var(--app-muted)]">
              Medium Priority
            </div>

            <div className="mt-1 text-2xl font-extrabold text-orange-700">
              {mediumIssues}
            </div>
          </div>

          <div className="rounded-2xl border border-green-100 bg-white p-5">
            <div className="text-xs font-bold text-[var(--app-muted)]">
              Low Priority
            </div>

            <div className="mt-1 text-2xl font-extrabold text-[var(--app-green)]">
              {lowIssues}
            </div>
          </div>
        </div>

        {/* Product information */}
        <div className="mb-6 rounded-2xl border border-[var(--app-border)] bg-white p-6 md:p-7">
          <div className="mb-5 flex items-center gap-2">
            <span className="h-4 w-1 rounded-full bg-[var(--app-orange)]" />

            <h2 className="text-sm font-extrabold uppercase tracking-wider text-[var(--app-green)]">
              Product Information
            </h2>
          </div>

          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 md:grid-cols-3">
            <InfoItem
              label="Product ID"
              value={product.product_id || product.id}
            />

            <InfoItem
              label="SKU"
              value={product.sku}
            />

            <InfoItem
              label="GTIN"
              value={product.gtin}
            />

            <InfoItem
              label="MPN"
              value={product.mpn}
            />

            <InfoItem
              label="Vendor"
              value={product.vendor}
            />

            <InfoItem
              label="Product Type"
              value={product.product_type || product.type}
            />
          </div>
        </div>

        {/* Agent summary */}
        {product.agent_summary && (
          <div className="mb-6 rounded-2xl border border-[var(--app-border)] bg-white p-6 md:p-7">
            <div className="mb-4 flex items-center gap-2">
              <span className="h-4 w-1 rounded-full bg-[var(--app-orange)]" />

              <h2 className="text-sm font-extrabold uppercase tracking-wider text-[var(--app-green)]">
                Agent Parsing Context
              </h2>
            </div>

            <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] p-4 text-sm leading-relaxed text-[var(--app-text)]">
              {product.agent_summary}
            </div>
          </div>
        )}

        {/* Issues */}
        <div className="rounded-2xl border border-[var(--app-border)] bg-white p-6 md:p-7">
          <div className="mb-5 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <span className="h-4 w-1 rounded-full bg-[var(--app-orange)]" />

              <h2 className="text-sm font-extrabold uppercase tracking-wider text-[var(--app-green)]">
                Product Issues
              </h2>
            </div>

            <span className="text-xs font-semibold text-[var(--app-muted)]">
              {issues.length} issue{issues.length === 1 ? "" : "s"}
            </span>
          </div>

          {issues.length > 0 ? (
            <div className="flex flex-col gap-3">
              {issues.map((issue, index) => (
                <IssueRow
                  key={`${issue.enrichment || issue.title || "issue"}-${index}`}
                  issue={issue}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-green-100 bg-green-50 p-8 text-center">
              <CheckCircle2
                size={28}
                className="mx-auto mb-3 text-[var(--app-green)]"
              />

              <h3 className="text-sm font-extrabold text-[var(--app-green)]">
                No product issues detected
              </h3>

              <p className="mt-1 text-xs text-[var(--app-muted)]">
                This product currently meets the checks included in the audit.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}