import { useEffect, useMemo, useState } from "react";
import { useLoaderData, useRevalidator } from "react-router";
import { boundary } from "@shopify/shopify-app-react-router/server";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  ExternalLink,
  FileText,
  Globe,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";

import { authenticate } from "../shopify.server";

const BACKEND_URL = "https://geo.properoapps.in/api";

const FILE_DEFINITIONS = [
  {
    key: "agents_md",
    label: "agents.md",
    description: "Canonical agent guide",
    path: "/agents.md",
  },
  {
    key: "llms_txt",
    label: "llms.txt",
    description: "Quick machine-readable store summary",
    path: "/llms.txt",
  },
  {
    key: "llms_full_txt",
    label: "llms-full.txt",
    description: "Detailed machine-readable store context",
    path: "/llms-full.txt",
  },
  {
    key: "ucp_manifest",
    label: "UCP manifest",
    description: "Universal Commerce Protocol discovery",
    path: "/.well-known/ucp",
  },
];

const STATUS_CONFIG = {
  served_custom: {
    label: "Served and customized",
    tone: "success",
    icon: Check,
  },
  served_default: {
    label: "Served — Shopify default",
    tone: "warning",
    icon: AlertCircle,
  },
  redirects: {
    label: "Redirects to agents.md",
    tone: "info",
    icon: ExternalLink,
  },
  missing: {
    label: "Not reachable",
    tone: "danger",
    icon: X,
  },
  unreachable: {
    label: "Could not connect",
    tone: "danger",
    icon: X,
  },
};

const CUSTOMIZATION_LABELS = {
  default_skeleton: "Shopify default skeleton",
  lightly_customized: "Lightly customized",
  heavily_customized: "Heavily customized",
  empty: "Empty or too thin",
  unknown: "Not evaluated",
};

export const loader = async ({ request }) => {
  const { session } = await authenticate.admin(request);

  const shopDomain = session.shop;

  const url =
    `${BACKEND_URL}/audits/latest?shop_domain=` +
    encodeURIComponent(shopDomain);

  try {
    const response = await fetch(url);

    if (response.status === 404) {
      return {
        ok: true,
        shopDomain,
        audit: null,
        error: null,
      };
    }

    if (!response.ok) {
      const text = await response.text();

      return {
        ok: false,
        shopDomain,
        audit: null,
        error: `Backend returned HTTP ${response.status}: ${text.slice(0, 300)}`,
      };
    }

    const audit = await response.json();

    return {
      ok: true,
      shopDomain,
      audit,
      error: null,
    };
  } catch (error) {
    console.error("[Agent Discovery] Backend request failed:", error);

    return {
      ok: false,
      shopDomain,
      audit: null,
      error:
        "Could not connect to the Agentic Commerce backend. Please try again.",
    };
  }
};

export default function AgentDiscovery() {
  const { ok, shopDomain, audit, error } = useLoaderData();
  const revalidator = useRevalidator();

  const [expandedFile, setExpandedFile] = useState("agents_md");
  const [copied, setCopied] = useState(null);

  const agentDiscovery = audit?.agent_discovery || null;

  const files = agentDiscovery?.files || {};

  const reachableCount = useMemo(() => {
    return FILE_DEFINITIONS.filter((file) => {
      const status = files[file.key]?.status;

      return [
        "served_custom",
        "served_default",
        "redirects",
      ].includes(status);
    }).length;
  }, [files]);

  const customizedCount = useMemo(() => {
    return FILE_DEFINITIONS.filter((file) => {
      const customization = files[file.key]?.customization;

      return customization === "heavily_customized";
    }).length;
  }, [files]);

  const recommendations = agentDiscovery?.recommendations || [];

  useEffect(() => {
    if (copied === null) return;

    const timer = setTimeout(() => {
      setCopied(null);
    }, 1800);

    return () => clearTimeout(timer);
  }, [copied]);

  const handleRefresh = () => {
    revalidator.revalidate();
  };

  const handleCopy = async (text, key) => {
    if (!text) return;

    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
    } catch (copyError) {
      console.error("Copy failed:", copyError);
    }
  };

  const getStoreFileUrl = (path) => {
    return `https://${shopDomain}${path}`;
  };

  if (error) {
    return (
      <main className="min-h-screen bg-[var(--app-bg)] px-6 py-8">
        <div className="mx-auto max-w-6xl">
          <PageHeader
            shopDomain={shopDomain}
            onRefresh={handleRefresh}
            refreshing={revalidator.state === "loading"}
          />

          <div className="mt-8 rounded-2xl border border-red-200 bg-white p-8 shadow-sm">
            <div className="flex items-start gap-4">
              <div className="rounded-xl bg-red-50 p-3">
                <AlertCircle className="h-6 w-6 text-red-600" />
              </div>

              <div>
                <h2 className="text-lg font-semibold text-[var(--app-text)]">
                  Unable to load Agent Discovery
                </h2>

                <p className="mt-2 text-sm leading-6 text-[var(--app-muted)]">
                  {error}
                </p>

                <button
                  type="button"
                  onClick={handleRefresh}
                  className="mt-5 inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--app-green-dark)]"
                >
                  <RefreshCw className="h-4 w-4" />
                  Try again
                </button>
              </div>
            </div>
          </div>
        </div>
      </main>
    );
  }

  if (!audit) {
    return (
      <main className="min-h-screen bg-[var(--app-bg)] px-6 py-8">
        <div className="mx-auto max-w-6xl">
          <PageHeader
            shopDomain={shopDomain}
            onRefresh={handleRefresh}
            refreshing={revalidator.state === "loading"}
          />

          <div className="mt-8 rounded-2xl border border-[var(--app-border)] bg-white p-10 text-center shadow-sm">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--app-orange-light)]">
              <Sparkles className="h-7 w-7 text-[var(--app-orange)]" />
            </div>

            <h2 className="mt-5 text-xl font-semibold text-[var(--app-text)]">
              Run an audit first
            </h2>

            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[var(--app-muted)]">
              Agent Discovery data is generated when your Shopify store is
              audited. Run an audit from the Dashboard and come back here to
              see the real discovery results.
            </p>
          </div>
        </div>
      </main>
    );
  }

  if (!agentDiscovery) {
    return (
      <main className="min-h-screen bg-[var(--app-bg)] px-6 py-8">
        <div className="mx-auto max-w-6xl">
          <PageHeader
            shopDomain={shopDomain}
            onRefresh={handleRefresh}
            refreshing={revalidator.state === "loading"}
          />

          <div className="mt-8 rounded-2xl border border-[var(--app-border)] bg-white p-10 text-center shadow-sm">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--app-orange-light)]">
              <Globe className="h-7 w-7 text-[var(--app-orange)]" />
            </div>

            <h2 className="mt-5 text-xl font-semibold text-[var(--app-text)]">
              Agent Discovery data unavailable
            </h2>

            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[var(--app-muted)]">
              The latest audit exists, but it does not contain Agent Discovery
              results. Run a new audit to generate them.
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[var(--app-bg)] px-6 py-8">
      <div className="mx-auto max-w-6xl">
        <PageHeader
          shopDomain={shopDomain}
          onRefresh={handleRefresh}
          refreshing={revalidator.state === "loading"}
        />

        {/* Summary */}
        <section className="mt-8 grid gap-4 md:grid-cols-3">
          <SummaryCard
            icon={<Globe className="h-5 w-5" />}
            label="Endpoints reachable"
            value={`${reachableCount}/4`}
            description="Agent discovery surfaces detected on your storefront."
          />

          <SummaryCard
            icon={<Sparkles className="h-5 w-5" />}
            label="Templates customized"
            value={`${agentDiscovery.templates_customized ?? customizedCount}/${agentDiscovery.templates_total ?? 3}`}
            description="Templates customized beyond Shopify's default."
          />

          <SummaryCard
            icon={<ShieldCheck className="h-5 w-5" />}
            label="Canonical guide"
            value={agentDiscovery.canonical_served ? "Available" : "Missing"}
            description="Whether the canonical agents.md endpoint is reachable."
          />
        </section>

        {/* Overall summary */}
        <section className="mt-6 rounded-2xl border border-[var(--app-border)] bg-white p-6 shadow-sm">
          <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--app-muted)]">
                Agent Discovery
              </p>

              <h2 className="mt-2 text-xl font-semibold text-[var(--app-text)]">
                Storefront discovery readiness
              </h2>

              <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--app-muted)]">
                {agentDiscovery.summary ||
                  "Agent discovery results from the latest audit."}
              </p>
            </div>

            {agentDiscovery.checked_at && (
              <div className="shrink-0 rounded-lg bg-[var(--app-panel,var(--acr-panel))] px-3 py-2 text-xs text-[var(--app-muted)]">
                Checked{" "}
                {formatDate(agentDiscovery.checked_at)}
              </div>
            )}
          </div>
        </section>

        {/* Discovery files */}
        <section className="mt-6">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-[var(--app-text)]">
              Agent Discovery Files
            </h2>

            <p className="mt-1 text-sm text-[var(--app-muted)]">
              Real storefront checks performed during the latest audit.
            </p>
          </div>

          <div className="space-y-3">
            {FILE_DEFINITIONS.map((file) => {
              const info = files[file.key] || {};
              const isExpanded = expandedFile === file.key;

              return (
                <DiscoveryFileCard
                  key={file.key}
                  file={file}
                  info={info}
                  expanded={isExpanded}
                  onToggle={() =>
                    setExpandedFile(isExpanded ? null : file.key)
                  }
                  copied={copied === file.key}
                  onCopy={() =>
                    handleCopy(
                      getFileSummaryText(file, info),
                      file.key,
                    )
                  }
                  url={getStoreFileUrl(file.path)}
                />
              );
            })}
          </div>
        </section>

        {/* Recommendations */}
        <section className="mt-8">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-[var(--app-text)]">
              Shopify-Aligned Recommendations
            </h2>

            <p className="mt-1 text-sm text-[var(--app-muted)]">
              Recommendations generated by the backend from the actual
              storefront discovery checks.
            </p>
          </div>

          {recommendations.length === 0 ? (
            <div className="rounded-2xl border border-[var(--app-border)] bg-white p-6 text-sm text-[var(--app-muted)] shadow-sm">
              No Agent Discovery recommendations were returned.
            </div>
          ) : (
            <div className="space-y-4">
              {recommendations.map((recommendation, index) => (
                <RecommendationCard
                  key={`${recommendation.enrichment}-${index}`}
                  recommendation={recommendation}
                />
              ))}
            </div>
          )}
        </section>

        {/* Audit metadata */}
        <section className="mt-8 mb-10 rounded-2xl border border-[var(--app-border)] bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-center gap-x-8 gap-y-3 text-xs text-[var(--app-muted)]">
            <span>
              <strong className="font-semibold text-[var(--app-text)]">
                Audit:
              </strong>{" "}
              {audit.id}
            </span>

            <span>
              <strong className="font-semibold text-[var(--app-text)]">
                Created:
              </strong>{" "}
              {formatDate(audit.created_at)}
            </span>

            {audit.provider && (
              <span>
                <strong className="font-semibold text-[var(--app-text)]">
                  Provider:
                </strong>{" "}
                {audit.provider}
              </span>
            )}

            {audit.model && (
              <span>
                <strong className="font-semibold text-[var(--app-text)]">
                  Model:
                </strong>{" "}
                {audit.model}
              </span>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

function PageHeader({ shopDomain, onRefresh, refreshing }) {
  return (
    <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--app-muted)]">
          Agentic Commerce
        </p>

        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-[var(--app-text)]">
          Agent Discovery
        </h1>

        <p className="mt-1 text-sm text-[var(--app-muted)]">
          {shopDomain}
        </p>
      </div>

      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        className="inline-flex items-center justify-center gap-2 self-start rounded-lg border border-[var(--app-border)] bg-white px-4 py-2.5 text-sm font-semibold text-[var(--app-text)] shadow-sm hover:bg-[var(--app-panel)] disabled:cursor-not-allowed disabled:opacity-60 md:self-auto"
      >
        <RefreshCw
          className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`}
        />
        Refresh
      </button>
    </header>
  );
}

function SummaryCard({ icon, label, value, description }) {
  return (
    <div className="rounded-2xl border border-[var(--app-border)] bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--app-orange-light)] text-[var(--app-orange)]">
          {icon}
        </div>

        <p className="text-sm font-medium text-[var(--app-muted)]">
          {label}
        </p>
      </div>

      <p className="mt-4 text-3xl font-semibold tracking-tight text-[var(--app-text)]">
        {value}
      </p>

      <p className="mt-1 text-xs leading-5 text-[var(--app-muted)]">
        {description}
      </p>
    </div>
  );
}

function DiscoveryFileCard({
  file,
  info,
  expanded,
  onToggle,
  copied,
  onCopy,
  url,
}) {
  const statusConfig =
    STATUS_CONFIG[info.status] || {
      label: "Unknown",
      tone: "neutral",
      icon: AlertCircle,
    };

  const StatusIcon = statusConfig.icon;

  const customization =
    CUSTOMIZATION_LABELS[info.customization] ||
    info.customization ||
    "Not evaluated";

  const canInspect =
    info.status &&
    !["missing", "unreachable"].includes(info.status);

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--app-border)] bg-white shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-4 p-5 text-left hover:bg-[var(--app-panel)]"
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--app-panel)] text-[var(--app-green)]">
          <FileText className="h-5 w-5" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-[var(--app-text)]">
              {file.label}
            </h3>

            <StatusBadge
              tone={statusConfig.tone}
              icon={<StatusIcon className="h-3.5 w-3.5" />}
            >
              {statusConfig.label}
            </StatusBadge>
          </div>

          <p className="mt-1 text-sm text-[var(--app-muted)]">
            {file.description}
          </p>
        </div>

        {expanded ? (
          <ChevronUp className="h-5 w-5 shrink-0 text-[var(--app-muted)]" />
        ) : (
          <ChevronDown className="h-5 w-5 shrink-0 text-[var(--app-muted)]" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-[var(--app-border)] px-5 pb-5 pt-4">
          <div className="grid gap-4 md:grid-cols-2">
            <InfoItem
              label="Status"
              value={statusConfig.label}
            />

            <InfoItem
              label="Customization"
              value={customization}
            />

            {info.word_count !== undefined && (
              <InfoItem
                label="Word count"
                value={String(info.word_count)}
              />
            )}

            {info.mirrors_agents_md && (
              <InfoItem
                label="Template relationship"
                value="Mirrors agents.md — no dedicated template"
              />
            )}
          </div>

          {info.quality && Object.keys(info.quality).length > 0 && (
            <div className="mt-5">
              <p className="mb-3 text-sm font-semibold text-[var(--app-text)]">
                Content quality checks
              </p>

              <div className="grid gap-2 sm:grid-cols-2">
                {Object.entries(info.quality).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between rounded-lg border border-[var(--app-border)] px-3 py-2.5"
                  >
                    <span className="text-sm text-[var(--app-muted)]">
                      {formatQualityLabel(key)}
                    </span>

                    <span
                      className={
                        value
                          ? "text-sm font-semibold text-[var(--app-green)]"
                          : "text-sm font-semibold text-[var(--app-muted)]"
                      }
                    >
                      {value ? "Present" : "Missing"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {info.mirrors_agents_md && (
            <div className="mt-4 rounded-xl border border-[var(--app-border)] bg-[var(--app-panel)] p-4">
              <p className="text-sm font-medium text-[var(--app-text)]">
                This endpoint mirrors agents.md
              </p>

              <p className="mt-1 text-xs leading-5 text-[var(--app-muted)]">
                The backend detected that this file is substantially similar
                to the canonical agents.md file.
              </p>
            </div>
          )}

          <div className="mt-5 flex flex-wrap gap-2">
            {canInspect && (
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-3.5 py-2 text-sm font-semibold text-white hover:bg-[var(--app-green-dark)]"
              >
                <ExternalLink className="h-4 w-4" />
                Open storefront file
              </a>
            )}

            <button
              type="button"
              onClick={onCopy}
              className="inline-flex items-center gap-2 rounded-lg border border-[var(--app-border)] bg-white px-3.5 py-2 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--app-panel)]"
            >
              <Copy className="h-4 w-4" />
              {copied ? "Copied" : "Copy analysis"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function RecommendationCard({ recommendation }) {
  const priority = recommendation.priority || "medium";

  return (
    <article className="rounded-2xl border border-[var(--app-border)] bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start gap-3">
        <PriorityBadge priority={priority} />

        <h3 className="min-w-0 flex-1 text-base font-semibold text-[var(--app-text)]">
          {recommendation.enrichment}
        </h3>
      </div>

      {recommendation.why_it_matters_for_agents && (
        <p className="mt-4 text-sm leading-6 text-[var(--app-muted)]">
          {recommendation.why_it_matters_for_agents}
        </p>
      )}

      {recommendation.example && (
        <div className="mt-4 rounded-xl border border-[var(--app-border)] bg-[var(--app-panel)] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--app-muted)]">
            Example
          </p>

          <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[var(--app-text)]">
            {recommendation.example}
          </p>
        </div>
      )}
    </article>
  );
}

function StatusBadge({ tone, icon, children }) {
  const styles = {
    success:
      "border-green-200 bg-green-50 text-green-700",
    warning:
      "border-amber-200 bg-amber-50 text-amber-700",
    info:
      "border-blue-200 bg-blue-50 text-blue-700",
    danger:
      "border-red-200 bg-red-50 text-red-700",
    neutral:
      "border-[var(--app-border)] bg-[var(--app-panel)] text-[var(--app-muted)]",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${
        styles[tone] || styles.neutral
      }`}
    >
      {icon}
      {children}
    </span>
  );
}

function PriorityBadge({ priority }) {
  const styles = {
    high: "border-red-200 bg-red-50 text-red-700",
    medium: "border-amber-200 bg-amber-50 text-amber-700",
    low: "border-green-200 bg-green-50 text-green-700",
  };

  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-semibold uppercase ${
        styles[priority] || styles.medium
      }`}
    >
      {priority}
    </span>
  );
}

function InfoItem({ label, value }) {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-panel)] p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--app-muted)]">
        {label}
      </p>

      <p className="mt-1 text-sm font-medium text-[var(--app-text)]">
        {value}
      </p>
    </div>
  );
}

function getFileSummaryText(file, info) {
  const lines = [
    file.label,
    file.description,
    `Status: ${
      STATUS_CONFIG[info.status]?.label || info.status || "Unknown"
    }`,
    `Customization: ${
      CUSTOMIZATION_LABELS[info.customization] ||
      info.customization ||
      "Not evaluated"
    }`,
  ];

  if (info.word_count !== undefined) {
    lines.push(`Word count: ${info.word_count}`);
  }

  if (info.mirrors_agents_md) {
    lines.push(
      "Template relationship: Mirrors agents.md — no dedicated template",
    );
  }

  if (info.quality && Object.keys(info.quality).length > 0) {
    lines.push("");
    lines.push("Content quality:");

    Object.entries(info.quality).forEach(([key, value]) => {
      lines.push(`${formatQualityLabel(key)}: ${value ? "Present" : "Missing"}`);
    });
  }

  return lines.join("\n");
}

function formatQualityLabel(key) {
  return key
    .replaceAll("_", " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDate(value) {
  if (!value) return "Unknown";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

export function ErrorBoundary() {
  return boundary.error();
}

export const headers = (headersArgs) => {
  return boundary.headers(headersArgs);
};