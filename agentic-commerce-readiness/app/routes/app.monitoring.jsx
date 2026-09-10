//agentic-commerce-readiness/app/routes/app.monitoring.jsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouteLoaderData } from "react-router";
import { RefreshCw, History } from "lucide-react";

const BACKEND_URL = "https://geo.properoapps.in/api";
const PAGE_SIZE = 5;

export default function Monitoring() {
  const [history, setHistory] = useState([]);

  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [totalAudits, setTotalAudits] = useState(0);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const totalAuditsRef = useRef(0);

  const { shopDomain } = useRouteLoaderData("routes/app");

  useEffect(() => {
    if (!shopDomain) return;

    loadAuditHistory();

    const interval = setInterval(() => {
      checkForNewAudit();
    }, 10000);

    return () => clearInterval(interval);
  }, [shopDomain]);

  const loadAuditHistory = async (requestedPage = null) => {
    if (!shopDomain) return;

    setLoadingHistory(true);

    try {
      const metaResponse = await fetch(
        `${BACKEND_URL}/audits/history?shop_domain=${encodeURIComponent(
          shopDomain
        )}&page=1&page_size=${PAGE_SIZE}`
      );

      if (!metaResponse.ok) {
        throw new Error(`Failed to load audit metadata: ${metaResponse.status}`);
      }

      const metaData = await metaResponse.json();

      const total = Number(metaData.total) || 0;
      const highestPage = Number(metaData.total_pages) || 0;

      setTotalAudits(total);
      setTotalPages(highestPage);
      totalAuditsRef.current = total;

      if (total === 0 || highestPage === 0) {
        setHistory([]);
        setPage(1);
        return;
      }

      const targetPage = requestedPage ?? highestPage;

      const pageResponse = await fetch(
        `${BACKEND_URL}/audits/history?shop_domain=${encodeURIComponent(
          shopDomain
        )}&page=${targetPage}&page_size=${PAGE_SIZE}`
      );

      if (!pageResponse.ok) {
        throw new Error(`Failed to load audit history: ${pageResponse.status}`);
      }

      const pageData = await pageResponse.json();

      const mappedHistory = (pageData.items || []).map((item) => ({
        id: item.id,
        score: item.overall_score,
        date: item.created_at,
        issues: item.issues_found,
        products_scanned: item.products_scanned,
      }));

      setHistory(mappedHistory);
      setPage(targetPage);
    } catch (error) {
      console.error("Unable to load audit history:", error);
    } finally {
      setLoadingHistory(false);
    }
  };

  const checkForNewAudit = async () => {
    if (!shopDomain || loadingHistory) return;

    try {
      const response = await fetch(
        `${BACKEND_URL}/audits/history?shop_domain=${encodeURIComponent(
          shopDomain
        )}&page=1&page_size=${PAGE_SIZE}`
      );

      if (!response.ok) return;

      const data = await response.json();
      const backendTotal = Number(data.total) || 0;

      if (backendTotal !== totalAuditsRef.current) {
        await loadAuditHistory();
      }
    } catch (error) {
      console.error("Unable to check for new audits:", error);
    }
  };

  const currentScore = useMemo(() => {
    if (!history.length) return null;
    const latest = Number(history[history.length - 1]?.score);
    return Number.isFinite(latest) ? latest : null;
  }, [history]);

  const trajectory = useMemo(() => {
    if (history.length < 2) return null;
    const first = Number(history[0]?.score);
    const last = Number(history[history.length - 1]?.score);
    if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
    return { delta: last - first, cycles: history.length - 1 };
  }, [history]);

  return (
    <main className="min-h-screen bg-[var(--app-bg)] px-6 py-8">
      <div className="mx-auto max-w-7xl">
        {/* Header */}
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-[var(--app-text)]">Monitoring</h1>
            <p className="mt-0.5 text-sm text-[var(--app-muted)]">
              Track your store's agent readiness over time.
            </p>
          </div>

          <button
            onClick={() => loadAuditHistory()}
            className="flex items-center gap-2 rounded-lg border border-[var(--app-border)] bg-white px-4 py-2 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>

        {totalAudits === 0 ? (
          <EmptyState />
        ) : (
          <>
            {/* Hero score + trend card */}
            <section className="mb-6 rounded-xl border border-[var(--app-border)] bg-white p-6">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <h2 className="text-base font-bold text-[var(--app-text)]">
                    Agent Readiness Score
                  </h2>
                  <p className="mt-0.5 text-xs text-[var(--app-muted)]">
                    Longitudinal tracking of catalog, knowledge, policy, and protocol
                    improvements
                  </p>
                </div>

                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-bold text-[var(--app-text)]">
                    {currentScore !== null ? currentScore : "—"}
                  </span>
                  <span className="text-xs font-semibold text-[var(--app-muted)]">/ 100</span>
                </div>
              </div>

              {history.length > 0 ? (
                <TrendChart history={history} />
              ) : (
                <div className="rounded-lg bg-[var(--acr-cream)] p-8 text-center text-sm text-[var(--app-muted)]">
                  Complete an audit to start tracking your readiness trend.
                </div>
              )}

              {trajectory && (
                <div className="mt-4 flex items-center justify-between rounded-lg bg-[var(--acr-cream)] p-3 text-xs text-[var(--app-muted)]">
                  <span>
                    {trajectory.delta >= 0 ? "+" : ""}
                    {trajectory.delta} points over {trajectory.cycles} audit
                    {trajectory.cycles === 1 ? "" : "s"} (this page)
                  </span>
                  <span className="font-semibold text-[var(--app-green)]">
                    {trajectory.delta >= 0 ? "Upward trend" : "Downward trend"}
                  </span>
                </div>
              )}
            </section>

            {/* Audit history table */}
            <section className="rounded-xl border border-[var(--app-border)] bg-white overflow-hidden">
              <div className="border-b border-[var(--app-border)] px-6 py-5">
                <h2 className="font-semibold text-[var(--app-text)]">Audit History</h2>
                <p className="mt-0.5 text-sm text-[var(--app-muted)]">
                  Complete log of catalog scans and readiness measurements.
                </p>
              </div>

              {history.length === 0 ? (
                <div className="p-8 text-center text-sm text-[var(--app-muted)]">
                  No audit history available.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead className="bg-[var(--acr-cream)] text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
                      <tr>
                        <th className="px-6 py-3">Date</th>
                        <th className="px-6 py-3 text-right">Score</th>
                        <th className="px-6 py-3 text-right">Issues</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--app-border)] text-xs">
                      {[...history].reverse().map((item, idx) => (
                        <HistoryRow key={`${item.id || "audit"}-${idx}`} item={item} isFirst={idx === 0} />
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {totalPages > 1 && (
                <div className="flex items-center justify-between border-t border-[var(--app-border)] px-6 py-4">
                  <button
                    type="button"
                    onClick={() => loadAuditHistory(page - 1)}
                    disabled={page <= 1 || loadingHistory}
                    className="rounded-lg border border-[var(--app-border)] px-4 py-2 text-sm font-semibold text-[var(--app-text)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Previous
                  </button>

                  <span className="text-sm text-[var(--app-muted)]">
                    Page {page} of {totalPages}
                  </span>

                  <button
                    type="button"
                    onClick={() => loadAuditHistory(page + 1)}
                    disabled={page >= totalPages || loadingHistory}
                    className="rounded-lg border border-[var(--app-border)] px-4 py-2 text-sm font-semibold text-[var(--app-text)] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                  </button>
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </main>
  );
}

function TrendChart({ history }) {
  const width = 900;
  const height = 220;
  const paddingX = 45;
  const paddingY = 30;

  const usableWidth = width - paddingX * 2;
  const usableHeight = height - paddingY * 2;

  const points = history.map((item, index) => {
    const score = Math.max(0, Math.min(100, Number(item.score) || 0));

    const x =
      history.length === 1
        ? width / 2
        : paddingX + (index / (history.length - 1)) * usableWidth;

    const y = paddingY + ((100 - score) / 100) * usableHeight;

    return { x, y, score };
  });

  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`)
    .join(" ");

  const isLast = (i) => i === points.length - 1;

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="min-w-[700px] w-full"
        role="img"
        aria-label="Readiness score trend"
      >
        {[0, 25, 50, 75, 100].map((score) => {
          const y = paddingY + ((100 - score) / 100) * usableHeight;
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
              <text x="8" y={y + 4} fontSize="11" fill="var(--app-muted)">
                {score}
              </text>
            </g>
          );
        })}

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

        {points.map((point, index) => (
          <g key={index}>
            <circle
              cx={point.x}
              cy={point.y}
              r={isLast(index) ? 6 : 5}
              fill={isLast(index) ? "var(--app-green)" : "white"}
              stroke="var(--app-green)"
              strokeWidth="3"
            />
            <text
              x={point.x}
              y={point.y - 12}
              textAnchor="middle"
              fontSize="11"
              fontWeight={isLast(index) ? 800 : 600}
              fill={isLast(index) ? "var(--app-green)" : "var(--app-text)"}
            >
              {point.score}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function HistoryRow({ item, isFirst }) {
  const date = item.date ? new Date(item.date) : null;
  const formattedDate =
    date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString() : "Unknown date";

  const score = Number(item.score);
  const issues = Number(item.issues);

  return (
    <tr className="hover:bg-[var(--acr-cream)]">
      <td className="px-6 py-4 font-semibold text-[var(--app-text)]">
        {formattedDate}
        {isFirst && (
          <span className="ml-2 rounded border border-[var(--app-green)] bg-[var(--acr-cream)] px-1.5 py-0.5 text-[10px] font-bold text-[var(--app-green)]">
            Current
          </span>
        )}
      </td>
      <td className="px-6 py-4 text-right font-bold text-[var(--app-text)]">
        {Number.isFinite(score) ? `${score} / 100` : "—"}
      </td>
      <td className="px-6 py-4 text-right text-[var(--app-text)]">
        {Number.isFinite(issues) ? issues : "—"}
      </td>
    </tr>
  );
}

function EmptyState() {
  return (
    <div className="rounded-xl border border-dashed border-[var(--app-border)] bg-white p-10 text-center">
      <History size={36} className="mx-auto mb-4 text-[var(--app-muted)]" />
      <h2 className="mb-2 text-lg font-semibold text-[var(--app-text)]">
        No historical audits yet
      </h2>
      <p className="mx-auto max-w-lg text-sm leading-6 text-[var(--app-muted)]">
        Run an audit from the Dashboard to start tracking your agent readiness over
        time.
      </p>
    </div>
  );
}