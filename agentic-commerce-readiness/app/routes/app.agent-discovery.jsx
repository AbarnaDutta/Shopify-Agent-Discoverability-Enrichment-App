// agentic-commerce-readiness/app/routes/app.agent-discovery.jsx

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useRouteLoaderData } from "react-router";
import {
  Search,
  CheckCircle2,
  AlertCircle,
  XCircle,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  RefreshCw,
  Sparkles,
  Bot,
  Globe,
  ShieldCheck,
  ShoppingBag,
  Copy,
  Check,
} from "lucide-react";

const BACKEND_URL = "https://geo.properoapps.in/api";


/* Discovery configuration      */


const DISCOVERY_FILES = [
  {
    key: "agents_md",
    name: "agents.md",
    title: "Agent Instructions",
    description:
      "Helps AI agents understand your store, brand, products, and commerce policies.",
    path: "/agents.md",
    icon: Bot,
  },
  {
    key: "llms_txt",
    name: "llms.txt",
    title: "Store Information",
    description:
      "Provides a concise machine-readable overview of your store for AI systems.",
    path: "/llms.txt",
    icon: FileText,
  },
  {
    key: "llms_full_txt",
    name: "llms-full.txt",
    title: "Detailed Store Information",
    description:
      "Provides detailed machine-readable context about your store and catalog.",
    path: "/llms-full.txt",
    icon: FileText,
  },
  {
    key: "ucp_manifest",
    name: "UCP",
    title: "Universal Commerce Protocol",
    description:
      "Helps compatible AI agents discover your commerce capabilities.",
    path: "/.well-known/ucp",
    icon: ShoppingBag,
  },
];

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function getStatus(file) {
  const status = file?.status;

  if (status === "served_custom") {
    return {
      label: "Ready",
      description: "Available and customized",
      type: "success",
      icon: CheckCircle2,
    };
  }

  if (status === "served_default") {
    return {
      label: "Needs improvement",
      description: "Using the default configuration",
      type: "warning",
      icon: AlertCircle,
    };
  }

  if (status === "redirects") {
    return {
      label: "Redirects",
      description: "Redirects to another discovery file",
      type: "warning",
      icon: AlertCircle,
    };
  }

  if (status === "missing") {
    return {
      label: "Missing",
      description: "Could not be found on the storefront",
      type: "danger",
      icon: XCircle,
    };
  }

  if (status === "unreachable") {
    return {
      label: "Unavailable",
      description: "Could not connect to the storefront",
      type: "danger",
      icon: XCircle,
    };
  }

  return {
    label: "Not configured",
    description: "No discovery information available",
    type: "neutral",
    icon: AlertCircle,
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

  return "border-[var(--app-border)] bg-[var(--app-panel)] text-[var(--app-muted)]";
}

function getRecommendationPriority(priority) {
  if (priority === "high") {
    return {
      label: "High priority",
      classes: "border-[#f0c3be] bg-[#fff2f0] text-[#c43222]",
    };
  }

  if (priority === "low") {
    return {
      label: "Low priority",
      classes: "border-[#d9e4df] bg-[#f1f7f4] text-[#52706a]",
    };
  }

  return {
    label: "Medium priority",
    classes: "border-[#f2d39c] bg-[#fff8ea] text-[#9a6700]",
  };
}

function getStoreUrl(shopDomain, path) {
  if (!shopDomain || !path) return "#";

  return `https://${shopDomain}${path}`;
}

/* -------------------------------------------------------------------------- */
/* Main component                                                             */
/* -------------------------------------------------------------------------- */

export default function AgentDiscovery() {
  const navigate = useNavigate();
  const { shopDomain } = useRouteLoaderData("routes/app");

  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const [search, setSearch] = useState("");
  const [expandedFile, setExpandedFile] = useState(null);
  const [copied, setCopied] = useState(false);

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

        const data = await response.json();

        if (!cancelled) {
          setReport(data);
          setLoading(false);
        }
      } catch (err) {
        console.error("Failed to load Agent Discovery:", err);

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
        throw new Error(`Failed to refresh audit: ${response.status}`);
      }

      const data = await response.json();

      setReport(data);
    } catch (err) {
      console.error("Failed to refresh Agent Discovery:", err);
      setError("Unable to refresh Agent Discovery data.");
    } finally {
      setRefreshing(false);
    }
  };

  /* ------------------------------------------------------------------------ */
  /* Real backend data                                                        */
  /* ------------------------------------------------------------------------ */

  const agentDiscovery = report?.agent_discovery || null;

  const files = agentDiscovery?.files || {};

  const recommendations = Array.isArray(
    agentDiscovery?.recommendations
  )
    ? agentDiscovery.recommendations
    : [];

  /* ------------------------------------------------------------------------ */
  /* Summary                                                                  */
  /* ------------------------------------------------------------------------ */

  const summary = useMemo(() => {
    const available = DISCOVERY_FILES.filter((definition) => {
      const status = files[definition.key]?.status;

      return [
        "served_custom",
        "served_default",
        "redirects",
      ].includes(status);
    }).length;

    const ready = DISCOVERY_FILES.filter((definition) => {
      return files[definition.key]?.status === "served_custom";
    }).length;

    const missing = DISCOVERY_FILES.filter((definition) => {
      const status = files[definition.key]?.status;

      return ["missing", "unreachable"].includes(status);
    }).length;

    return {
      available,
      ready,
      missing,
      total: DISCOVERY_FILES.length,
    };
  }, [files]);

  /* ------------------------------------------------------------------------ */
  /* Search                                                                   */
  /* ------------------------------------------------------------------------ */

  const filteredFiles = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) {
      return DISCOVERY_FILES;
    }

    return DISCOVERY_FILES.filter((definition) => {
      const file = files[definition.key];

      const searchable = [
        definition.name,
        definition.title,
        definition.description,
        file?.status,
        file?.customization,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return searchable.includes(query);
    });
  }, [search, files]);

  /* ------------------------------------------------------------------------ */
  /* Copy                                                                    */
  /* ------------------------------------------------------------------------ */

  const copyDiscoverySummary = async () => {
    if (!agentDiscovery) return;

    const text = [
      "Agent Discovery",
      "",
      agentDiscovery.summary || "",
      "",
      ...DISCOVERY_FILES.map((definition) => {
        const file = files[definition.key];
        const status = getStatus(file);

        return `${definition.name}: ${status.label}`;
      }),
    ].join("\n");

    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);

      setTimeout(() => {
        setCopied(false);
      }, 1500);
    } catch (err) {
      console.error("Failed to copy Agent Discovery summary:", err);
    }
  };

  /* ------------------------------------------------------------------------ */
  /* Loading state                                                             */
  /* ------------------------------------------------------------------------ */

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] p-8">
        <div className="mx-auto max-w-7xl">
          <PageHeader
            shopDomain={shopDomain}
            refreshing={true}
            onRefresh={() => {}}
          />

          <div className="mt-8 rounded-xl border border-[var(--app-border)] bg-white p-12 text-center shadow-sm">
            <RefreshCw className="mx-auto h-7 w-7 animate-spin text-[var(--app-green)]" />

            <p className="mt-4 text-sm font-semibold text-[var(--app-text)]">
              Loading Agent Discovery
            </p>

            <p className="mt-1 text-xs text-[var(--app-muted)]">
              Fetching the latest audit results.
            </p>
          </div>
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /* Error state                                                               */
  /* ------------------------------------------------------------------------ */

  if (error) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] p-8">
        <div className="mx-auto max-w-7xl">
          <PageHeader
            shopDomain={shopDomain}
            refreshing={refreshing}
            onRefresh={refresh}
          />

          <div className="mt-8 rounded-xl border border-[#f0c3be] bg-white p-10 text-center shadow-sm">
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
  /* No audit                                                                  */
  /* ------------------------------------------------------------------------ */

  if (!report || !agentDiscovery) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] p-8">
        <div className="mx-auto max-w-7xl">
          <PageHeader
            shopDomain={shopDomain}
            refreshing={refreshing}
            onRefresh={refresh}
          />

          <div className="mt-8 rounded-xl border border-[var(--app-border)] bg-white p-12 text-center shadow-sm">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--app-orange-light)]">
              <Sparkles className="h-7 w-7 text-[var(--app-orange)]" />
            </div>

            <h2 className="mt-5 text-lg font-bold text-[var(--app-text)]">
              Run an audit to discover your store
            </h2>

            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[var(--app-muted)]">
              Agent Discovery results are generated as part of your store
              audit. Run an audit from the Dashboard to see how AI agents
              can discover your store.
            </p>

            <button
              type="button"
              onClick={() => navigate("/app")}
              className="mt-6 rounded-lg bg-[var(--app-green)] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[var(--app-green-dark)]"
            >
              Go to Dashboard
            </button>
          </div>
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /* Main page                                                                 */
  /* ------------------------------------------------------------------------ */

  return (
    <div className="min-h-screen bg-[var(--app-bg)] p-8">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Header */}
        <PageHeader
          shopDomain={shopDomain}
          refreshing={refreshing}
          onRefresh={refresh}
        />

        {/* Hero */}
        <section className="rounded-xl border border-[var(--app-border)] bg-white p-7 shadow-sm">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-3xl">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[var(--app-green)] text-white">
                  <Bot className="h-5 w-5" />
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-[var(--app-muted)]">
                    Agentic Commerce
                  </p>

                  <h1 className="text-2xl font-bold tracking-tight text-[var(--app-text)]">
                    Agent Discovery
                  </h1>
                </div>
              </div>

              <p className="mt-5 text-sm leading-6 text-[var(--app-muted)]">
                Make your store easier for AI agents to discover,
                understand, and use during agentic shopping experiences.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={copyDiscoverySummary}
                className="inline-flex items-center gap-2 rounded-lg border border-[var(--app-border)] bg-white px-4 py-2.5 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--app-panel)]"
              >
                {copied ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <Copy className="h-4 w-4" />
                )}

                {copied ? "Copied" : "Copy summary"}
              </button>

              <button
                type="button"
                onClick={refresh}
                disabled={refreshing}
                className="inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[var(--app-green-dark)] disabled:opacity-60"
              >
                <RefreshCw
                  className={`h-4 w-4 ${
                    refreshing ? "animate-spin" : ""
                  }`}
                />

                Refresh
              </button>
            </div>
          </div>
        </section>

        {/* Status overview */}
        <section className="grid gap-4 md:grid-cols-3">
          <OverviewCard
            icon={<Globe className="h-5 w-5" />}
            title="Discovery coverage"
            value={`${summary.available}/${summary.total}`}
            description="Discovery endpoints available on your storefront"
          />

          <OverviewCard
            icon={<ShieldCheck className="h-5 w-5" />}
            title="Ready for agents"
            value={`${summary.ready}/${summary.total}`}
            description="Endpoints detected as customized and ready"
          />

          <OverviewCard
            icon={<AlertCircle className="h-5 w-5" />}
            title="Needs attention"
            value={summary.missing}
            description="Discovery endpoints that need configuration"
          />
        </section>

        {/* Backend summary */}
        <section className="rounded-xl border border-[var(--app-border)] bg-white p-6 shadow-sm">
          <div className="flex items-start gap-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--app-orange-light)] text-[var(--app-orange)]">
              <Sparkles className="h-5 w-5" />
            </div>

            <div>
              <h2 className="text-base font-bold text-[var(--app-text)]">
                Your store's discovery status
              </h2>

              <p className="mt-2 max-w-4xl text-sm leading-6 text-[var(--app-muted)]">
                {agentDiscovery.summary ||
                  "Your latest audit contains Agent Discovery results."}
              </p>
            </div>
          </div>
        </section>

        {/* Search */}
        <section className="rounded-xl border border-[var(--app-border)] bg-white p-4 shadow-sm">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--app-muted)]" />

            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search discovery files..."
              className="w-full rounded-lg border border-[var(--app-border)] bg-white py-2.5 pl-9 pr-4 text-sm text-[var(--app-text)] outline-none placeholder:text-[var(--app-muted)] focus:border-[var(--app-green)] focus:ring-1 focus:ring-[var(--app-green)]"
            />
          </div>
        </section>

        {/* Discovery files */}
        <section className="rounded-xl border border-[var(--app-border)] bg-white shadow-sm">
          <div className="border-b border-[var(--app-border)] px-5 py-4">
            <h2 className="text-base font-bold text-[var(--app-text)]">
              Discovery files
            </h2>

            <p className="mt-1 text-xs text-[var(--app-muted)]">
              These are the discovery surfaces checked during your latest
              audit.
            </p>
          </div>

          <div className="divide-y divide-[var(--app-border)]">
            {filteredFiles.length === 0 ? (
              <div className="px-5 py-12 text-center">
                <Search className="mx-auto h-7 w-7 text-[var(--app-muted)]" />

                <p className="mt-3 text-sm font-semibold text-[var(--app-text)]">
                  No discovery files found
                </p>
              </div>
            ) : (
              filteredFiles.map((definition) => {
                const file = files[definition.key] || {};
                const status = getStatus(file);
                const StatusIcon = status.icon;
                const Icon = definition.icon;
                const expanded = expandedFile === definition.key;

                return (
                  <div key={definition.key}>
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedFile(
                          expanded ? null : definition.key
                        )
                      }
                      className="flex w-full items-center gap-4 px-5 py-5 text-left hover:bg-[var(--app-panel)]"
                    >
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--app-panel)] text-[var(--app-green)]">
                        <Icon className="h-5 w-5" />
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-sm font-bold text-[var(--app-text)]">
                            {definition.name}
                          </h3>

                          <span
                            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${statusClasses(
                              status.type
                            )}`}
                          >
                            <StatusIcon className="h-3.5 w-3.5" />
                            {status.label}
                          </span>
                        </div>

                        <p className="mt-1 text-xs leading-5 text-[var(--app-muted)]">
                          {definition.description}
                        </p>
                      </div>

                      <div className="shrink-0 text-[var(--app-muted)]">
                        {expanded ? (
                          <ChevronUp className="h-4 w-4" />
                        ) : (
                          <ChevronDown className="h-4 w-4" />
                        )}
                      </div>
                    </button>

                    {expanded && (
                      <DiscoveryDetails
                        definition={definition}
                        file={file}
                        status={status}
                        shopDomain={shopDomain}
                      />
                    )}
                  </div>
                );
              })
            )}
          </div>
        </section>

        {/* Recommendations */}
        <section className="rounded-xl border border-[var(--app-border)] bg-white shadow-sm">
          <div className="border-b border-[var(--app-border)] px-5 py-4">
            <h2 className="text-base font-bold text-[var(--app-text)]">
              Recommendations
            </h2>

            <p className="mt-1 text-xs text-[var(--app-muted)]">
              Improvements identified from your latest Agent Discovery audit.
            </p>
          </div>

          {recommendations.length === 0 ? (
            <div className="px-5 py-10 text-center">
              <CheckCircle2 className="mx-auto h-8 w-8 text-[var(--app-green)]" />

              <p className="mt-3 text-sm font-semibold text-[var(--app-text)]">
                No Agent Discovery recommendations
              </p>

              <p className="mt-1 text-xs text-[var(--app-muted)]">
                Your latest audit did not return any additional
                recommendations.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-[var(--app-border)]">
              {recommendations.map((recommendation, index) => {
                const priority = getRecommendationPriority(
                  recommendation.priority
                );

                return (
                  <div
                    key={`${recommendation.enrichment || "recommendation"}-${index}`}
                    className="p-5"
                  >
                    <div className="flex items-start gap-4">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[var(--app-orange-light)] text-[var(--app-orange)]">
                        <Sparkles className="h-4 w-4" />
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-sm font-bold text-[var(--app-text)]">
                            {recommendation.enrichment ||
                              "Agent Discovery improvement"}
                          </h3>

                          <span
                            className={`rounded-full border px-2.5 py-1 text-[10px] font-bold ${priority.classes}`}
                          >
                            {priority.label}
                          </span>
                        </div>

                        {recommendation.why_it_matters_for_agents && (
                          <p className="mt-2 text-xs leading-6 text-[var(--app-muted)]">
                            {recommendation.why_it_matters_for_agents}
                          </p>
                        )}

                        {recommendation.example && (
                          <div className="mt-3 rounded-lg border-l-2 border-[var(--app-orange)] bg-[var(--app-panel)] px-4 py-3">
                            <p className="text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
                              Recommended approach
                            </p>

                            <p className="mt-1 whitespace-pre-line text-xs leading-5 text-[var(--app-text)]">
                              {recommendation.example}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Last audit */}
        <div className="pb-6 text-center text-[11px] text-[var(--app-muted)]">
          Agent Discovery is based on your latest completed audit.
          {report?.created_at
            ? ` Last audited ${formatDate(report.created_at)}.`
            : ""}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Header                                                                     */
/* -------------------------------------------------------------------------- */

function PageHeader({ shopDomain, refreshing, onRefresh }) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-[var(--app-muted)]">
          Store
        </p>

        <p className="mt-0.5 text-sm font-semibold text-[var(--app-text)]">
          {shopDomain || "Shopify store"}
        </p>
      </div>

      <button
        type="button"
        onClick={onRefresh}
        disabled={refreshing}
        className="inline-flex items-center gap-2 self-start rounded-lg border border-[var(--app-border)] bg-white px-3.5 py-2 text-xs font-semibold text-[var(--app-text)] shadow-sm hover:bg-[var(--app-panel)] disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
      >
        <RefreshCw
          className={`h-3.5 w-3.5 ${
            refreshing ? "animate-spin" : ""
          }`}
        />

        Refresh audit
      </button>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Overview card                                                              */
/* -------------------------------------------------------------------------- */

function OverviewCard({ icon, title, value, description }) {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--app-orange-light)] text-[var(--app-orange)]">
          {icon}
        </div>

        <p className="text-xs font-semibold text-[var(--app-muted)]">
          {title}
        </p>
      </div>

      <p className="mt-4 text-2xl font-bold tracking-tight text-[var(--app-text)]">
        {value}
      </p>

      <p className="mt-1 text-[11px] leading-5 text-[var(--app-muted)]">
        {description}
      </p>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Discovery details                                                          */
/* -------------------------------------------------------------------------- */

function DiscoveryDetails({
  definition,
  file,
  status,
  shopDomain,
}) {
  const storeUrl = getStoreUrl(shopDomain, definition.path);

  return (
    <div className="border-t border-[var(--app-border)] bg-[var(--app-panel)] px-5 py-5">
      <div className="grid gap-5 lg:grid-cols-[1fr_auto]">
        <div>
          <p className="text-sm font-semibold text-[var(--app-text)]">
            {definition.title}
          </p>

          <p className="mt-1 text-xs leading-5 text-[var(--app-muted)]">
            {status.description}
          </p>

          {/* Status */}
          <div className="mt-4 flex flex-wrap gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${statusClasses(
                status.type
              )}`}
            >
              <status.icon className="h-3.5 w-3.5" />
              {status.label}
            </span>

            {file.mirrors_agents_md && (
              <span className="rounded-full border border-[var(--app-border)] bg-white px-2.5 py-1 text-[11px] font-semibold text-[var(--app-muted)]">
                Uses agents.md content
              </span>
            )}
          </div>

          {/* Customization message */}
          {file.customization === "heavily_customized" && (
            <div className="mt-4 rounded-lg border border-[#b7dfd3] bg-[#edf8f4] px-4 py-3">
              <div className="flex items-start gap-2">
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-[#067a5f]" />

                <div>
                  <p className="text-xs font-semibold text-[#067a5f]">
                    Customized for your store
                  </p>

                  <p className="mt-1 text-[11px] leading-5 text-[#52706a]">
                    This discovery resource contains store-specific
                    information that can help AI agents understand your
                    business.
                  </p>
                </div>
              </div>
            </div>
          )}

          {file.customization === "default_skeleton" && (
            <div className="mt-4 rounded-lg border border-[#f2d39c] bg-[#fff8ea] px-4 py-3">
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-[#9a6700]" />

                <div>
                  <p className="text-xs font-semibold text-[#9a6700]">
                    Default configuration
                  </p>

                  <p className="mt-1 text-[11px] leading-5 text-[#8a6b2b]">
                    Add store-specific information so AI agents can better
                    understand your products and brand.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Quality summary without technical metrics */}
          {file.quality &&
            Object.keys(file.quality).length > 0 && (
              <div className="mt-4">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
                  Recommended content
                </p>

                <div className="flex flex-wrap gap-2">
                  {Object.entries(file.quality).map(
                    ([key, value]) => {
                      const label = formatQualityLabel(key);

                      return (
                        <span
                          key={key}
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium ${
                            value
                              ? "border-[#b7dfd3] bg-[#edf8f4] text-[#067a5f]"
                              : "border-[var(--app-border)] bg-white text-[var(--app-muted)]"
                          }`}
                        >
                          {value ? (
                            <CheckCircle2 className="h-3 w-3" />
                          ) : (
                            <AlertCircle className="h-3 w-3" />
                          )}

                          {label}
                        </span>
                      );
                    }
                  )}
                </div>
              </div>
            )}
        </div>

        {/* Actions */}
        <div className="flex flex-row flex-wrap items-start gap-2 lg:flex-col">
          {status.type !== "danger" && (
            <a
              href={storeUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--app-green)] px-4 py-2.5 text-xs font-semibold text-white hover:bg-[var(--app-green-dark)]"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              View file
            </a>
          )}

          <button
            type="button"
            onClick={() => {
              window.open(storeUrl, "_blank", "noopener,noreferrer");
            }}
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--app-border)] bg-white px-4 py-2.5 text-xs font-semibold text-[var(--app-text)] hover:bg-[var(--app-panel)]"
          >
            <Globe className="h-3.5 w-3.5" />
            Open storefront
          </button>
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function formatQualityLabel(key) {
  const labels = {
    mentions_ucp_mcp: "UCP / MCP",
    policy_links: "Policy links",
    brand_identity: "Brand identity",
    shopping_guidance: "Shopping guidance",
  };

  return (
    labels[key] ||
    key
      .replaceAll("_", " ")
      .replace(/\b\w/g, (character) =>
        character.toUpperCase()
      )
  );
}

function formatDate(value) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString();
}