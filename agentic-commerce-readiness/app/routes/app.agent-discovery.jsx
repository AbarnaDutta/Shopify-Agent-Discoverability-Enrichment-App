// app/routes/app.agent-discovery.jsx

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useRouteLoaderData } from "react-router";
import {
  Search,
  CheckCircle2,
  AlertCircle,
  XCircle,
  ExternalLink,
  FileText,
  RefreshCw,
  Sparkles,
  Bot,
  ShoppingBag,
  Copy,
  Check,
  Settings2,
  ArrowRight,
  X,
  Globe,
} from "lucide-react";

const BACKEND_URL = "https://geo.properoapps.in/api";

/* -------------------------------------------------------------------------- */
/* Discovery files                                                            */
/* -------------------------------------------------------------------------- */

const DISCOVERY_FILES = [
  {
    key: "agents_md",
    name: "agents.md",
    title: "Agent Instructions",
    description:
      "Provides instructions and context for AI agents interacting with your store.",
    path: "/.well-known/agents.md",
    icon: Bot,
  },
  {
    key: "llms_txt",
    name: "llms.txt",
    title: "Store Information",
    description:
      "Provides a concise machine-readable overview of your store.",
    path: "/llms.txt",
    icon: FileText,
  },
  {
    key: "llms_full_txt",
    name: "llms-full.txt",
    title: "Detailed Store Information",
    description:
      "Provides detailed machine-readable store and product information.",
    path: "/llms-full.txt",
    icon: FileText,
  },
  {
    key: "ucp_manifest",
    name: "UCP",
    title: "Universal Commerce Protocol (UCP)",
    description:
      "Commerce flow readiness for agent-assisted shopping.",
    path: "/.well-known/ucp.json",
    icon: ShoppingBag,
  },
];

/* -------------------------------------------------------------------------- */
/* Status helpers                                                             */
/* -------------------------------------------------------------------------- */

function getStatus(file) {
  const status = file?.status;

  if (status === "served_custom") {
    return {
      label: "Ready",
      description:
        "Available and customized for this store.",
      type: "success",
    };
  }

  if (status === "served_default") {
    return {
      label: "Needs configuration",
      description:
        "Available but still using the default configuration.",
      type: "warning",
    };
  }

  if (status === "redirects") {
    return {
      label: "Redirects",
      description:
        "Redirects to another discovery resource.",
      type: "warning",
    };
  }

  if (status === "missing") {
    return {
      label: "Missing",
      description:
        "Could not be found on the storefront.",
      type: "danger",
    };
  }

  if (status === "unreachable") {
    return {
      label: "Unavailable",
      description:
        "The storefront resource could not be reached.",
      type: "danger",
    };
  }

  return {
    label: "Not configured",
    description:
      "No discovery information is available yet.",
    type: "neutral",
  };
}

function statusClasses(type) {
  if (type === "success") {
    return "border-[#b7dfd3] bg-[#edf8f4] text-[#067a5f]";
  }

  if (type === "warning") {
    return "border-[#f2d39c] bg-[#fff8ea] text-[#9a6700]";
  }

  if (type === "danger") {
    return "border-[#f0c3be] bg-[#fff2f0] text-[#c43222]";
  }

  return "border-[#dfe3e1] bg-[#f4f5f4] text-[#5f6f85]";
}

function getRecommendationPriority(priority) {
  if (priority === "high") {
    return {
      label: "High",
      classes:
        "border-[#f0c3be] bg-[#fff2f0] text-[#c43222]",
    };
  }

  if (priority === "low") {
    return {
      label: "Low",
      classes:
        "border-[#d9e4df] bg-[#f1f7f4] text-[#52706a]",
    };
  }

  return {
    label: "Medium",
    classes:
      "border-[#f2d39c] bg-[#fff8ea] text-[#9a6700]",
  };
}

function getStoreUrl(shopDomain, path) {
  if (!shopDomain || !path) return "#";

  return `https://${shopDomain}${path}`;
}

function formatDate(value) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}

/* -------------------------------------------------------------------------- */
/* Backend content helpers                                                    */
/* -------------------------------------------------------------------------- */

function getFileContent(file) {
  if (!file) return "";

  const candidates = [
    file.content,
    file.preview,
    file.preview_content,
    file.content_preview,
    file.generated_content,
    file.body,
    file.text,
    file.markdown,
  ];

  for (const value of candidates) {
    if (
      typeof value === "string" &&
      value.trim()
    ) {
      return value;
    }
  }

  return "";
}

function getFileDisplayUrl(
  shopDomain,
  definition,
  file
) {
  return (
    file?.url ||
    file?.live_url ||
    file?.public_url ||
    getStoreUrl(
      shopDomain,
      definition.path
    )
  );
}

function getCustomizationText(file) {
  if (!file) {
    return "No discovery information is available.";
  }

  if (
    file.customization ===
    "heavily_customized"
  ) {
    return "Heavily customized with store-specific information.";
  }

  if (
    file.customization ===
    "partially_customized"
  ) {
    return "Partially customized with store-specific information.";
  }

  if (
    file.customization ===
    "default_skeleton"
  ) {
    return "Using the default discovery configuration.";
  }

  if (file.mirrors_agents_md) {
    return "Uses the agents.md content for this discovery surface.";
  }

  return "";
}

/* -------------------------------------------------------------------------- */
/* Discovery score                                                            */
/* -------------------------------------------------------------------------- */

function calculateDiscoveryScore(files) {
  let total = 0;

  DISCOVERY_FILES.forEach((definition) => {
    const status = files?.[definition.key]?.status;

    if (status === "served_custom") {
      total += 100;
    } else if (status === "served_default") {
      total += 50;
    } else if (status === "redirects") {
      total += 40;
    } else {
      total += 0;
    }
  });

  return Math.round(
    total / DISCOVERY_FILES.length
  );
}

function getDiscoveryScore(
  report,
  agentDiscovery,
  files
) {
  const possibleValues = [
    agentDiscovery?.score,
    agentDiscovery?.discovery_score,
    agentDiscovery?.overall_score,
    report?.agent_discovery_score,
    report?.discovery_score,
  ];

  for (const value of possibleValues) {
    const numeric = Number(value);

    if (
      Number.isFinite(numeric) &&
      numeric >= 0 &&
      numeric <= 100
    ) {
      return Math.round(numeric);
    }
  }

  return calculateDiscoveryScore(files);
}

/* -------------------------------------------------------------------------- */
/* Main component                                                             */
/* -------------------------------------------------------------------------- */

export default function AgentDiscovery() {
  const navigate = useNavigate();

  const { shopDomain } =
    useRouteLoaderData("routes/app");

  const [report, setReport] =
    useState(null);

  const [loading, setLoading] =
    useState(true);

  const [refreshing, setRefreshing] =
    useState(false);

  const [error, setError] =
    useState(null);

  const [search, setSearch] =
    useState("");

  const [previewFile, setPreviewFile] =
    useState(null);

  const [copied, setCopied] =
    useState(false);

  const [configureOpen, setConfigureOpen] =
    useState(false);

  /* ------------------------------------------------------------------------ */
  /* Load latest audit                                                        */
  /* ------------------------------------------------------------------------ */

  useEffect(() => {
    if (!shopDomain) return;

    let cancelled = false;

    const loadAudit = async () => {
      try {
        setLoading(true);
        setError(null);

        const response = await fetch(
          `${BACKEND_URL}/audits/latest?shop_domain=${encodeURIComponent(
            shopDomain
          )}`
        );

        if (response.status === 404) {
          if (!cancelled) {
            setReport(null);
            setLoading(false);
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

        if (!cancelled) {
          setReport(data);
          setLoading(false);
        }
      } catch (err) {
        console.error(
          "Failed to load Agent Discovery:",
          err
        );

        if (!cancelled) {
          setError(
            "Unable to load Agent Discovery data from the backend."
          );

          setLoading(false);
        }
      }
    };

    loadAudit();

    return () => {
      cancelled = true;
    };
  }, [shopDomain]);

  /* ------------------------------------------------------------------------ */
  /* Refresh                                                                  */
  /* ------------------------------------------------------------------------ */

  const refresh = async () => {
    if (!shopDomain) return;

    try {
      setRefreshing(true);
      setError(null);

      const response = await fetch(
        `${BACKEND_URL}/audits/latest?shop_domain=${encodeURIComponent(
          shopDomain
        )}`
      );

      if (response.status === 404) {
        setReport(null);
        return;
      }

      if (!response.ok) {
        throw new Error(
          `Failed to refresh audit: ${response.status}`
        );
      }

      const data =
        await response.json();

      setReport(data);
    } catch (err) {
      console.error(
        "Failed to refresh Agent Discovery:",
        err
      );

      setError(
        "Unable to refresh Agent Discovery data."
      );
    } finally {
      setRefreshing(false);
    }
  };

  /* ------------------------------------------------------------------------ */
  /* Real backend data                                                        */
  /* ------------------------------------------------------------------------ */

  const agentDiscovery =
    report?.agent_discovery || null;

  const files =
    agentDiscovery?.files || {};

  const recommendations =
    Array.isArray(
      agentDiscovery?.recommendations
    )
      ? agentDiscovery.recommendations
      : [];

  /* ------------------------------------------------------------------------ */
  /* Summary                                                                  */
  /* ------------------------------------------------------------------------ */

  const summary = useMemo(() => {
    let available = 0;
    let ready = 0;
    let attention = 0;

    DISCOVERY_FILES.forEach(
      (definition) => {
        const status =
          files?.[definition.key]?.status;

        if (
          [
            "served_custom",
            "served_default",
            "redirects",
          ].includes(status)
        ) {
          available += 1;
        }

        if (status === "served_custom") {
          ready += 1;
        }

        if (
          [
            "missing",
            "unreachable",
            "served_default",
          ].includes(status)
        ) {
          attention += 1;
        }
      }
    );

    return {
      available,
      ready,
      attention,
      total: DISCOVERY_FILES.length,
    };
  }, [files]);

  const discoveryScore =
    getDiscoveryScore(
      report,
      agentDiscovery,
      files
    );

  /* ------------------------------------------------------------------------ */
  /* Search                                                                   */
  /* ------------------------------------------------------------------------ */

  const filteredFiles = useMemo(() => {
    const query =
      search.trim().toLowerCase();

    if (!query) {
      return DISCOVERY_FILES;
    }

    return DISCOVERY_FILES.filter(
      (definition) => {
        const file =
          files?.[definition.key];

        const searchable = [
          definition.name,
          definition.title,
          definition.description,
          file?.status,
          file?.customization,
          file?.summary,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();

        return searchable.includes(query);
      }
    );
  }, [search, files]);

  /* ------------------------------------------------------------------------ */
  /* Copy                                                                     */
  /* ------------------------------------------------------------------------ */

  const copyDiscoverySummary =
    async () => {
      if (!agentDiscovery) return;

      const text = [
        "Agent Discovery",
        `Store: ${shopDomain}`,
        `Score: ${discoveryScore}/100`,
        "",
        agentDiscovery.summary || "",
        "",
        ...DISCOVERY_FILES.map(
          (definition) => {
            const file =
              files?.[definition.key];

            const status =
              getStatus(file);

            return `${definition.name}: ${status.label}`;
          }
        ),
      ].join("\n");

      try {
        await navigator.clipboard.writeText(
          text
        );

        setCopied(true);

        setTimeout(() => {
          setCopied(false);
        }, 1500);
      } catch (err) {
        console.error(
          "Failed to copy Agent Discovery summary:",
          err
        );
      }
    };

  /* ------------------------------------------------------------------------ */
  /* Loading                                                                  */
  /* ------------------------------------------------------------------------ */

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] p-8">
        <div className="mx-auto max-w-[1500px]">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-[var(--app-text)]">
                Agent Discovery
              </h1>

              <p className="mt-1 text-sm text-[var(--app-muted)]">
                Make your store understandable and discoverable to AI agents.
              </p>
            </div>
          </div>

          <div className="mt-8 rounded-xl border border-[var(--app-border)] bg-white p-16 text-center shadow-sm">
            <RefreshCw className="mx-auto h-7 w-7 animate-spin text-[var(--app-green)]" />

            <p className="mt-4 text-sm font-semibold text-[var(--app-text)]">
              Loading Agent Discovery
            </p>

            <p className="mt-1 text-xs text-[var(--app-muted)]">
              Fetching the latest audit results for this store.
            </p>
          </div>
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /* Error                                                                    */
  /* ------------------------------------------------------------------------ */

  if (error) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] p-8">
        <div className="mx-auto max-w-[1500px]">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-[var(--app-text)]">
                Agent Discovery
              </h1>

              <p className="mt-1 text-sm text-[var(--app-muted)]">
                Make your store understandable and discoverable to AI agents.
              </p>
            </div>
          </div>

          <div className="mt-8 rounded-xl border border-[#f0c3be] bg-white p-12 text-center shadow-sm">
            <XCircle className="mx-auto h-10 w-10 text-[#c43222]" />

            <h2 className="mt-4 text-base font-bold text-[var(--app-text)]">
              Unable to load Agent Discovery
            </h2>

            <p className="mt-2 text-sm text-[var(--app-muted)]">
              {error}
            </p>

            <button
              type="button"
              onClick={refresh}
              className="mt-5 inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--app-green-dark)]"
            >
              <RefreshCw className="h-4 w-4" />
              Try again
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /* No audit                                                                 */
  /* ------------------------------------------------------------------------ */

  if (!report || !agentDiscovery) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] p-8">
        <div className="mx-auto max-w-[1500px]">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h1 className="text-2xl font-bold text-[var(--app-text)]">
                Agent Discovery
              </h1>

              <p className="mt-1 text-base text-[var(--app-muted)]">
                Make your store understandable and discoverable to AI agents.
              </p>
            </div>

            <button
              type="button"
              onClick={() => navigate("/app")}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-[var(--app-green-dark)]"
            >
              Run Audit
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-8 rounded-xl border border-[var(--app-border)] bg-white p-14 text-center shadow-sm">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--app-orange-light)]">
              <Sparkles className="h-7 w-7 text-[var(--app-orange)]" />
            </div>

            <h2 className="mt-5 text-lg font-bold text-[var(--app-text)]">
              Run an audit to discover your store
            </h2>

            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[var(--app-muted)]">
              Agent Discovery results are generated from your latest store
              audit. Run an audit to see the real discovery status for this
              Shopify store.
            </p>
          </div>
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /* Main page                                                                */
  /* ------------------------------------------------------------------------ */

  return (
    <>
      <div className="min-h-screen bg-[var(--app-bg)] p-8">
        <div className="mx-auto max-w-[1500px]">

          {/* ---------------------------------------------------------------- */}
          {/* Header                                                           */}
          {/* ---------------------------------------------------------------- */}

          <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h1 className="text-[26px] font-bold tracking-tight text-[var(--app-text)]">
                Agent Discovery
              </h1>

              <p className="mt-1 text-[16px] text-[var(--app-muted)]">
                Make your store understandable and discoverable to AI agents.
              </p>
            </div>

            <button
              type="button"
              onClick={() =>
                setConfigureOpen(true)
              }
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-[var(--app-green-dark)]"
            >
              <Settings2 className="h-4 w-4" />
              Configure Agent Discovery
            </button>
          </div>

          {/* ---------------------------------------------------------------- */}
          {/* Discovery cards                                                  */}
          {/* ---------------------------------------------------------------- */}

          <section className="mt-8 grid grid-cols-1 gap-7 lg:grid-cols-2">
            {filteredFiles.map(
              (definition) => {
                const file =
                  files?.[definition.key] ||
                  {};

                const status =
                  getStatus(file);

                const Icon =
                  definition.icon;

                const displayUrl =
                  getFileDisplayUrl(
                    shopDomain,
                    definition,
                    file
                  );

                return (
                  <DiscoveryCard
                    key={definition.key}
                    definition={definition}
                    file={file}
                    status={status}
                    Icon={Icon}
                    displayUrl={displayUrl}
                    onPreview={() =>
                      setPreviewFile({
                        definition,
                        file,
                        status,
                        displayUrl,
                      })
                    }
                    onConfigure={() =>
                      setConfigureOpen(true)
                    }
                  />
                );
              }
            )}
          </section>

          {/* ---------------------------------------------------------------- */}
          {/* Score                                                            */}
          {/* ---------------------------------------------------------------- */}

          <section className="mt-8 rounded-xl border border-[var(--app-border)] bg-white p-7 shadow-sm">
            <div className="flex flex-col gap-7 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0 flex-1">
                <p className="text-xs font-semibold uppercase tracking-wider text-[var(--app-muted)]">
                  Discovery Engine
                </p>

                <h2 className="mt-2 text-[24px] font-bold tracking-tight text-[var(--app-text)]">
                  Agent Discovery Score{" "}
                  <span className="font-extrabold">
                    {discoveryScore} / 100
                  </span>
                </h2>

                <p className="mt-1 max-w-[850px] text-sm leading-6 text-[var(--app-muted)]">
                  {agentDiscovery.summary ||
                    "Your latest audit contains Agent Discovery results for this store."}
                </p>
              </div>

              <div className="w-full lg:w-[320px]">
                <div className="h-3 overflow-hidden rounded-full bg-[#EEF0F1]">
                  <div
                    className="h-full rounded-full bg-[#FFB100] transition-all"
                    style={{
                      width: `${discoveryScore}%`,
                    }}
                  />
                </div>
              </div>
            </div>

            <div className="mt-7 border-t border-[var(--app-border)] pt-5">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                {DISCOVERY_FILES.map(
                  (definition) => {
                    const file =
                      files?.[
                        definition.key
                      ] || {};

                    const status =
                      getStatus(file);

                    const isReady =
                      status.type ===
                      "success";

                    const isWarning =
                      status.type ===
                      "warning";

                    return (
                      <button
                        key={
                          definition.key
                        }
                        type="button"
                        onClick={() =>
                          setPreviewFile({
                            definition,
                            file,
                            status,
                            displayUrl:
                              getFileDisplayUrl(
                                shopDomain,
                                definition,
                                file
                              ),
                          })
                        }
                        className="flex items-center justify-between gap-3 rounded-lg border border-[var(--app-border)] bg-[#F8F9FA] px-4 py-4 text-left transition hover:border-[#cdd4d1] hover:bg-white"
                      >
                        <span className="flex min-w-0 items-center gap-3">
                          <span
                            className={`h-2.5 w-2.5 shrink-0 rounded-full ${
                              isReady
                                ? "bg-[#008060]"
                                : isWarning
                                  ? "bg-[#FFB100]"
                                  : "bg-[#D72C0D]"
                            }`}
                          />

                          <span className="truncate text-sm font-semibold text-[var(--app-text)]">
                            {definition.name ===
                            "UCP"
                              ? "UCP Protocol"
                              : definition.name}
                          </span>
                        </span>

                        <span
                          className={`shrink-0 text-xs font-bold ${
                            isReady
                              ? "text-[#008060]"
                              : isWarning
                                ? "text-[#9A6700]"
                                : "text-[#D72C0D]"
                          }`}
                        >
                          {status.label}
                        </span>
                      </button>
                    );
                  }
                )}
              </div>
            </div>

            <div className="mt-7 flex flex-wrap items-center justify-between gap-4">
              <div className="flex flex-wrap items-center gap-5 text-sm text-[var(--app-muted)]">
                <span>
                  <strong className="text-[var(--app-text)]">
                    {summary.available}
                  </strong>{" "}
                  / {summary.total} endpoints available
                </span>

                <span>
                  <strong className="text-[var(--app-text)]">
                    {summary.ready}
                  </strong>{" "}
                  customized
                </span>

                <span>
                  <strong className="text-[var(--app-text)]">
                    {summary.attention}
                  </strong>{" "}
                  need attention
                </span>
              </div>

              <button
                type="button"
                onClick={() =>
                  setConfigureOpen(true)
                }
                className="inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-3 text-sm font-bold text-white shadow-sm hover:bg-[var(--app-green-dark)]"
              >
                Configure Agent Discovery
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
          </section>

          {/* ---------------------------------------------------------------- */}
          {/* Recommendations                                                  */}
          {/* ---------------------------------------------------------------- */}

          {recommendations.length > 0 && (
            <section className="mt-8 rounded-xl border border-[var(--app-border)] bg-white shadow-sm">
              <div className="border-b border-[var(--app-border)] px-6 py-5">
                <h2 className="text-base font-bold text-[var(--app-text)]">
                  Shopify-Aligned Recommendations
                </h2>

                <p className="mt-1 text-sm text-[var(--app-muted)]">
                  Recommendations generated from the latest audit for{" "}
                  {shopDomain}.
                </p>
              </div>

              <div className="divide-y divide-[var(--app-border)]">
                {recommendations.map(
                  (recommendation, index) => {
                    const priority =
                      getRecommendationPriority(
                        recommendation.priority
                      );

                    return (
                      <div
                        key={`${recommendation.enrichment || "recommendation"}-${index}`}
                        className="p-6"
                      >
                        <div className="flex items-start gap-4">
                          <div className="mt-1 flex h-3 w-3 shrink-0 rounded-full bg-[#FFB100]" />

                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-start justify-between gap-3">
                              <h3 className="text-base font-bold text-[var(--app-text)]">
                                {recommendation.enrichment ||
                                  "Agent Discovery improvement"}
                              </h3>

                              <span
                                className={`rounded-full border px-3 py-1 text-xs font-bold ${priority.classes}`}
                              >
                                {priority.label}
                              </span>
                            </div>

                            {recommendation.why_it_matters_for_agents && (
                              <p className="mt-3 text-sm leading-6 text-[var(--app-muted)]">
                                {
                                  recommendation.why_it_matters_for_agents
                                }
                              </p>
                            )}

                            {recommendation.example && (
                              <div className="mt-4 rounded-lg border-l-2 border-[#cfd9e2] bg-[#FAF9F7] px-4 py-3">
                                <p className="font-mono text-xs leading-5 text-[#425466]">
                                  <strong>
                                    Example:
                                  </strong>{" "}
                                  {
                                    recommendation.example
                                  }
                                </p>
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  }
                )}
              </div>
            </section>
          )}

          {/* ---------------------------------------------------------------- */}
          {/* Footer                                                           */}
          {/* ---------------------------------------------------------------- */}

          <div className="py-8 text-center text-xs text-[var(--app-muted)]">
            Agent Discovery is based on the latest completed audit for{" "}
            <span className="font-semibold">
              {shopDomain}
            </span>
            .
            {report?.created_at
              ? ` Last audited ${formatDate(
                  report.created_at
                )}.`
              : ""}
          </div>
        </div>
      </div>

      {/* -------------------------------------------------------------------- */}
      {/* Preview modal                                                        */}
      {/* -------------------------------------------------------------------- */}

      {previewFile && (
        <DiscoveryPreviewModal
          shopDomain={shopDomain}
          item={previewFile}
          onClose={() =>
            setPreviewFile(null)
          }
          onConfigure={() => {
            setPreviewFile(null);
            setConfigureOpen(true);
          }}
        />
      )}

      {/* -------------------------------------------------------------------- */}
      {/* Configure modal                                                      */}
      {/* -------------------------------------------------------------------- */}

      {configureOpen && (
        <ConfigureAgentDiscoveryModal
          shopDomain={shopDomain}
          files={files}
          recommendations={recommendations}
          onClose={() =>
            setConfigureOpen(false)
          }
          onPreview={(item) => {
            setConfigureOpen(false);
            setPreviewFile(item);
          }}
        />
      )}
    </>
  );
}

/* ========================================================================== */
/* Discovery Card                                                             */
/* ========================================================================== */

function DiscoveryCard({
  definition,
  file,
  status,
  Icon,
  displayUrl,
  onPreview,
  onConfigure,
}) {
  const isUcp =
    definition.key === "ucp_manifest";

  const actionLabel = isUcp
    ? status.type === "success"
      ? "Configure"
      : "Configure"
    : status.type === "success"
      ? "View"
      : "Generate";

  return (
    <div className="rounded-2xl border border-[#DCDCDC] bg-white p-7 shadow-[0_2px_6px_rgba(0,0,0,0.08)]">
      <div className="flex items-start justify-between gap-5">
        <div className="flex min-w-0 items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#F1F6F4] text-[var(--app-green)]">
            <Icon className="h-5 w-5" />
          </div>

          <div className="min-w-0">
            <h3 className="text-[17px] font-bold text-[var(--app-text)]">
              {definition.name}
            </h3>

            <p className="mt-1 text-sm text-[var(--app-muted)]">
              {definition.name === "UCP"
                ? "Universal Commerce Protocol (UCP)"
                : definition.name}
            </p>
          </div>
        </div>

        <span
          className={`shrink-0 rounded-md border px-3 py-1 text-xs font-semibold ${statusClasses(
            status.type
          )}`}
        >
          {status.label}
        </span>
      </div>

      <p className="mt-6 min-h-[44px] text-sm leading-6 text-[var(--app-muted)]">
        {definition.description}
      </p>

      <div className="mt-5 flex items-center gap-2 rounded-md border border-[#DCDCDC] bg-[#F7F7F7] px-3 py-3">
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-[#53657A]">
          {displayUrl}
        </span>

        <a
          href={displayUrl}
          target="_blank"
          rel="noreferrer"
          onClick={(event) =>
            event.stopPropagation()
          }
          className="shrink-0 text-[#6D7175] hover:text-[var(--app-green)]"
          aria-label={`Open ${definition.name}`}
        >
          <ExternalLink className="h-4 w-4" />
        </a>
      </div>

      <div className="mt-6 flex items-center justify-between border-t border-[#DCDCDC] pt-5">
        <button
          type="button"
          onClick={onPreview}
          className="text-sm font-medium text-[var(--app-text)] hover:text-[var(--app-green)]"
        >
          View Preview
        </button>

        <button
          type="button"
          onClick={onConfigure}
          className="rounded-md bg-[var(--app-green)] px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-[var(--app-green-dark)]"
        >
          {actionLabel}
        </button>
      </div>
    </div>
  );
}

/* ========================================================================== */
/* Preview Modal                                                              */
/* ========================================================================== */

function DiscoveryPreviewModal({
  shopDomain,
  item,
  onClose,
  onConfigure,
}) {
  const {
    definition,
    file,
    status,
    displayUrl,
  } = item;

  const content =
    getFileContent(file);

  const customization =
    getCustomizationText(file);

  const [copied, setCopied] =
    useState(false);

  const copyContent = async () => {
    if (!content) return;

    try {
      await navigator.clipboard.writeText(
        content
      );

      setCopied(true);

      setTimeout(() => {
        setCopied(false);
      }, 1500);
    } catch (error) {
      console.error(
        "Failed to copy discovery content:",
        error
      );
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]">
      <div className="flex max-h-[90vh] w-full max-w-[840px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#E1E3E5] px-6 py-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#F1F6F4] text-[var(--app-green)]">
              <FileText className="h-5 w-5" />
            </div>

            <div className="min-w-0">
              <h2 className="text-base font-bold text-[var(--app-text)]">
                {definition.name}
              </h2>

              <p className="mt-1 truncate font-mono text-xs text-[var(--app-muted)]">
                {displayUrl}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-[#6D7175] hover:bg-[#F5F5F5] hover:text-[#202223]"
            aria-label="Close preview"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-6">
          <p className="text-sm leading-6 text-[var(--app-muted)]">
            {definition.description}
          </p>

          <div className="mt-5 flex flex-wrap gap-2">
            <span
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusClasses(
                status.type
              )}`}
            >
              {status.label}
            </span>

            {customization && (
              <span className="rounded-full border border-[#DCDCDC] bg-[#F7F7F7] px-3 py-1 text-xs font-medium text-[#53657A]">
                {customization}
              </span>
            )}
          </div>

          {content ? (
            <div className="mt-6 overflow-hidden rounded-xl bg-[#202223]">
              <div className="flex items-center justify-between border-b border-[#383A3C] px-4 py-3">
                <span className="font-mono text-xs text-[#B7C0C8]">
                  {definition.name}
                </span>

                <button
                  type="button"
                  onClick={copyContent}
                  className="inline-flex items-center gap-2 rounded-md border border-[#4A4D50] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[#303336]"
                >
                  {copied ? (
                    <Check className="h-3.5 w-3.5" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}

                  {copied
                    ? "Copied"
                    : "Copy Spec"}
                </button>
              </div>

              <pre className="max-h-[430px] overflow-auto p-5 font-mono text-xs leading-5 text-[#B9E8D8]">
                {content}
              </pre>
            </div>
          ) : (
            <div className="mt-6 rounded-xl border border-[#DCDCDC] bg-[#F8F8F7] p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-[#9A6700]" />

                <div>
                  <p className="text-sm font-bold text-[var(--app-text)]">
                    Preview content is not included in this audit response.
                  </p>

                  <p className="mt-1 text-sm leading-6 text-[var(--app-muted)]">
                    The backend returned the discovery status for this store,
                    but did not return the generated file contents. The live
                    discovery resource can still be opened below.
                  </p>
                </div>
              </div>
            </div>
          )}

          <div className="mt-5 rounded-lg border border-[#b7dfd3] bg-[#edf8f4] px-4 py-3">
            <div className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#067a5f]" />

              <p className="text-xs leading-5 text-[#52706a]">
                This information is loaded for{" "}
                <strong>{shopDomain}</strong> from the latest completed
                audit.
              </p>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E1E3E5] bg-[#FAFAFA] px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="px-2 py-2 text-sm font-medium text-[#6D7175] hover:text-[#202223]"
          >
            Close
          </button>

          <div className="flex flex-wrap gap-2">
            <a
              href={displayUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg border border-[#DCDCDC] bg-white px-4 py-2.5 text-sm font-semibold text-[var(--app-text)] hover:bg-[#F5F5F5]"
            >
              <ExternalLink className="h-4 w-4" />
              Open live file
            </a>

            <button
              type="button"
              onClick={onConfigure}
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-2.5 text-sm font-bold text-white hover:bg-[var(--app-green-dark)]"
            >
              Configure
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ========================================================================== */
/* Configure Modal                                                            */
/* ========================================================================== */

function ConfigureAgentDiscoveryModal({
  shopDomain,
  files,
  recommendations,
  onClose,
  onPreview,
}) {
  const [selectedKey, setSelectedKey] =
    useState("agents_md");

  const selectedDefinition =
    DISCOVERY_FILES.find(
      (definition) =>
        definition.key === selectedKey
    ) || DISCOVERY_FILES[0];

  const selectedFile =
    files?.[selectedDefinition.key] ||
    {};

  const selectedStatus =
    getStatus(selectedFile);

  const selectedContent =
    getFileContent(selectedFile);

  const displayUrl =
    getFileDisplayUrl(
      shopDomain,
      selectedDefinition,
      selectedFile
    );

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]">
      <div className="flex max-h-[92vh] w-full max-w-[900px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">

        {/* Header */}
        <div className="flex items-center justify-between border-b border-[#E1E3E5] px-6 py-5">
          <div>
            <h2 className="text-lg font-bold text-[var(--app-text)]">
              Configure Agent Discovery
            </h2>

            <p className="mt-1 text-sm text-[var(--app-muted)]">
              Configure discovery resources for{" "}
              <span className="font-semibold text-[var(--app-text)]">
                {shopDomain}
              </span>
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-[#6D7175] hover:bg-[#F5F5F5] hover:text-[#202223]"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* File selector */}
        <div className="border-b border-[#E1E3E5] px-6 py-4">
          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {DISCOVERY_FILES.map(
              (definition) => {
                const file =
                  files?.[
                    definition.key
                  ] || {};

                const status =
                  getStatus(file);

                const selected =
                  selectedKey ===
                  definition.key;

                return (
                  <button
                    key={definition.key}
                    type="button"
                    onClick={() =>
                      setSelectedKey(
                        definition.key
                      )
                    }
                    className={`rounded-lg border px-3 py-3 text-left transition ${
                      selected
                        ? "border-[var(--app-green)] bg-[#edf8f4]"
                        : "border-[#DCDCDC] bg-white hover:bg-[#F7F7F7]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-sm font-bold text-[var(--app-text)]">
                        {definition.name}
                      </span>

                      <span
                        className={`h-2 w-2 shrink-0 rounded-full ${
                          status.type ===
                          "success"
                            ? "bg-[#008060]"
                            : status.type ===
                                "warning"
                              ? "bg-[#FFB100]"
                              : "bg-[#D72C0D]"
                        }`}
                      />
                    </div>

                    <div className="mt-1 text-[11px] text-[var(--app-muted)]">
                      {status.label}
                    </div>
                  </button>
                );
              }
            )}
          </div>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h3 className="text-lg font-bold text-[var(--app-text)]">
                {selectedDefinition.name}
              </h3>

              <p className="mt-1 text-sm text-[var(--app-muted)]">
                {selectedDefinition.description}
              </p>
            </div>

            <span
              className={`shrink-0 rounded-full border px-3 py-1 text-xs font-semibold ${statusClasses(
                selectedStatus.type
              )}`}
            >
              {selectedStatus.label}
            </span>
          </div>

          <div className="mt-5 rounded-lg border border-[#DCDCDC] bg-[#F7F7F7] px-4 py-3">
            <div className="flex items-center gap-2">
              <Globe className="h-4 w-4 shrink-0 text-[var(--app-muted)]" />

              <span className="min-w-0 flex-1 truncate font-mono text-xs text-[#53657A]">
                {displayUrl}
              </span>

              <a
                href={displayUrl}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 text-[#6D7175] hover:text-[var(--app-green)]"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>
          </div>

          {selectedContent ? (
            <div className="mt-5 overflow-hidden rounded-xl bg-[#202223]">
              <div className="flex items-center justify-between border-b border-[#383A3C] px-4 py-3">
                <span className="font-mono text-xs text-[#B7C0C8]">
                  Generated discovery content
                </span>

                <button
                  type="button"
                  onClick={() =>
                    onPreview({
                      definition:
                        selectedDefinition,
                      file: selectedFile,
                      status:
                        selectedStatus,
                      displayUrl,
                    })
                  }
                  className="text-xs font-semibold text-white hover:underline"
                >
                  View full preview
                </button>
              </div>

              <pre className="max-h-[360px] overflow-auto p-5 font-mono text-xs leading-5 text-[#B9E8D8]">
                {selectedContent}
              </pre>
            </div>
          ) : (
            <div className="mt-5 rounded-xl border border-[#DCDCDC] bg-[#FAFAFA] p-5">
              <p className="text-sm font-semibold text-[var(--app-text)]">
                {getCustomizationText(
                  selectedFile
                ) ||
                  "This discovery resource has not returned generated content yet."}
              </p>

              <p className="mt-2 text-xs leading-5 text-[var(--app-muted)]">
                The configuration status and recommendation data shown here
                come from the latest audit for this store.
              </p>
            </div>
          )}

          {/* Recommendations relevant to selected resource */}
          {recommendations.length > 0 && (
            <div className="mt-6">
              <h3 className="text-sm font-bold text-[var(--app-text)]">
                Recommended configuration
              </h3>

              <div className="mt-3 space-y-3">
                {recommendations
                  .filter(
                    (recommendation) => {
                      const text = [
                        recommendation.enrichment,
                        recommendation.example,
                        recommendation.why_it_matters_for_agents,
                      ]
                        .filter(Boolean)
                        .join(" ")
                        .toLowerCase();

                      if (
                        selectedKey ===
                        "agents_md"
                      ) {
                        return (
                          text.includes(
                            "agent"
                          ) ||
                          text.includes(
                            "brand"
                          ) ||
                          text.includes(
                            "policy"
                          ) ||
                          text.includes(
                            "faq"
                          )
                        );
                      }

                      if (
                        selectedKey ===
                        "llms_txt"
                      ) {
                        return (
                          text.includes(
                            "store"
                          ) ||
                          text.includes(
                            "brand"
                          ) ||
                          text.includes(
                            "product"
                          )
                        );
                      }

                      if (
                        selectedKey ===
                        "llms_full_txt"
                      ) {
                        return (
                          text.includes(
                            "product"
                          ) ||
                          text.includes(
                            "catalog"
                          ) ||
                          text.includes(
                            "information"
                          )
                        );
                      }

                      return (
                        text.includes("ucp") ||
                        text.includes(
                          "commerce"
                        ) ||
                        text.includes(
                          "checkout"
                        )
                      );
                    }
                  )
                  .slice(0, 5)
                  .map(
                    (
                      recommendation,
                      index
                    ) => {
                      const priority =
                        getRecommendationPriority(
                          recommendation.priority
                        );

                      return (
                        <div
                          key={`${selectedKey}-${index}`}
                          className="rounded-xl border border-[#E1E3E5] bg-white p-4"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <h4 className="text-sm font-bold text-[var(--app-text)]">
                              {recommendation.enrichment ||
                                "Improve discovery configuration"}
                            </h4>

                            <span
                              className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-bold ${priority.classes}`}
                            >
                              {priority.label}
                            </span>
                          </div>

                          {recommendation.why_it_matters_for_agents && (
                            <p className="mt-2 text-xs leading-5 text-[var(--app-muted)]">
                              {
                                recommendation.why_it_matters_for_agents
                              }
                            </p>
                          )}

                          {recommendation.example && (
                            <div className="mt-3 rounded-lg bg-[#FAF9F7] px-3 py-2">
                              <p className="font-mono text-[11px] leading-5 text-[#53657A]">
                                {
                                  recommendation.example
                                }
                              </p>
                            </div>
                          )}
                        </div>
                      );
                    }
                  )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E1E3E5] bg-[#FAFAFA] px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="px-2 py-2 text-sm font-medium text-[#6D7175] hover:text-[#202223]"
          >
            Close
          </button>

          <div className="flex flex-wrap gap-2">
            <a
              href={displayUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-lg border border-[#DCDCDC] bg-white px-4 py-2.5 text-sm font-semibold text-[var(--app-text)] hover:bg-[#F5F5F5]"
            >
              <ExternalLink className="h-4 w-4" />
              Open storefront file
            </a>

            <button
              type="button"
              onClick={() =>
                onPreview({
                  definition:
                    selectedDefinition,
                  file: selectedFile,
                  status:
                    selectedStatus,
                  displayUrl,
                })
              }
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-2.5 text-sm font-bold text-white hover:bg-[var(--app-green-dark)]"
            >
              View Preview
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}