// app/routes/app.agent-discovery.jsx

import PropTypes from "prop-types";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useRouteLoaderData } from "react-router";
import {
  Search,
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
  Loader2,
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
    path: "/.well-known/ucp",
    icon: ShoppingBag,
  },
];

/* Status helpers*/

function getStatus(file) {
  const status = file?.status;

  if (status === "served_custom") {
    return {
      label: "Ready",
      description: "Available and customized for this store.",
      type: "success",
    };
  }

  if (status === "served_default") {
    return {
      label: "Needs configuration",
      description: "Available but still using Shopify's default template.",
      type: "warning",
    };
  }

  if (status === "redirects") {
    return {
      label: "Redirects",
      description: "Redirects to another discovery resource.",
      type: "warning",
    };
  }

  if (status === "password_protected") {
    return {
      label: "Password protected",
      description: "The storefront password page is blocking agents from reading this file.",
      type: "danger",
    };
  }

  if (status === "missing") {
    return {
      label: "Missing",
      description: "Could not be found on the storefront.",
      type: "danger",
    };
  }

  if (status === "unreachable") {
    return {
      label: "Unavailable",
      description: "The storefront resource could not be reached.",
      type: "danger",
    };
  }

  return {
    label: "Not checked yet",
    description: "Run a live Agent Discovery check to see this file's status.",
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


function getStoreUrl(shopDomain, path) {
  if (!shopDomain || !path) return "#";
  return `https://${shopDomain}${path}`;
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

/* Backend content helpers */

function getFileContent(file, fallbackContent) {
  if (!file) return fallbackContent || "";

  const candidates = [file.content, file._body, file.body, file.text];

  for (const value of candidates) {
    if (typeof value === "string" && value.trim()) {
      // A storefront password/login page is HTML, not a discovery file.
      if (/^\s*(<!doctype html|<html)/i.test(value)) continue;
      return value;
    }
  }

  if (file.mirrors_agents_md && fallbackContent) {
    return fallbackContent;
  }

  return "";
}

function getFileDisplayUrl(shopDomain, definition, file) {
  if (file?.final_url) return file.final_url;
  return getStoreUrl(shopDomain, definition.path);
}
function getMissingContentReason(file) {
  if (!file || !file.status) {
    return "This file hasn't been checked yet for this store.";
  }

  if (file.status === "redirects") {
    return file.final_url
      ? `This URL redirected to ${file.final_url} instead of returning the file's own content.`
      : "This URL redirected elsewhere instead of returning the file's own content.";
  }

  if (file.status === "missing") {
    return `No file was found at this URL${file.http_status ? ` (HTTP ${file.http_status})` : ""}.`;
  }

  if (file.status === "unreachable") {
    return "The storefront could not be reached to fetch this file.";
  }

  if (file.status === "served_custom" || file.status === "served_default") {
    return "The response was an HTML page, not agents.md text — this usually means the storefront returned a login or password page instead of the file.";
  }

  return "No content is available for this file.";
}

function getCustomizationText(file) {
  if (!file) {
    return "No discovery information is available.";
  }

  if (file.customization === "heavily_customized") {
    return "Heavily customized with store-specific information.";
  }

  if (file.customization === "lightly_customized") {
    return "Lightly customized — default boilerplate plus some added content.";
  }

  if (file.customization === "default_skeleton") {
    return "Still using Shopify's default template.";
  }

  if (file.customization === "empty") {
    return "Empty or too thin to classify.";
  }

  if (file.mirrors_agents_md) {
    return "Mirrors agents.md — no dedicated template defined for this file.";
  }

  return "";
}

/* -------------------------------------------------------------------------- */
/* Main component                                                             */
/* -------------------------------------------------------------------------- */

export default function AgentDiscovery() {
  const navigate = useNavigate();
  const { shopDomain } = useRouteLoaderData("routes/app");

  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [previewFile, setPreviewFile] = useState(null);
  const [configureOpen, setConfigureOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState(null);


  /* Load latest audit — the only endpoint this uses: GET /audits/latest,     */


  const fetchLatestAudit = useCallback(async () => {
    if (!shopDomain) return null;

    const response = await fetch(
      `${BACKEND_URL}/audits/latest?shop_domain=${encodeURIComponent(shopDomain)}`
    );

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      throw new Error(`Failed to load latest audit: ${response.status}`);
    }

    return response.json();
  }, [shopDomain]);

  useEffect(() => {
    if (!shopDomain) return;

    let cancelled = false;

    (async () => {
      try {
        setLoading(true);
        setError(null);

        const data = await fetchLatestAudit();

        if (!cancelled) {
          setReport(data);
          setLoading(false);
        }
      } catch (err) {
        console.error("Failed to load Agent Discovery:", err);

        if (!cancelled) {
          setError("Unable to load Agent Discovery data from the backend.");
          setLoading(false);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [fetchLatestAudit, shopDomain]);

  

  const openConfigure = async () => {
    if (checking) return;

    try {
      setChecking(true);
      setCheckError(null);

      const data = await fetchLatestAudit();
      setReport(data);
      setConfigureOpen(true);
    } catch (err) {
      console.error("Failed to refresh Agent Discovery:", err);
      setCheckError("Couldn't reach the backend to load Agent Discovery data. Try again.");
    } finally {
      setChecking(false);
    }
  };

  // backend data for  the audit

  const agentDiscovery = report?.agent_discovery || null;

  // The audit now stores the four raw discovery resources in dedicated DB columns.
  
  const files = useMemo(() => {
    const savedFiles = agentDiscovery?.files || {};
    if (!agentDiscovery) return {};

    return {
      ...savedFiles,
      agents_md: {
        ...(savedFiles.agents_md || {}),
        content: agentDiscovery.agents_md_content || "",
      },
      llms_txt: {
        ...(savedFiles.llms_txt || {}),
        content: agentDiscovery.llms_txt_content || "",
      },
      llms_full_txt: {
        ...(savedFiles.llms_full_txt || {}),
        content: agentDiscovery.llms_full_txt_content || "",
      },
      ucp_manifest: {
        ...(savedFiles.ucp_manifest || {}),
        content: agentDiscovery.ucp_content || "",
      },
    };
  }, [agentDiscovery]);

  // search

  const filteredFiles = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) {
      return DISCOVERY_FILES;
    }

    return DISCOVERY_FILES.filter((definition) => {
      const file = files?.[definition.key];

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
    });
  }, [search, files]);

  // loading part-this shows up a run page 

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

//  Error part-this shows up if backend data fails

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
            <p className="mt-2 text-sm text-[var(--app-muted)]">{error}</p>

            <button
              type="button"
              onClick={() => window.location.reload()}
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

  // no audit data yet — show a "Run Audit" page
  
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

          {checkError && (
            <div className="mt-6 rounded-lg border border-[#f0c3be] bg-[#fff2f0] px-4 py-3 text-sm text-[#c43222]">
              {checkError}
            </div>
          )}

          <div className="mt-8 rounded-xl border border-[var(--app-border)] bg-white p-14 text-center shadow-sm">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--app-orange-light)]">
              <Sparkles className="h-7 w-7 text-[var(--app-orange)]" />
            </div>

            <h2 className="mt-5 text-lg font-bold text-[var(--app-text)]">
              No Agent Discovery data yet
            </h2>

            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[var(--app-muted)]">
              Run a full store audit, or run a live Agent Discovery check on its
              own to see the real status of agents.md, llms.txt, llms-full.txt
              and the UCP manifest for this store right now.
            </p>

            <button
              type="button"
              onClick={openConfigure}
              disabled={checking}
              className="mt-6 inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-3 text-sm font-bold text-white shadow-sm hover:bg-[var(--app-green-dark)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {checking ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Checking this store…
                </>
              ) : (
                <>
                  <Settings2 className="h-4 w-4" />
                  Configure Agent Discovery
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Main page                                                                

  return (
    <>
      <div className="min-h-screen bg-[var(--app-bg)] p-8">
        <div className="mx-auto max-w-[1500px]">
        {/* Header */}
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
              onClick={openConfigure}
              disabled={checking}
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-[var(--app-green-dark)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {checking ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Checking this store…
                </>
              ) : (
                <>
                  <Settings2 className="h-4 w-4" />
                  Configure Agent Discovery
                </>
              )}
            </button>
          </div>

          {checkError && (
            <div className="mt-5 rounded-lg border border-[#f0c3be] bg-[#fff2f0] px-4 py-3 text-sm text-[#c43222]">
              {checkError}
            </div>
          )}
          {/* search */}
          <div className="relative mt-5 max-w-xs">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--app-muted)]" />
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search discovery files"
              className="w-full rounded-lg border border-[var(--app-border)] bg-white py-2.5 pl-9 pr-3 text-sm text-[var(--app-text)] placeholder:text-[var(--app-muted)] focus:border-[var(--app-green)] focus:outline-none"
            />
          </div>

          <section className="mt-6 grid grid-cols-1 gap-7 lg:grid-cols-2">
            {filteredFiles.map((definition) => {
              const file = files?.[definition.key] || {};
              const status = getStatus(file);
              const Icon = definition.icon;
              const displayUrl = getFileDisplayUrl(shopDomain, definition, file);

              return (
                <DiscoveryCard
                  key={definition.key}
                  definition={definition}
                  status={status}
                  Icon={Icon}
                  displayUrl={displayUrl}
                  checking={checking}
                  onPreview={() =>
                    setPreviewFile({ definition, file, status, displayUrl })
                  }
                  onConfigure={openConfigure}
                />
              );
            })}
          </section>
          {/* Footer */}

          <div className="py-8 text-center text-xs text-[var(--app-muted)]">
            Agent Discovery is based on the latest completed audit for{" "}
            <span className="font-semibold">{shopDomain}</span>.
            {report?.created_at ? ` Last audited ${formatDate(report.created_at)}.` : ""}
          </div>
        </div>
      </div>

      {/* Preview modal */}
      {previewFile && (
        <DiscoveryPreviewModal
          item={previewFile}
          onClose={() => setPreviewFile(null)}
          onConfigure={() => {
            setPreviewFile(null);
            openConfigure();
          }}
        />
      )}

      {/* Configure modal */}

      {configureOpen && (
        <ConfigureAgentDiscoveryModal
          shopDomain={shopDomain}
          files={files}
          checkedAt={agentDiscovery.checked_at}
          checking={checking}
          onClose={() => setConfigureOpen(false)}
          onRecheck={openConfigure}
          onPreview={(item) => {
            setConfigureOpen(false);
            setPreviewFile(item);
          }}
        />
      )}
    </>
  );
}

// Discovery card for each discovery file

function DiscoveryCard({
  definition,
  status,
  Icon,
  displayUrl,
  checking,
  onPreview,
  onConfigure,
}) {
  const isAgentsMd = definition.key === "agents_md";

  const actionLabel = isAgentsMd
    ? "Configure"
    : status.type === "success"
      ? "View"
      : "View Preview";

  return (
    <div className="rounded-2xl border border-[#DCDCDC] bg-white p-7 shadow-[0_2px_6px_rgba(0,0,0,0.08)]">
      <div className="flex items-start justify-between gap-5">
        <div className="flex min-w-0 items-start gap-4">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#F1F6F4] text-[var(--app-green)]">
            <Icon className="h-5 w-5" />
          </div>

          <div className="min-w-0">
            <h3 className="text-[17px] font-bold text-[var(--app-text)]">{definition.name}</h3>
            <p className="mt-1 text-sm text-[var(--app-muted)]">
              {definition.name === "UCP" ? "Universal Commerce Protocol (UCP)" : definition.name}
            </p>
          </div>
        </div>

        <span
          className={`shrink-0 rounded-md border px-3 py-1 text-xs font-semibold ${statusClasses(status.type)}`}
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
        <span className="shrink-0 text-xs font-medium text-[var(--app-muted)]">
          Live from store
        </span>
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
          onClick={isAgentsMd ? onConfigure : onPreview}
          disabled={isAgentsMd && checking}
          className="flex items-center gap-2 rounded-md bg-[var(--app-green)] px-5 py-2.5 text-sm font-bold text-white shadow-sm hover:bg-[var(--app-green-dark)] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isAgentsMd && checking ? (
            <>
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Checking…
            </>
          ) : (
            actionLabel
          )}
        </button>
      </div>
    </div>
  );
}

DiscoveryCard.propTypes = {
  definition: PropTypes.shape({
    key: PropTypes.string.isRequired,
    name: PropTypes.string.isRequired,
    description: PropTypes.string.isRequired,
  }).isRequired,
  status: PropTypes.shape({
    type: PropTypes.string.isRequired,
    label: PropTypes.string.isRequired,
  }).isRequired,
  Icon: PropTypes.elementType.isRequired,
  displayUrl: PropTypes.string.isRequired,
  checking: PropTypes.bool.isRequired,
  onPreview: PropTypes.func.isRequired,
  onConfigure: PropTypes.func.isRequired,
};

// Preview modal for any discovery file

function DiscoveryPreviewModal({ item, onClose, onConfigure }) {
  const { definition, file, status, displayUrl } = item;

  // Preview always uses the content saved with this audit.
  const content = getFileContent(file);

  const customization = getCustomizationText(file);

  const [copied, setCopied] = useState(false);

  const copyContent = async () => {
    if (!content) return;

    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.error("Failed to copy discovery content:", error);
    }

    DiscoveryPreviewModal.propTypes = {
      item: PropTypes.shape({
        definition: PropTypes.shape({
          name: PropTypes.string.isRequired,
          description: PropTypes.string.isRequired,
        }).isRequired,
        file: PropTypes.object.isRequired,
        status: PropTypes.shape({
          type: PropTypes.string.isRequired,
          label: PropTypes.string.isRequired,
        }).isRequired,
        displayUrl: PropTypes.string.isRequired,
      }).isRequired,
      onClose: PropTypes.func.isRequired,
      onConfigure: PropTypes.func.isRequired,
    };
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
              <h2 className="text-base font-bold text-[var(--app-text)]">{definition.name}</h2>
              <p className="mt-1 truncate font-mono text-xs text-[var(--app-muted)]">
                {displayUrl}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {content && (
              <button
                type="button"
                onClick={copyContent}
                className="inline-flex items-center gap-2 rounded-lg border border-[#DCDCDC] px-3 py-2 text-xs font-semibold text-[var(--app-text)] hover:bg-[#F5F5F5]"
              >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
            )}

            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-2 text-[#6D7175] hover:bg-[#F5F5F5] hover:text-[#202223]"
              aria-label="Close preview"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="overflow-y-auto px-6 py-6">
          <p className="text-sm leading-6 text-[var(--app-muted)]">{definition.description}</p>

          <div className="mt-5 flex flex-wrap gap-2">
            <span
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${statusClasses(status.type)}`}
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
                <span className="font-mono text-xs text-[#B7C0C8]">{definition.name}</span>
                <span className="text-[10px] text-[#7F8A92]">Saved from the latest audit</span>
              </div>

              <pre className="max-h-[430px] overflow-auto p-5 font-mono text-xs leading-5 text-[#B9E8D8]">
                {content}
              </pre>
            </div>
          ) : (
            <div className="mt-6 rounded-xl border border-[#DCDCDC] bg-[#F8F8F7] p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-[#9A6700]" />
                <p className="text-sm leading-6 text-[var(--app-text)]">
                  {getMissingContentReason(file)}
                </p>
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
  );
}

// Configure modal for agents.md
function ConfigureAgentDiscoveryModal({
  shopDomain,
  files,
  checkedAt,
  checking,
  onClose,
  onRecheck,
  onPreview,
}) {
  const definition =
    DISCOVERY_FILES.find((item) => item.key === "agents_md") || DISCOVERY_FILES[0];

  const file = files?.agents_md || {};
  const status = getStatus(file);
  const content = getFileContent(file);
  const displayUrl = getFileDisplayUrl(shopDomain, definition, file);

  const quality =
    file.quality && typeof file.quality === "object" ? file.quality : {};

  const [copied, setCopied] = useState(false);

  const copyContent = async () => {
    if (!content) return;

    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.error("Failed to copy agents.md content:", err);
    }

    ConfigureAgentDiscoveryModal.propTypes = {
      shopDomain: PropTypes.string.isRequired,
      files: PropTypes.shape({
        agents_md: PropTypes.object,
      }).isRequired,
      checkedAt: PropTypes.string,
      checking: PropTypes.bool.isRequired,
      onClose: PropTypes.func.isRequired,
      onRecheck: PropTypes.func.isRequired,
      onPreview: PropTypes.func.isRequired,
    };
  };

  return (
    <div className="fixed inset-0 z-[110] flex items-center justify-center bg-black/45 p-4 backdrop-blur-[2px]">
      <div className="flex max-h-[92vh] w-full max-w-[980px] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-[#E1E3E5] px-6 py-5">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#F1F6F4] text-[var(--app-green)]">
              <Bot className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h2 className="text-lg font-bold text-[var(--app-text)]">agents.md</h2>
              <p className="mt-1 truncate font-mono text-xs text-[var(--app-muted)]">
                {displayUrl}
              </p>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {content && (
              <button
                type="button"
                onClick={copyContent}
                className="inline-flex items-center gap-2 rounded-lg border border-[#DCDCDC] px-3 py-2 text-xs font-semibold text-[var(--app-text)] hover:bg-[#F5F5F5]"
              >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? "Copied" : "Copy"}
              </button>
            )}

            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-2 text-[#6D7175] hover:bg-[#F5F5F5] hover:text-[#202223]"
              aria-label="Close"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="overflow-y-auto px-6 py-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h3 className="text-base font-bold text-[var(--app-text)]">
                Agent Instructions
              </h3>
              <p className="mt-1 text-sm leading-6 text-[var(--app-muted)]">
                Loaded from the latest completed audit for {shopDomain}
                {checkedAt ? ` · checked ${formatDate(checkedAt)}` : ""}.
              </p>
            </div>

            <span
              className={`shrink-0 rounded-full border px-3 py-1 text-xs font-semibold ${statusClasses(status.type)}`}
            >
              {status.label}
            </span>
          </div>

          <div className="mt-5 rounded-lg border border-[#DCDCDC] bg-[#F7F7F7] px-4 py-3">
            <div className="flex items-start gap-2">
              <Globe className="mt-0.5 h-4 w-4 shrink-0 text-[var(--app-muted)]" />
              <div className="min-w-0 flex-1">
                <div className="text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                  Endpoint / Final URL
                </div>
                <div className="mt-1 break-all font-mono text-xs leading-5 text-[#53657A]">
                  {file.final_url || displayUrl}
                </div>
              </div>
              <a
                href={displayUrl}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 text-[#6D7175] hover:text-[var(--app-green)]"
                aria-label="Open agents.md"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
            {[
              ["HTTP Status", file.http_status ?? "—"],
              ["Word Count", file.word_count ?? "—"],
              ["Customized", file.looks_customized ? "Yes" : "No"],
              ["Classification", file.customization || "—"],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-lg border border-[#DCDCDC] bg-[#FAFAFA] px-4 py-3"
              >
                <div className="text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                  {label}
                </div>
                <div className="mt-1 break-words text-sm font-semibold text-[var(--app-text)]">
                  {value}
                </div>
              </div>
            ))}
          </div>

          {Object.keys(quality).length > 0 && (
            <div className="mt-5 rounded-xl border border-[#E1E3E5] bg-white p-5">
              <div className="text-sm font-bold text-[var(--app-text)]">Content checks</div>
              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
                {Object.entries(quality).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex items-center justify-between gap-4 rounded-lg border border-[#E1E3E5] bg-[#FAFAFA] px-3 py-2.5"
                  >
                    <span className="text-xs font-medium capitalize text-[#6D7175]">
                      {key.replaceAll("_", " ")}
                    </span>
                    <span
                      className={`text-xs font-bold ${value ? "text-[#067a5f]" : "text-[#c43222]"}`}
                    >
                      {value ? "Yes" : "No"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {content ? (
            <div className="mt-5 overflow-hidden rounded-xl bg-[#202223]">
              <div className="flex items-center justify-between border-b border-[#383A3C] px-4 py-3">
                <div>
                  <span className="font-mono text-xs text-[#B7C0C8]">agents.md</span>
                  <span className="ml-2 text-[10px] text-[#7F8A92]">From the latest audit</span>
                </div>
                <button
                  type="button"
                  onClick={() => onPreview({ definition, file, status, displayUrl })}
                  className="text-xs font-semibold text-white hover:underline"
                >
                  View full preview
                </button>
              </div>
              <pre className="max-h-[430px] overflow-auto whitespace-pre-wrap p-5 font-mono text-xs leading-5 text-[#B9E8D8]">
                {content}
              </pre>
            </div>
          ) : (
            <div className="mt-5 rounded-xl border border-[#DCDCDC] bg-[#FAFAFA] p-5">
              <p className="text-sm leading-6 text-[var(--app-text)]">
                {getMissingContentReason(file)}
              </p>
            </div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[#E1E3E5] bg-[#FAFAFA] px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="px-2 py-2 text-sm font-medium text-[#6D7175] hover:text-[#202223]"
          >
            Close
          </button>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onRecheck}
              disabled={checking}
              className="inline-flex items-center gap-2 rounded-lg border border-[#DCDCDC] px-5 py-2.5 text-sm font-bold text-[var(--app-text)] hover:bg-[#F5F5F5] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {checking ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Checking…
                </>
              ) : (
                <>
                  <RefreshCw className="h-4 w-4" />
                  Re-check now
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => onPreview({ definition, file, status, displayUrl })}
              className="inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-2.5 text-sm font-bold text-white hover:bg-[var(--app-green-dark)]"
            >
              View Full Preview
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}