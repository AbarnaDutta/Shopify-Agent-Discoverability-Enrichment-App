import { useState } from "react";

// Temporary demo values have been removed.
// The scores will be populated from the real audit API in the next step.

function Icon({ children, className = "h-5 w-5" }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      className={className}
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function ActivityIcon() {
  return (
    <Icon className="h-6 w-6">
      <path d="M3 12h4l2.2-7L14 19l2.5-7H21" />
    </Icon>
  );
}

function CartIcon() {
  return (
    <Icon className="h-6 w-6">
      <circle cx="9" cy="20" r="1" />
      <circle cx="18" cy="20" r="1" />
      <path d="M3 4h2l2.2 11.5a2 2 0 0 0 2 1.5h7.8a2 2 0 0 0 1.9-1.4L21 8H6" />
    </Icon>
  );
}

function BookIcon() {
  return (
    <Icon className="h-6 w-6">
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 0 4 22V5.5Z" />
      <path d="M4 5.5V22" />
      <path d="M8 7h8M8 11h8" />
    </Icon>
  );
}

function BoxIcon() {
  return (
    <Icon className="h-6 w-6">
      <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Z" />
      <path d="m4.5 7.8 7.5 4.3 7.5-4.3M12 12.1V21" />
    </Icon>
  );
}

function RefreshIcon() {
  return (
    <Icon className="h-4 w-4">
      <path d="M20 11a8 8 0 0 0-14.9-4M4 4v5h5" />
      <path d="M4 13a8 8 0 0 0 14.9 4M20 20v-5h-5" />
    </Icon>
  );
}

function ArrowIcon() {
  return (
    <Icon className="h-4 w-4">
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </Icon>
  );
}

function ScoreCard({
  title,
  value,
  suffix = "%",
  icon,
  orange = false,
}) {
  const displayValue =
    value === null || value === undefined ? "—" : value;

  const progressValue =
    typeof value === "number"
      ? Math.min(Math.max(value, 0), 100)
      : 0;

  return (
    <div className="rounded-2xl border border-[#e7e5df] bg-white p-6 shadow-[0_2px_12px_rgba(20,50,45,0.04)]">
      <div className="flex items-start gap-4">
        <div
          className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-xl ${
            orange
              ? "bg-[#f59a18] text-white"
              : "bg-[#063f3a] text-white"
          }`}
        >
          {icon}
        </div>

        <div className="min-w-0">
          <p className="text-sm font-medium text-[#71807d]">
            {title}
          </p>

          <div className="mt-1 flex items-baseline gap-1">
            <span className="text-4xl font-bold tracking-tight text-[#123d3a]">
              {displayValue}
            </span>

            {suffix && value !== null && value !== undefined && (
              <span className="text-xl font-semibold text-[#123d3a]">
                {suffix}
              </span>
            )}
          </div>

          {title === "Overall Readiness" && (
            <p className="mt-1 text-sm text-[#71807d]">
              out of 100
            </p>
          )}
        </div>
      </div>

      <div className="mt-5 h-1.5 overflow-hidden rounded-full bg-[#f1eadf]">
        <div
          className={`h-full rounded-full ${
            orange ? "bg-[#f59a18]" : "bg-[#063f3a]"
          }`}
          style={{ width: `${progressValue}%` }}
        />
      </div>
    </div>
  );
}

function ReadinessCircle({ score }) {
  const radius = 88;
  const circumference = 2 * Math.PI * radius;

  const numericScore =
    typeof score === "number"
      ? Math.min(Math.max(score, 0), 100)
      : 0;

  const progress =
    (numericScore / 100) * circumference;

  const displayScore =
    score === null || score === undefined ? "—" : score;

  return (
    <div className="relative flex h-64 w-64 items-center justify-center">
      <svg
        width="220"
        height="220"
        viewBox="0 0 220 220"
        className="-rotate-90"
      >
        <circle
          cx="110"
          cy="110"
          r={radius}
          stroke="#f1eadf"
          strokeWidth="12"
          fill="none"
        />

        <circle
          cx="110"
          cy="110"
          r={radius}
          stroke="#063f3a"
          strokeWidth="12"
          strokeLinecap="round"
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
        />

        <circle
          cx="110"
          cy="110"
          r="88"
          stroke="#f59a18"
          strokeWidth="12"
          fill="none"
          strokeLinecap="round"
          strokeDasharray="100 453"
          strokeDashoffset="-40"
        />
      </svg>

      <div className="absolute text-center">
        <div className="text-6xl font-bold tracking-tight text-[#063f3a]">
          {displayScore}
        </div>

        <div className="mt-1 text-sm font-medium text-[#71807d]">
          Overall score
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [auditUrl, setAuditUrl] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [auditAdded, setAuditAdded] = useState(false);

  // These will be populated from the backend.
  const [scores, setScores] = useState({
    overall: null,
    ucp: null,
    mcp: null,
    catalog: null,
  });

  function handleAddAudit() {
    if (!auditUrl.trim()) {
      alert("Please enter your website URL first.");
      return;
    }

    setAuditAdded(true);

    console.log("Audit added:", auditUrl);
  }

  async function handleRunAudit() {
    if (!auditUrl.trim()) {
      alert("Please enter your website URL first.");
      return;
    }

    setIsRunning(true);

    try {
      /*
       * Backend connection will be added in the next step.
       *
       * Expected flow:
       *
       * 1. POST /api/report-requests
       * 2. Receive job_id
       * 3. Poll GET /api/report-requests/{job_id}
       * 4. Wait for completed status
       * 5. Read the real scores
       * 6. setScores(...)
       */

      console.log("Running audit for:", auditUrl);

    } catch (error) {
      console.error("Audit failed:", error);
      alert("Audit failed. Please try again.");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#f8f8f6] text-[#123d3a]">
      <main className="mx-auto w-full max-w-[1500px] px-6 py-8 lg:px-10">

        {/* Header */}
        <div className="mb-7 flex flex-col justify-between gap-5 md:flex-row md:items-center">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-[#063f3a]">
              Agentic Commerce Readiness
            </h1>

            <p className="mt-1 text-sm text-[#71807d]">
              Monitor and improve your store&apos;s AI readiness.
            </p>
          </div>

          <div className="flex items-center gap-4">
            <div className="hidden items-center gap-2 text-sm text-[#71807d] sm:flex">
              <RefreshIcon />
              <span>Last updated: —</span>
            </div>
          </div>
        </div>

        {/* Score Cards */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4">

          <ScoreCard
            title="Overall Readiness"
            value={scores.overall}
            suffix=""
            icon={<ActivityIcon />}
          />

          <ScoreCard
            title="UCP Commerce"
            value={scores.ucp}
            icon={<CartIcon />}
            orange
          />

          <ScoreCard
            title="MCP Knowledge"
            value={scores.mcp}
            icon={<BookIcon />}
          />

          <ScoreCard
            title="Catalog"
            value={scores.catalog}
            icon={<BoxIcon />}
            orange
          />

        </div>

        {/* Main Dashboard */}
        <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-2">

          {/* AI Readiness */}
          <section className="rounded-2xl border border-[#e7e5df] bg-white p-7 shadow-[0_2px_12px_rgba(20,50,45,0.04)]">

            <div className="mb-2">
              <h2 className="text-xl font-bold text-[#063f3a]">
                AI Readiness
              </h2>

              <p className="mt-1 text-sm text-[#71807d]">
                Your store&apos;s overall agentic commerce score.
              </p>
            </div>

            <div className="flex min-h-[300px] items-center justify-center">
              <ReadinessCircle score={scores.overall} />
            </div>

            <div className="grid grid-cols-3 gap-3 border-t border-[#eeeae2] pt-5">

              <div className="text-center">
                <p className="text-xs text-[#71807d]">
                  UCP
                </p>

                <p className="mt-1 text-lg font-bold text-[#063f3a]">
                  {scores.ucp ?? "—"}
                  {scores.ucp !== null && scores.ucp !== undefined && "%"}
                </p>
              </div>

              <div className="border-x border-[#eeeae2] text-center">
                <p className="text-xs text-[#71807d]">
                  MCP
                </p>

                <p className="mt-1 text-lg font-bold text-[#063f3a]">
                  {scores.mcp ?? "—"}
                  {scores.mcp !== null && scores.mcp !== undefined && "%"}
                </p>
              </div>

              <div className="text-center">
                <p className="text-xs text-[#71807d]">
                  Catalog
                </p>

                <p className="mt-1 text-lg font-bold text-[#063f3a]">
                  {scores.catalog ?? "—"}
                  {scores.catalog !== null &&
                    scores.catalog !== undefined &&
                    "%"}
                </p>
              </div>

            </div>
          </section>

          {/* Priority Fixes */}
          <section className="rounded-2xl border border-[#e7e5df] bg-white p-7 shadow-[0_2px_12px_rgba(20,50,45,0.04)]">

            <div className="flex items-center justify-between">

              <div>
                <h2 className="text-xl font-bold text-[#063f3a]">
                  Priority Fixes
                </h2>

                <p className="mt-1 text-sm text-[#71807d]">
                  Issues that can improve your readiness score.
                </p>
              </div>

              <span className="rounded-full bg-[#f1f6f5] px-3 py-1 text-xs font-semibold text-[#063f3a]">
                Audit required
              </span>

            </div>

            <div className="mt-6 space-y-3">

              <div className="rounded-xl border border-[#eeeae2] bg-[#fffdfa] p-5">

                <div className="flex items-start gap-3">

                  <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-[#dcd9d0]" />

                  <div>
                    <h3 className="font-semibold text-[#123d3a]">
                      Product analysis
                    </h3>

                    <p className="mt-2 text-sm leading-6 text-[#71807d]">
                      Run an audit to identify product-level issues.
                    </p>
                  </div>

                </div>

              </div>

              <div className="rounded-xl border border-[#eeeae2] bg-[#fffdfa] p-5">

                <div className="flex items-start gap-3">

                  <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-[#dcd9d0]" />

                  <div>
                    <h3 className="font-semibold text-[#123d3a]">
                      Agent discovery analysis
                    </h3>

                    <p className="mt-2 text-sm leading-6 text-[#71807d]">
                      Run an audit to check your AI discovery files.
                    </p>
                  </div>

                </div>

              </div>

            </div>
          </section>
        </div>

        {/* Catalog Audit */}
        <section className="mt-6 rounded-2xl border border-[#e7e5df] bg-white p-7 shadow-[0_2px_12px_rgba(20,50,45,0.04)]">

          {/* Header */}
          <div>
            <h2 className="text-xl font-bold text-[#063f3a]">
              Catalog Audit
            </h2>

            <p className="mt-1 text-sm text-[#71807d]">
              Run an analysis of your Shopify catalog.
            </p>
          </div>

          {/* URL + Actions */}
          <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-end">

            {/* Website URL */}
            <div className="flex-1">

              <label
                htmlFor="audit-url"
                className="mb-2 block text-sm font-medium text-[#123d3a]"
              >
                Website URL
              </label>

              <input
                id="audit-url"
                type="url"
                value={auditUrl}
                onChange={(event) => {
                  setAuditUrl(event.target.value);
                  setAuditAdded(false);
                }}
                placeholder="https://yourstore.com"
                disabled={isRunning}
                draggable={false}
                className="h-12 w-full rounded-xl border border-[#dcd9d0] bg-white px-4 text-sm text-[#123d3a] outline-none transition placeholder:text-[#9aa5a2] focus:border-[#063f3a] focus:ring-2 focus:ring-[#063f3a]/10 disabled:bg-[#f5f5f3]"
              />

            </div>

            {/* Add Audit */}
            <button
              type="button"
              onClick={handleAddAudit}
              disabled={!auditUrl.trim() || isRunning}
              draggable={false}
              className="h-12 rounded-xl border border-[#063f3a] bg-white px-6 text-sm font-semibold text-[#063f3a] transition hover:bg-[#f1f6f5] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {auditAdded ? "✓ Audit Added" : "+ Add Audit"}
            </button>

            {/* Run Audit */}
            <button
              type="button"
              onClick={handleRunAudit}
              disabled={!auditUrl.trim() || isRunning}
              draggable={false}
              className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-[#f59a18] px-7 text-sm font-semibold text-white shadow-sm transition hover:bg-[#df870c] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <ActivityIcon />

              {isRunning
                ? "Running Audit..."
                : "Run Audit"}
            </button>

          </div>

          {/* Audit URL status */}
          {auditAdded && (
            <div className="mt-4 flex items-center gap-2 rounded-xl bg-[#f1f6f5] px-4 py-3 text-sm text-[#063f3a]">

              <span className="h-2 w-2 shrink-0 rounded-full bg-[#063f3a]" />

              <span>
                Audit added for:
              </span>

              <strong className="truncate">
                {auditUrl}
              </strong>

            </div>
          )}

          {/* Running state */}
          {isRunning && (
            <div className="mt-4 rounded-xl bg-[#fff1dc] px-4 py-3 text-sm font-medium text-[#a86400]">
              Audit is being processed. Please wait...
            </div>
          )}

        </section>

        {/* Bottom spacing */}
        <div className="h-10" />

      </main>
    </div>
  );
}