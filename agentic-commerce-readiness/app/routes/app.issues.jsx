import { useEffect, useMemo, useState } from "react";
import { Search, Filter, AlertCircle, CheckCircle2, ChevronDown } from "lucide-react";

const STORAGE_KEY = "acr_latest_report";

const severityConfig = {
  high: {
    label: "High",
    className: "bg-red-50 text-red-700 border-red-200",
    dot: "bg-red-500",
  },
  medium: {
    label: "Medium",
    className: "bg-orange-50 text-orange-700 border-orange-200",
    dot: "bg-orange-500",
  },
  low: {
    label: "Low",
    className: "bg-green-50 text-green-700 border-green-200",
    dot: "bg-green-600",
  },
};

function normalizeIssues(report) {
  if (!report) return [];

  const products = report.products || [];
  const issues = [];

  products.forEach((product) => {
    const enrichments = product.missing_enrichments || [];

    enrichments.forEach((issue, index) => {
      issues.push({
        id: `${product.product_id || product.id || "product"}-${index}`,
        productId: product.product_id || product.id || "",
        productTitle: product.title || "Untitled product",
        priority: issue.priority || "medium",
        category:
          issue.category ||
          issue.type ||
          issue.field ||
          "Catalog Enrichment",
        title:
          issue.enrichment ||
          issue.title ||
          issue.name ||
          "Missing product enrichment",
        description:
          issue.why_it_matters_for_agents ||
          issue.description ||
          "This information can help AI agents understand and recommend the product.",
        example: issue.example || "",
        status: issue.status || "open",
      });
    });
  });

  return issues;
}

function SeverityBadge({ priority }) {
  const config = severityConfig[priority] || severityConfig.medium;

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold ${config.className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      {config.label}
    </span>
  );
}

function StatusBadge({ status }) {
  const resolved =
    status === "resolved" ||
    status === "fixed" ||
    status === "complete";

  return resolved ? (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--app-green)]">
      <CheckCircle2 size={14} />
      Resolved
    </span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-[var(--app-muted)]">
      <AlertCircle size={14} />
      Open
    </span>
  );
}

function IssueCard({ issue, onSelect }) {
  return (
    <button
      type="button"
      onClick={() => onSelect(issue)}
      className="w-full rounded-2xl border border-[var(--app-border)] bg-white p-5 text-left transition-shadow hover:shadow-[0_12px_30px_rgba(6,63,58,0.08)]"
    >
      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <SeverityBadge priority={issue.priority} />

            <span className="rounded-full bg-[var(--app-orange-light)] px-2.5 py-1 text-[11px] font-semibold text-[var(--app-green)]">
              {issue.category}
            </span>
          </div>

          <h3 className="text-sm font-bold text-[var(--app-text)]">
            {issue.title}
          </h3>

          <p className="mt-1.5 line-clamp-2 text-xs leading-relaxed text-[var(--app-muted)]">
            {issue.description}
          </p>

          <div className="mt-3 text-xs font-semibold text-[var(--app-green)]">
            {issue.productTitle}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <StatusBadge status={issue.status} />
          <ChevronDown size={16} className="text-[var(--app-muted)]" />
        </div>
      </div>
    </button>
  );
}

function IssueDetail({ issue, onClose }) {
  if (!issue) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-3xl border border-[var(--app-border)] bg-white shadow-2xl">
        <div className="flex items-start justify-between border-b border-[var(--app-border)] px-6 py-5">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <SeverityBadge priority={issue.priority} />
            </div>

            <h2 className="text-xl font-extrabold text-[var(--app-text)]">
              {issue.title}
            </h2>

            <p className="mt-1 text-xs text-[var(--app-muted)]">
              {issue.productTitle}
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-full px-3 py-1 text-xl text-[var(--app-muted)] hover:bg-[var(--app-bg)]"
          >
            ×
          </button>
        </div>

        <div className="space-y-5 p-6">
          <div>
            <div className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.08em] text-[var(--app-muted)]">
              Why this matters
            </div>

            <p className="text-sm leading-relaxed text-[var(--app-text)]">
              {issue.description}
            </p>
          </div>

          <div>
            <div className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.08em] text-[var(--app-muted)]">
              Category
            </div>

            <div className="text-sm font-semibold text-[var(--app-text)]">
              {issue.category}
            </div>
          </div>

          {issue.example && (
            <div>
              <div className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.08em] text-[var(--app-muted)]">
                Example
              </div>

              <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] p-4 font-mono text-xs leading-relaxed text-[var(--app-text)]">
                {issue.example}
              </div>
            </div>
          )}

          <div className="flex justify-end border-t border-[var(--app-border)] pt-5">
            <button
              type="button"
              className="rounded-full bg-[var(--app-green)] px-5 py-2.5 text-sm font-bold text-white transition-colors hover:bg-[var(--app-green-dark)]"
              onClick={onClose}
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Issues() {
  const [report, setReport] = useState(null);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("all");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("all");
  const [selectedIssue, setSelectedIssue] = useState(null);

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

  const issues = useMemo(() => normalizeIssues(report), [report]);

  const categories = useMemo(() => {
    return [...new Set(issues.map((issue) => issue.category))].sort();
  }, [issues]);

  const filteredIssues = useMemo(() => {
    const query = search.trim().toLowerCase();

    return issues.filter((issue) => {
      const matchesSearch =
        !query ||
        issue.title.toLowerCase().includes(query) ||
        issue.productTitle.toLowerCase().includes(query) ||
        issue.description.toLowerCase().includes(query);

      const matchesSeverity =
        severity === "all" || issue.priority === severity;

      const matchesCategory =
        category === "all" || issue.category === category;

      const issueResolved =
        issue.status === "resolved" ||
        issue.status === "fixed" ||
        issue.status === "complete";

      const matchesStatus =
        status === "all" ||
        (status === "open" && !issueResolved) ||
        (status === "resolved" && issueResolved);

      return (
        matchesSearch &&
        matchesSeverity &&
        matchesCategory &&
        matchesStatus
      );
    });
  }, [issues, search, severity, category, status]);

  const highCount = issues.filter((i) => i.priority === "high").length;
  const mediumCount = issues.filter((i) => i.priority === "medium").length;
  const lowCount = issues.filter((i) => i.priority === "low").length;

  return (
    <div className="min-h-screen bg-[var(--app-bg)] px-5 py-8 text-[var(--app-text)] md:px-8">
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="mb-7">
          <div className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.1em] text-[var(--app-orange)]">
            Agentic Commerce Readiness
          </div>

          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-[var(--app-green)]">
                Issues
              </h1>

              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-[var(--app-muted)]">
                Review the catalog issues that may prevent AI agents from
                discovering, understanding, and recommending your products.
              </p>
            </div>

            <div className="rounded-xl border border-[var(--app-border)] bg-white px-4 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
                Total Issues
              </div>

              <div className="mt-0.5 text-2xl font-extrabold text-[var(--app-green)]">
                {issues.length}
              </div>
            </div>
          </div>
        </div>

        {/* Summary */}
        <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="rounded-2xl border border-red-100 bg-white p-4">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-red-500" />
              <span className="text-xs font-bold text-[var(--app-muted)]">
                High Priority
              </span>
            </div>

            <div className="mt-2 text-2xl font-extrabold text-red-700">
              {highCount}
            </div>
          </div>

          <div className="rounded-2xl border border-orange-100 bg-white p-4">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-orange-500" />
              <span className="text-xs font-bold text-[var(--app-muted)]">
                Medium Priority
              </span>
            </div>

            <div className="mt-2 text-2xl font-extrabold text-orange-700">
              {mediumCount}
            </div>
          </div>

          <div className="rounded-2xl border border-green-100 bg-white p-4">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-green-600" />
              <span className="text-xs font-bold text-[var(--app-muted)]">
                Low Priority
              </span>
            </div>

            <div className="mt-2 text-2xl font-extrabold text-[var(--app-green)]">
              {lowCount}
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="mb-5 rounded-2xl border border-[var(--app-border)] bg-white p-4">
          <div className="flex flex-col gap-3 lg:flex-row">
            <div className="relative flex-1">
              <Search
                size={17}
                className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--app-muted)]"
              />

              <input
                type="text"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search issues or products..."
                className="h-11 w-full rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] pl-10 pr-4 text-sm text-[var(--app-text)] outline-none transition focus:border-[var(--app-green)]"
              />
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative">
                <Filter
                  size={15}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--app-muted)]"
                />

                <select
                  value={severity}
                  onChange={(event) => setSeverity(event.target.value)}
                  className="h-11 min-w-[145px] appearance-none rounded-xl border border-[var(--app-border)] bg-white pl-9 pr-9 text-sm font-semibold text-[var(--app-text)] outline-none"
                >
                  <option value="all">All severity</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>

                <ChevronDown
                  size={15}
                  className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[var(--app-muted)]"
                />
              </div>

              <select
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                className="h-11 min-w-[175px] rounded-xl border border-[var(--app-border)] bg-white px-3 text-sm font-semibold text-[var(--app-text)] outline-none"
              >
                <option value="all">All categories</option>

                {categories.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>

              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="h-11 min-w-[145px] rounded-xl border border-[var(--app-border)] bg-white px-3 text-sm font-semibold text-[var(--app-text)] outline-none"
              >
                <option value="all">All status</option>
                <option value="open">Open</option>
                <option value="resolved">Resolved</option>
              </select>
            </div>
          </div>
        </div>

        {/* Results */}
        {filteredIssues.length > 0 ? (
          <div className="flex flex-col gap-3">
            {filteredIssues.map((issue) => (
              <IssueCard
                key={issue.id}
                issue={issue}
                onSelect={setSelectedIssue}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-2xl border border-[var(--app-border)] bg-white px-6 py-16 text-center">
            {!report ? (
              <>
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--app-orange-light)]">
                  <AlertCircle
                    size={22}
                    className="text-[var(--app-green)]"
                  />
                </div>

                <h2 className="text-lg font-extrabold text-[var(--app-green)]">
                  No audit report available
                </h2>

                <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-[var(--app-muted)]">
                  Run an audit from the Dashboard first. Once the audit
                  finishes, the detected catalog issues will appear here.
                </p>
              </>
            ) : (
              <>
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--app-orange-light)]">
                  <CheckCircle2
                    size={22}
                    className="text-[var(--app-green)]"
                  />
                </div>

                <h2 className="text-lg font-extrabold text-[var(--app-green)]">
                  No issues match your filters
                </h2>

                <p className="mt-2 text-sm text-[var(--app-muted)]">
                  Try changing the search or filter criteria.
                </p>
              </>
            )}
          </div>
        )}

        <div className="mt-6 text-center text-xs text-[var(--app-muted)]">
          Showing {filteredIssues.length} of {issues.length} issues
        </div>
      </div>

      <IssueDetail
        issue={selectedIssue}
        onClose={() => setSelectedIssue(null)}
      />
    </div>
  );
}