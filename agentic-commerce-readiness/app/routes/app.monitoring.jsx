import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  Clock3,
  FileText,
  RefreshCw,
  TrendingUp,
} from "lucide-react";

export default function Monitoring() {
  const [report, setReport] = useState(null);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = () => {
    const storedReport = localStorage.getItem("acr_latest_report");
    const storedHistory = localStorage.getItem("acr_audit_history");

    if (storedReport) {
      try {
        const parsedReport = JSON.parse(storedReport);
        setReport(parsedReport);
      } catch (error) {
        console.error("Unable to parse latest report:", error);
      }
    }

    if (storedHistory) {
      try {
        const parsedHistory = JSON.parse(storedHistory);

        if (Array.isArray(parsedHistory)) {
          setHistory(parsedHistory);
        }
      } catch (error) {
        console.error("Unable to parse audit history:", error);
      }
    }
  };

  const currentScore = useMemo(() => {
    if (!report) return null;

    if (
      report.overall_readiness_score !== undefined &&
      report.overall_readiness_score !== null
    ) {
      return Number(report.overall_readiness_score);
    }

    if (
      report.readiness_score !== undefined &&
      report.readiness_score !== null
    ) {
      return Number(report.readiness_score);
    }

    const products = report.products || [];

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
      scores.reduce((sum, score) => sum + score, 0) /
        scores.length
    );
  }, [report]);

  const previousScore = useMemo(() => {
    if (!history.length) return null;

    const scores = history
      .map((item) => Number(item.score))
      .filter((score) => Number.isFinite(score));

    if (!scores.length) return null;

    return scores[scores.length - 1];
  }, [history]);

  const scoreChange =
    currentScore !== null && previousScore !== null
      ? currentScore - previousScore
      : null;

  const displayHistory = useMemo(() => {
    const items = [...history];

    if (currentScore !== null) {
      const latest = {
        id: "current",
        score: currentScore,
        date: new Date().toISOString(),
        status: "Completed",
        current: true,
      };

      items.push(latest);
    }

    return items.reverse();
  }, [history, currentScore]);

  const maxScore = 100;

  return (
    <main className="min-h-screen bg-[var(--app-bg)] px-6 py-8">
      <div className="mx-auto max-w-7xl">

        {/* Header */}
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Activity
                size={24}
                className="text-[var(--app-green)]"
              />

              <h1 className="text-2xl font-bold text-[var(--app-text)]">
                Monitoring
              </h1>
            </div>

            <p className="max-w-2xl text-sm text-[var(--app-muted)]">
              Track your store's agent-readiness score and review
              previous audits.
            </p>
          </div>

          <button
            onClick={loadData}
            className="flex items-center gap-2 rounded-lg border border-[var(--app-border)] bg-white px-4 py-2.5 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>

        {!report ? (
          <EmptyState />
        ) : (
          <>
            {/* Score summary */}
            <div className="mb-6 grid gap-4 md:grid-cols-3">

              <ScoreCard
                title="Current readiness"
                value={
                  currentScore !== null
                    ? `${currentScore}%`
                    : "—"
                }
                icon={<TrendingUp size={18} />}
              />

              <ScoreCard
                title="Score change"
                value={
                  scoreChange !== null
                    ? `${scoreChange >= 0 ? "+" : ""}${scoreChange}%`
                    : "—"
                }
                icon={<Activity size={18} />}
              />

              <ScoreCard
                title="Audits recorded"
                value={displayHistory.length}
                icon={<FileText size={18} />}
              />
            </div>

            {/* Trend */}
            <section className="mb-6 rounded-xl border border-[var(--app-border)] bg-white p-6">
              <div className="mb-6">
                <h2 className="font-semibold text-[var(--app-text)]">
                  Readiness trend
                </h2>

                <p className="mt-1 text-sm text-[var(--app-muted)]">
                  Agent-readiness score across completed audits.
                </p>
              </div>

              {displayHistory.length > 0 ? (
                <TrendChart history={displayHistory} />
              ) : (
                <div className="rounded-lg bg-[var(--acr-cream)] p-8 text-center text-sm text-[var(--app-muted)]">
                  Complete an audit to start tracking your readiness
                  trend.
                </div>
              )}
            </section>

            {/* Audit history */}
            <section className="rounded-xl border border-[var(--app-border)] bg-white">
              <div className="border-b border-[var(--app-border)] px-6 py-5">
                <h2 className="font-semibold text-[var(--app-text)]">
                  Audit history
                </h2>

                <p className="mt-1 text-sm text-[var(--app-muted)]">
                  Previous readiness measurements.
                </p>
              </div>

              {displayHistory.length === 0 ? (
                <div className="p-8 text-center text-sm text-[var(--app-muted)]">
                  No audit history available.
                </div>
              ) : (
                <div className="divide-y divide-[var(--app-border)]">
                  {displayHistory.map((item, index) => (
                    <HistoryRow
                      key={`${item.id || "audit"}-${index}`}
                      item={item}
                    />
                  ))}
                </div>
              )}
            </section>

            {/* Monitoring note */}
            <div className="mt-6 rounded-xl border border-[var(--app-border)] bg-white p-5">
              <div className="flex gap-3">
                <CheckCircle2
                  size={20}
                  className="mt-0.5 shrink-0 text-[var(--app-green)]"
                />

                <div>
                  <h3 className="font-semibold text-[var(--app-text)]">
                    Monitoring is connected to your audit data
                  </h3>

                  <p className="mt-1 text-sm leading-6 text-[var(--app-muted)]">
                    The current score comes from the latest completed
                    audit. Historical entries are stored locally until
                    the backend exposes a dedicated audit-history
                    endpoint.
                  </p>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

function ScoreCard({ title, value, icon }) {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-white p-5">
      <div className="mb-3 flex items-center gap-2 text-[var(--app-muted)]">
        {icon}

        <span className="text-xs font-medium">
          {title}
        </span>
      </div>

      <div className="text-2xl font-bold text-[var(--app-text)]">
        {value}
      </div>
    </div>
  );
}

function TrendChart({ history }) {
  const width = 900;
  const height = 260;
  const paddingX = 45;
  const paddingY = 30;

  const usableWidth = width - paddingX * 2;
  const usableHeight = height - paddingY * 2;

  const points = history.map((item, index) => {
    const score = Math.max(
      0,
      Math.min(100, Number(item.score) || 0)
    );

    const x =
      history.length === 1
        ? width / 2
        : paddingX +
          (index / (history.length - 1)) *
            usableWidth;

    const y =
      paddingY +
      ((100 - score) / 100) * usableHeight;

    return {
      x,
      y,
      score,
      item,
    };
  });

  const path = points
    .map(
      (point, index) =>
        `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`
    )
    .join(" ");

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="min-w-[700px] w-full"
        role="img"
        aria-label="Readiness score trend"
      >
        {/* Grid */}
        {[0, 25, 50, 75, 100].map((score) => {
          const y =
            paddingY +
            ((100 - score) / 100) *
              usableHeight;

          return (
            <g key={score}>
              <line
                x1={paddingX}
                x2={width - paddingX}
                y1={y}
                y2={y}
                stroke="var(--app-border)"
                strokeWidth="1"
              />

              <text
                x="8"
                y={y + 4}
                fontSize="11"
                fill="var(--app-muted)"
              >
                {score}
              </text>
            </g>
          );
        })}

        {/* Trend line */}
        {points.length > 1 && (
          <path
            d={path}
            fill="none"
            stroke="var(--app-green)"
            strokeWidth="3"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {/* Points */}
        {points.map((point, index) => (
          <g key={index}>
            <circle
              cx={point.x}
              cy={point.y}
              r="6"
              fill="white"
              stroke="var(--app-green)"
              strokeWidth="3"
            />

            <text
              x={point.x}
              y={point.y - 12}
              textAnchor="middle"
              fontSize="11"
              fontWeight="600"
              fill="var(--app-text)"
            >
              {point.score}%
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function HistoryRow({ item }) {
  const date = item.date
    ? new Date(item.date)
    : null;

  const formattedDate =
    date && !Number.isNaN(date.getTime())
      ? date.toLocaleString()
      : "Unknown date";

  const score = Number(item.score);

  return (
    <div className="flex flex-col gap-3 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--app-orange-light)]">
          <Clock3
            size={17}
            className="text-[var(--app-green)]"
          />
        </div>

        <div>
          <p className="text-sm font-semibold text-[var(--app-text)]">
            {item.current
              ? "Latest audit"
              : "Audit"}
          </p>

          <p className="text-xs text-[var(--app-muted)]">
            {formattedDate}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <span className="text-sm text-[var(--app-muted)]">
          {item.status || "Completed"}
        </span>

        <span className="min-w-[70px] text-right text-lg font-bold text-[var(--app-green)]">
          {Number.isFinite(score)
            ? `${score}%`
            : "—"}
        </span>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-white p-10 text-center">
      <Activity
        size={36}
        className="mx-auto mb-4 text-[var(--app-muted)]"
      />

      <h2 className="mb-2 text-lg font-semibold text-[var(--app-text)]">
        No audit data available
      </h2>

      <p className="mx-auto max-w-lg text-sm leading-6 text-[var(--app-muted)]">
        Run an audit from the Dashboard first. Monitoring will use
        the resulting readiness information.
      </p>
    </div>
  );
}