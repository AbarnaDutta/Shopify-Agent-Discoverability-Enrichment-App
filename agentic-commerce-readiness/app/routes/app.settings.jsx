import { useLoaderData } from "react-router";
import { authenticate } from "../shopify.server";
import { useEffect, useState } from "react";
import {
  Bell,
  Bot,
  CalendarClock,
  CheckCircle2,
  Database,
  ExternalLink,
  FileSpreadsheet,
  Mail,
  RefreshCw,
  Save,
  Settings as SettingsIcon,
  Sparkles,
  Store,
  Upload,
  Download,
} from "lucide-react";

const SETTINGS_KEY = "acr_settings";

const DEFAULT_SETTINGS = {
  auditCadence: "weekly",
  autoReaudit: true,
  notifications: true,
  notificationEmail: "",
  agentDiscovery: true,
  proxyStatus: true,
};
export const loader = async ({ request }) => {
  const { admin, session } = await authenticate.admin(request);

  if (!session?.shop) {
    throw new Response("Shopify session is missing.", {
      status: 401,
    });
  }

  try {
    const response = await admin.graphql(`
      query SettingsStoreDetails {
        shop {
          name
          myshopifyDomain
          plan {
            publicDisplayName
          }
        }
      }
    `);

    const result = await response.json();

    if (result.errors?.length || !result.data?.shop) {
      console.error("Settings store query failed:", result.errors);

      throw new Response("Unable to fetch Shopify store details.", {
        status: 502,
      });
    }

    const shop = result.data.shop;

    return {
      shopName: shop.name,
      shopDomain: shop.myshopifyDomain || session.shop,
      shopPlan: shop.plan?.publicDisplayName || "Unavailable",
      isConnected: true,
    };
  } catch (error) {
    console.error("Settings loader error:", error);

    if (error instanceof Response) {
      throw error;
    }

    throw new Response("Unable to load Shopify store details.", {
      status: 500,
    });
  }
};
export default function Settings({ onRelaunchTour }) {
  const loaderData = useLoaderData();

  const shopName = loaderData?.shopName || "Unavailable";
  const shopDomain = loaderData?.shopDomain || "Unavailable";
  const shopPlan = loaderData?.shopPlan || "Unavailable";
  const isConnected = loaderData?.isConnected === true;

    const agentFilesStatus =
    loaderData?.agentFilesStatus || "Managed by Agentic Commerce";

  const proxyStatus =
    loaderData?.proxyStatus || "Unavailable";

  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(SETTINGS_KEY);

      if (stored) {
        setSettings({
          ...DEFAULT_SETTINGS,
          ...JSON.parse(stored),
        });
      }
    } catch (error) {
      console.error("Unable to load settings:", error);
    }
  }, []);

  const updateSetting = (key, value) => {
    setSettings((previous) => ({
      ...previous,
      [key]: value,
    }));

    setSaved(false);
  };

  const saveSettings = () => {
    try {
      localStorage.setItem(
        SETTINGS_KEY,
        JSON.stringify(settings)
      );

      setSaved(true);
      window.setTimeout(() => setSaved(false), 2500);
    } catch (error) {
      console.error("Unable to save settings:", error);
      alert("Unable to save settings.");
    }
  };

  const resetSettings = () => {
    setSettings(DEFAULT_SETTINGS);
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify(DEFAULT_SETTINGS)
    );
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2500);
  };

  const storeLabel = shopName || shopDomain || "Shopify store";

  return (
    <main className="min-h-screen bg-[var(--app-bg)] px-5 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl">

        {/* Page heading */}
        <div className="mb-8">
          <div className="mb-2 flex items-center gap-2">
            <SettingsIcon
              size={22}
              className="text-[var(--app-text)]"
            />
            <h1 className="text-2xl font-bold text-[var(--app-text)]">
              Settings
            </h1>
          </div>

          <p className="text-sm text-[var(--app-muted)]">
            Configure Shopify store access, automated audit
            cadences, and machine-readable agent files.
          </p>
        </div>

        {/* Store */}
        <SettingsSection title="Store">
          <SettingRow
            title="Store Name"
            description="Currently connected Shopify store"
          >
            <div className="max-w-full rounded-md border border-[var(--app-border)] bg-[var(--acr-panel)] px-4 py-2 text-sm font-semibold text-[var(--app-text)]">
              {storeLabel}
            </div>
          </SettingRow>

          <SettingRow
            title="Store Domain"
            description="Primary Shopify store identifier"
          >
            {shopDomain ? (
              <a
                href={`https://${shopDomain}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-md border border-[var(--app-border)] bg-[var(--acr-panel)] px-4 py-2 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
              >
                {shopDomain}
                <ExternalLink size={14} />
              </a>
            ) : (
              <StatusBadge status="Not available" />
            )}
          </SettingRow>

          <SettingRow
            title="Shopify Connection"
            description="Admin API connection and store access"
          >
            <StatusBadge
              status={isConnected ? "Connected" : "Not connected"}
              success={isConnected}
            />
          </SettingRow>

          <SettingRow
            title="Shopify Plan"
            description="Current subscription plan for this store"
          >
            <div className="rounded-md border border-[var(--app-border)] bg-[var(--acr-panel)] px-4 py-2 text-sm font-medium text-[var(--app-text)]">
              {shopPlan}
            </div>
          </SettingRow>
        </SettingsSection>

        {/* Audit settings */}
        <SettingsSection title="Audit Settings">
          <SettingRow
            title="Audit frequency"
            description="How often agent crawlers re-evaluate your entire catalog"
          >
            <select
              value={settings.auditCadence}
              onChange={(event) =>
                updateSetting("auditCadence", event.target.value)
              }
              className="min-w-52 rounded-md border border-[var(--app-border)] bg-[var(--acr-panel)] px-3 py-2 text-sm text-[var(--app-text)] outline-none focus:border-[var(--app-green)]"
            >
              <option value="manual">Manual</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly (Recommended)</option>
              <option value="monthly">Monthly</option>
            </select>
          </SettingRow>

          <SettingRow
            title="Automatic re-audit"
            description="Re-scan items immediately whenever product taxonomy or inventory updates"
          >
            <Toggle
              checked={settings.autoReaudit}
              onChange={(value) =>
                updateSetting("autoReaudit", value)
              }
            />
          </SettingRow>

          <SettingRow
            title="Audit notifications"
            description="Receive executive alerts when critical purchase blockers are flagged"
          >
            <Toggle
              checked={settings.notifications}
              onChange={(value) =>
                updateSetting("notifications", value)
              }
            />
          </SettingRow>

          <SettingRow
            title="Audit Notification Email"
            description="Email address used for audit notifications"
          >
            <div className="relative w-full sm:w-72">
              <Mail
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--app-muted)]"
              />
              <input
                type="email"
                value={settings.notificationEmail}
                onChange={(event) =>
                  updateSetting(
                    "notificationEmail",
                    event.target.value
                  )
                }
                placeholder="Enter notification email"
                className="w-full rounded-md border border-[var(--app-border)] bg-[var(--acr-panel)] py-2 pl-9 pr-3 text-sm text-[var(--app-text)] outline-none focus:border-[var(--app-green)]"
              />
            </div>
          </SettingRow>
        </SettingsSection>

        {/* Agent configuration */}
        <SettingsSection title="Agent Configuration">
          <SettingRow
            title="Agent files"
            description="Distribution method for agents.md, llms.txt, and UCP schemas"
          >
            <div className="rounded-md border border-[var(--app-border)] bg-[var(--acr-panel)] px-4 py-2 text-sm font-medium text-[var(--app-text)]">
              {agentFilesStatus}
            </div>
          </SettingRow>

          <SettingRow
            title="Root Proxy Status"
            description="Automatically routes requests from /.well-known/agents.md to dynamic catalog specifications"
          >
            <StatusBadge
              status={proxyStatus}
              success={proxyStatus === "Active Routing"}
            />
          </SettingRow>

          <SettingRow
            title="Agent Discovery"
            description="Enable machine-readable agent discovery information for this store"
          >
            <Toggle
              checked={settings.agentDiscovery}
              onChange={(value) =>
                updateSetting("agentDiscovery", value)
              }
            />
          </SettingRow>
        </SettingsSection>

        {/* Save settings */}
        <div className="flex justify-end">
          <button
            type="button"
            onClick={saveSettings}
            className="inline-flex items-center gap-2 rounded-lg bg-[var(--app-green)] px-5 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-[var(--app-green-dark)]"
          >
            <Save size={17} />
            Save Settings
          </button>
        </div>

        {saved && (
          <div className="mt-4 flex items-center justify-end gap-2 text-sm font-medium text-green-700">
            <CheckCircle2 size={17} />
            Settings saved successfully.
          </div>
        )}

        {/* Onboarding guide */}
        <SettingsSection
          title="Merchant Onboarding & Audit Guide"
          right={
            <span className="rounded-md border border-green-200 bg-green-50 px-3 py-1 text-xs font-medium text-green-700">
              Interactive Walkthrough
            </span>
          }
        >
          <SettingRow
            title="Relaunch Onboarding & Audit Tour"
            description="Review the 5 foundational pillars of agentic commerce (Catalog Enrichment, MCP Knowledge, UCP Commerce Flows, Safety & Policies, and Agent Discovery) and trigger a baseline scan."
          >
            <button
              type="button"
              onClick={() => {
                if (onRelaunchTour) {
                  onRelaunchTour();
                } else {
                  window.dispatchEvent(
                    new CustomEvent("acr:relaunch-onboarding")
                  );
                }
              }}
              className="inline-flex items-center gap-2 rounded-md border border-green-200 bg-green-50 px-4 py-2.5 text-sm font-semibold text-[var(--app-green)] hover:bg-green-100"
            >
              <Sparkles size={17} />
              Relaunch Onboarding Tour
            </button>
          </SettingRow>
        </SettingsSection>

        {/* Catalog operations */}
        <SettingsSection
          title="Catalog Data & CSV Operations"
          right={
            <span className="text-xs text-[var(--app-muted)]">
              Spreadsheet Import / Export
            </span>
          }
        >
          <SettingRow
            title="Import Products from CSV"
            description="Bulk upload products with GTINs, MPNs, specifications, and attributes for instant audit scoring."
          >
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => alert("Connect your existing CSV template download handler here.")}
                className="inline-flex items-center gap-2 rounded-md border border-[var(--app-border)] bg-[var(--acr-panel)] px-3 py-2 text-sm font-medium text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
              >
                <FileSpreadsheet size={16} />
                Download Template
              </button>

              <button
                type="button"
                onClick={() => alert("Connect your existing CSV import handler here.")}
                className="inline-flex items-center gap-2 rounded-md border border-[var(--app-border)] bg-white px-3 py-2 text-sm font-medium text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
              >
                <Upload size={16} />
                Import CSV
              </button>
            </div>
          </SettingRow>

          <SettingRow
            title="Export Audit Results in CSV Format"
            description="Download comprehensive spreadsheet reports including detected blockers, item readiness scores, and store summaries."
          >
            <button
              type="button"
              onClick={exportLatestReport}
              className="inline-flex items-center gap-2 rounded-md border border-[var(--app-border)] bg-white px-4 py-2.5 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
            >
              <Download size={16} />
              Export Audit CSVs
            </button>
          </SettingRow>
        </SettingsSection>

        {/* Local settings reset */}
        <div className="mt-6 flex flex-col justify-between gap-4 rounded-xl border border-[var(--app-border)] bg-white p-5 sm:flex-row sm:items-center">
          <div>
            <h3 className="text-sm font-semibold text-[var(--app-text)]">
              Reset local configuration
            </h3>
            <p className="mt-1 text-sm text-[var(--app-muted)]">
              Reset saved preferences in this browser.
            </p>
          </div>

          <button
            type="button"
            onClick={resetSettings}
            className="rounded-lg border border-[var(--app-border)] bg-white px-4 py-2 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
          >
            Reset Settings
          </button>
        </div>

        <div className="pb-8 pt-6 text-center text-xs text-[var(--app-muted)]">
          Agentic Commerce Readiness · Powered by Propero
        </div>
      </div>
    </main>
  );
}

function SettingsSection({ title, right, children }) {
  return (
    <section className="mb-6 overflow-hidden rounded-xl border border-[var(--app-border)] bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--app-border)] px-5 py-5">
        <h2 className="text-sm font-bold uppercase tracking-wide text-[var(--app-text)]">
          {title}
        </h2>
        {right}
      </div>

      <div className="px-5">
        {children}
      </div>
    </section>
  );
}

function SettingRow({ title, description, children }) {
  return (
    <div className="flex flex-col gap-3 border-b border-[var(--app-border)] py-5 last:border-b-0 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h3 className="text-sm font-medium text-[var(--app-text)]">
          {title}
        </h3>
        <p className="mt-1 max-w-2xl text-sm leading-5 text-[var(--app-muted)]">
          {description}
        </p>
      </div>

      <div className="w-full shrink-0 sm:w-auto">
        {children}
      </div>
    </div>
  );
}

function StatusBadge({ status, success = false }) {
  return (
    <span
      className={`inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-semibold ${
        success
          ? "border-green-200 bg-green-50 text-green-700"
          : "border-[var(--app-border)] bg-[var(--acr-panel)] text-[var(--app-muted)]"
      }`}
    >
      {success && <CheckCircle2 size={15} />}
      {status}
    </span>
  );
}

function Toggle({ checked, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 rounded-full transition ${
        checked ? "bg-[var(--app-green)]" : "bg-gray-300"
      }`}
    >
      <span
        className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow transition ${
          checked ? "left-6" : "left-1"
        }`}
      />
    </button>
  );
}

function exportLatestReport() {
  const stored = localStorage.getItem("acr_latest_report");

  if (!stored) {
    alert("No completed audit report is available to export.");
    return;
  }

  try {
    const report = JSON.parse(stored);
    const blob = new Blob(
      [JSON.stringify(report, null, 2)],
      { type: "application/json;charset=utf-8" }
    );

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = "agentic-commerce-audit.json";

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  } catch (error) {
    console.error("Unable to export report:", error);
    alert("Unable to export the latest report.");
  }
}
