import { useEffect, useMemo, useState } from "react";
import {
  Bot,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Play,
  RefreshCw,
  XCircle,
} from "lucide-react";

const TESTS = [
  {
    id: "product-discovery",
    name: "Product Discovery",
    description:
      "Checks whether AI agents can discover and locate your products.",
  },
  {
    id: "product-understanding",
    name: "Product Understanding",
    description:
      "Checks whether product information is complete and understandable to AI agents.",
  },
  {
    id: "personalization",
    name: "Personalization",
    description:
      "Checks whether product data provides enough context for personalized recommendations.",
  },
  {
    id: "commerce-flow",
    name: "Commerce Flow",
    description:
      "Checks whether an agent has enough information to support a commerce journey.",
  },
];

export default function AgentTests() {
  const [report, setReport] = useState(null);
  const [results, setResults] = useState({});
  const [running, setRunning] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("acr_latest_report");

    if (!stored) return;

    try {
      setReport(JSON.parse(stored));
    } catch (error) {
      console.error("Unable to load audit report:", error);
    }
  }, []);

  const products = report?.products || [];

  const overallScore = useMemo(() => {
    if (!products.length) return null;

    const scores = products
      .map((product) =>
        Number(
          product.readiness_score ??
            product.score ??
            product.readinessScore
        )
      )
      .filter((score) => Number.isFinite(score));

    if (!scores.length) return null;

    return Math.round(
      scores.reduce((sum, score) => sum + score, 0) / scores.length
    );
  }, [products]);

  const getTestResult = (testId) => {
    if (results[testId]) return results[testId];

    if (!report) {
      return {
        status: "needs-config",
        label: "Needs configuration",
        detail: "Run an audit first.",
      };
    }

    if (!products.length) {
      return {
        status: "needs-config",
        label: "Needs configuration",
        detail: "No product data was returned by the audit.",
      };
    }

    const score = overallScore ?? 0;

    if (testId === "product-discovery") {
      if (score >= 80) {
        return {
          status: "passed",
          label: "Passed",
          detail: "Products have sufficient discovery information.",
        };
      }

      if (score >= 60) {
        return {
          status: "partial",
          label: "Partial",
          detail: "Some product discovery information needs improvement.",
        };
      }

      return {
        status: "failed",
        label: "Failed",
        detail: "Product discovery readiness is below the recommended level.",
      };
    }

    if (testId === "product-understanding") {
      const affected = products.filter(
        (product) =>
          Array.isArray(product.missing_enrichments) &&
          product.missing_enrichments.length > 0
      ).length;

      if (affected === 0) {
        return {
          status: "passed",
          label: "Passed",
          detail: "No missing product enrichments were reported.",
        };
      }

      if (affected < products.length) {
        return {
          status: "partial",
          label: "Partial",
          detail: `${affected} of ${products.length} products have missing enrichments.`,
        };
      }

      return {
        status: "failed",
        label: "Failed",
        detail: "All analyzed products contain missing enrichments.",
      };
    }

    if (testId === "personalization") {
      if (score >= 80) {
        return {
          status: "passed",
          label: "Passed",
          detail: "Product data provides strong contextual information.",
        };
      }

      if (score >= 60) {
        return {
          status: "partial",
          label: "Partial",
          detail: "Additional product context could improve personalization.",
        };
      }

      return {
        status: "failed",
        label: "Failed",
        detail: "Product context is currently insufficient.",
      };
    }

    if (testId === "commerce-flow") {
      if (score >= 85) {
        return {
          status: "passed",
          label: "Passed",
          detail: "Store readiness supports an agent commerce flow.",
        };
      }

      if (score >= 65) {
        return {
          status: "partial",
          label: "Partial",
          detail: "Some readiness improvements are recommended.",
        };
      }

      return {
        status: "failed",
        label: "Failed",
        detail: "The current readiness score indicates commerce-flow gaps.",
      };
    }

    return {
      status: "needs-config",
      label: "Needs configuration",
      detail: "Test configuration is unavailable.",
    };
  };

  const runTest = async (testId) => {
    setResults((previous) => ({
      ...previous,
      [testId]: {
        status: "running",
        label: "Running",
        detail: "Analyzing the latest audit data...",
      },
    }));

    await new Promise((resolve) => setTimeout(resolve, 800));

    setResults((previous) => ({
      ...previous,
      [testId]: getTestResult(testId),
    }));
  };

  const runAllTests = async () => {
    setRunning(true);

    for (const test of TESTS) {
      await runTest(test.id);
    }

    setRunning(false);
  };

  const refreshReport = () => {
    const stored = localStorage.getItem("acr_latest_report");

    if (!stored) {
      setReport(null);
      setResults({});
      return;
    }

    try {
      setReport(JSON.parse(stored));
      setResults({});
    } catch (error) {
      console.error(error);
    }
  };

  const statusCounts = TESTS.reduce(
    (counts, test) => {
      const result = getTestResult(test.id);

      if (result.status === "passed") counts.passed += 1;
      if (result.status === "partial") counts.partial += 1;
      if (result.status === "failed") counts.failed += 1;
      if (result.status === "needs-config") counts.needsConfig += 1;

      return counts;
    },
    {
      passed: 0,
      partial: 0,
      failed: 0,
      needsConfig: 0,
    }
  );

  return (
    <main className="min-h-screen bg-[var(--app-bg)] px-6 py-8">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Bot
                size={24}
                className="text-[var(--app-green)]"
              />

              <h1 className="text-2xl font-bold text-[var(--app-text)]">
                Agent Tests
              </h1>
            </div>

            <p className="max-w-2xl text-sm text-[var(--app-muted)]">
              Test how well your current Shopify store data supports
              AI-agent discovery, understanding, personalization, and
              commerce flows.
            </p>
          </div>

          <div className="flex gap-2">
            <button
              onClick={refreshReport}
              className="flex items-center gap-2 rounded-lg border border-[var(--app-border)] bg-white px-4 py-2.5 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
            >
              <RefreshCw size={16} />
              Refresh
            </button>

            <button
              onClick={runAllTests}
              disabled={running || !report}
              className="flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--app-green-dark)] disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Play size={16} />
              {running ? "Running..." : "Run all tests"}
            </button>
          </div>
        </div>

        {!report ? (
          <EmptyState />
        ) : (
          <>
            {/* Summary */}
            <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <SummaryCard
                label="Tests"
                value={TESTS.length}
              />

              <SummaryCard
                label="Passed"
                value={statusCounts.passed}
                icon={<CheckCircle2 size={17} />}
              />

              <SummaryCard
                label="Partial"
                value={statusCounts.partial}
                icon={<CircleAlert size={17} />}
              />

              <SummaryCard
                label="Failed"
                value={statusCounts.failed}
                icon={<XCircle size={17} />}
              />

              <SummaryCard
                label="Products"
                value={products.length}
              />
            </div>

            {/* Test cards */}
            <div className="space-y-4">
              {TESTS.map((test) => {
                const result = getTestResult(test.id);

                return (
                  <TestCard
                    key={test.id}
                    test={test}
                    result={result}
                    onRun={() => runTest(test.id)}
                  />
                );
              })}
            </div>

            {/* Data source */}
            <div className="mt-6 rounded-xl border border-[var(--app-border)] bg-white p-5">
              <h2 className="mb-2 font-semibold text-[var(--app-text)]">
                Test data source
              </h2>

              <p className="text-sm leading-6 text-[var(--app-muted)]">
                These tests use the latest completed audit report
                generated by your real backend. No prototype product
                data is used.
              </p>

              {overallScore !== null && (
                <div className="mt-4 flex items-center gap-2 text-sm">
                  <span className="font-medium text-[var(--app-text)]">
                    Current readiness:
                  </span>

                  <span className="font-bold text-[var(--app-green)]">
                    {overallScore}%
                  </span>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}

function TestCard({ test, result, onRun }) {
  const isRunning = result.status === "running";

  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-white p-5">
      <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
        <div className="flex gap-4">
          <div className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--app-orange-light)] text-[var(--app-green)]">
            <Bot size={19} />
          </div>

          <div>
            <h2 className="font-semibold text-[var(--app-text)]">
              {test.name}
            </h2>

            <p className="mt-1 max-w-2xl text-sm leading-6 text-[var(--app-muted)]">
              {test.description}
            </p>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-3">
          <StatusBadge result={result} />

          <button
            onClick={onRun}
            disabled={isRunning}
            className="flex items-center gap-2 rounded-lg border border-[var(--app-border)] px-3 py-2 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)] disabled:opacity-50"
          >
            {isRunning ? (
              <RefreshCw
                size={15}
                className="animate-spin"
              />
            ) : (
              <Play size={15} />
            )}

            {isRunning ? "Running" : "Run"}
          </button>
        </div>
      </div>

      <div className="mt-5 border-t border-[var(--app-border)] pt-4">
        <div className="flex items-center gap-2 text-sm text-[var(--app-muted)]">
          <Clock3 size={15} />

          <span>{result.detail}</span>
        </div>
      </div>
    </div>
  );
}

function StatusBadge({ result }) {
  if (result.status === "passed") {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-[var(--app-orange-light)] px-3 py-1.5 text-xs font-bold text-[var(--app-green)]">
        <CheckCircle2 size={14} />
        Passed
      </span>
    );
  }

  if (result.status === "partial") {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-orange-50 px-3 py-1.5 text-xs font-bold text-orange-700">
        <CircleAlert size={14} />
        Partial
      </span>
    );
  }

  if (result.status === "failed") {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-red-50 px-3 py-1.5 text-xs font-bold text-red-700">
        <XCircle size={14} />
        Failed
      </span>
    );
  }

  if (result.status === "running") {
    return (
      <span className="flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1.5 text-xs font-bold text-gray-700">
        <RefreshCw
          size={14}
          className="animate-spin"
        />
        Running
      </span>
    );
  }

  return (
    <span className="rounded-full bg-gray-100 px-3 py-1.5 text-xs font-bold text-gray-600">
      Needs configuration
    </span>
  );
}

function SummaryCard({ label, value, icon }) {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-white p-4">
      <div className="mb-2 flex items-center gap-2 text-[var(--app-muted)]">
        {icon}
        <span className="text-xs font-medium">
          {label}
        </span>
      </div>

      <div className="text-2xl font-bold text-[var(--app-text)]">
        {value}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-white p-10 text-center">
      <Bot
        size={36}
        className="mx-auto mb-4 text-[var(--app-muted)]"
      />

      <h2 className="mb-2 text-lg font-semibold text-[var(--app-text)]">
        No audit data available
      </h2>

      <p className="mx-auto max-w-lg text-sm leading-6 text-[var(--app-muted)]">
        Run an audit from the Dashboard first. Agent tests will use
        the resulting real Shopify audit data.
      </p>
    </div>
  );
}