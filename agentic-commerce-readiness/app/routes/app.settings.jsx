import { useEffect, useState } from "react";
import {
  Bell,
  Bot,
  CalendarClock,
  CheckCircle2,
  Database,
  Mail,
  RefreshCw,
  Settings as SettingsIcon,
  Store,
  Upload,
} from "lucide-react";

const SETTINGS_KEY = "acr_settings";

const DEFAULT_SETTINGS = {
  auditCadence: "manual",
  autoReaudit: false,
  notifications: true,
  notificationEmail: "",
  agentDiscovery: true,
  proxyStatus: true,
};

export default function Settings({ loaderData }) {
  const shopDomain = loaderData?.shopDomain || "";

  const [settings, setSettings] =
    useState(DEFAULT_SETTINGS);

  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(SETTINGS_KEY);

    if (!stored) return;

    try {
      setSettings({
        ...DEFAULT_SETTINGS,
        ...JSON.parse(stored),
      });
    } catch (error) {
      console.error(
        "Unable to load settings:",
        error
      );
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
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify(settings)
    );

    setSaved(true);

    setTimeout(() => {
      setSaved(false);
    }, 2500);
  };

  const resetSettings = () => {
    setSettings(DEFAULT_SETTINGS);

    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify(DEFAULT_SETTINGS)
    );

    setSaved(true);

    setTimeout(() => {
      setSaved(false);
    }, 2500);
  };

  return (
    <main className="min-h-screen bg-[var(--app-bg)] px-6 py-8">
      <div className="mx-auto max-w-5xl">

        {/* Header */}
        <div className="mb-8 flex items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <SettingsIcon
                size={24}
                className="text-[var(--app-green)]"
              />

              <h1 className="text-2xl font-bold text-[var(--app-text)]">
                Settings
              </h1>
            </div>

            <p className="max-w-2xl text-sm text-[var(--app-muted)]">
              Manage your Shopify connection, audit
              preferences, notifications, and agent
              discovery configuration.
            </p>
          </div>

          <button
            onClick={saveSettings}
            className="rounded-lg bg-[var(--app-green)] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[var(--app-green-dark)]"
          >
            Save changes
          </button>
        </div>

        {saved && (
          <div className="mb-6 flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm font-medium text-green-700">
            <CheckCircle2 size={17} />
            Settings saved successfully.
          </div>
        )}

        <div className="space-y-6">

          {/* Shopify connection */}
          <SettingsSection
            icon={<Store size={19} />}
            title="Shopify Connection"
            description="The Shopify store connected to this app."
          >
            <div className="rounded-xl border border-[var(--app-border)] bg-[var(--acr-panel)] p-4">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-[var(--app-muted)]">
                    Connected store
                  </div>

                  <div className="font-semibold text-[var(--app-text)]">
                    {shopDomain || "Current Shopify store"}
                  </div>
                </div>

                <div className="flex items-center gap-2 rounded-full bg-green-50 px-3 py-1.5 text-xs font-bold text-green-700">
                  <CheckCircle2 size={14} />
                  Connected
                </div>
              </div>
            </div>
          </SettingsSection>

          {/* Audit configuration */}
          <SettingsSection
            icon={<CalendarClock size={19} />}
            title="Audit Configuration"
            description="Control how and when your store is audited."
          >
            <div className="space-y-5">

              <SettingRow
                title="Audit cadence"
                description="Choose how frequently you want audits to be scheduled."
              >
                <select
                  value={settings.auditCadence}
                  onChange={(event) =>
                    updateSetting(
                      "auditCadence",
                      event.target.value
                    )
                  }
                  className="rounded-lg border border-[var(--app-border)] bg-white px-3 py-2 text-sm text-[var(--app-text)] outline-none focus:border-[var(--app-green)]"
                >
                  <option value="manual">
                    Manual
                  </option>

                  <option value="daily">
                    Daily
                  </option>

                  <option value="weekly">
                    Weekly
                  </option>

                  <option value="monthly">
                    Monthly
                  </option>
                </select>
              </SettingRow>

              <SettingRow
                title="Automatic re-audit"
                description="Automatically re-check the store after changes are detected."
              >
                <Toggle
                  checked={settings.autoReaudit}
                  onChange={(value) =>
                    updateSetting(
                      "autoReaudit",
                      value
                    )
                  }
                />
              </SettingRow>

            </div>
          </SettingsSection>

          {/* Notifications */}
          <SettingsSection
            icon={<Bell size={19} />}
            title="Notifications"
            description="Configure audit and readiness notifications."
          >
            <div className="space-y-5">

              <SettingRow
                title="Email notifications"
                description="Receive notifications when an audit is completed."
              >
                <Toggle
                  checked={settings.notifications}
                  onChange={(value) =>
                    updateSetting(
                      "notifications",
                      value
                    )
                  }
                />
              </SettingRow>

              <div>
                <label className="mb-2 block text-sm font-semibold text-[var(--app-text)]">
                  Notification email
                </label>

                <div className="relative">
                  <Mail
                    size={17}
                    className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--app-muted)]"
                  />

                  <input
                    type="email"
                    value={
                      settings.notificationEmail
                    }
                    onChange={(event) =>
                      updateSetting(
                        "notificationEmail",
                        event.target.value
                      )
                    }
                    placeholder="you@example.com"
                    className="w-full rounded-lg border border-[var(--app-border)] bg-white py-2.5 pl-10 pr-3 text-sm text-[var(--app-text)] outline-none focus:border-[var(--app-green)]"
                  />
                </div>
              </div>

            </div>
          </SettingsSection>

          {/* Agent configuration */}
          <SettingsSection
            icon={<Bot size={19} />}
            title="Agent Configuration"
            description="Manage machine-readable agent discovery features."
          >
            <div className="space-y-5">

              <SettingRow
                title="Agent discovery"
                description="Enable discovery information generated from your audit data."
              >
                <Toggle
                  checked={settings.agentDiscovery}
                  onChange={(value) =>
                    updateSetting(
                      "agentDiscovery",
                      value
                    )
                  }
                />
              </SettingRow>

              <SettingRow
                title="Storefront proxy"
                description="Indicates whether the agent discovery proxy is configured."
              >
                <div className="flex items-center gap-2 rounded-full bg-green-50 px-3 py-1.5 text-xs font-bold text-green-700">
                  <CheckCircle2 size={14} />
                  Active
                </div>
              </SettingRow>

            </div>
          </SettingsSection>

          {/* CSV operations */}
          <SettingsSection
            icon={<Database size={19} />}
            title="Catalog Operations"
            description="Tools for working with your product catalog."
          >
            <div className="grid gap-4 md:grid-cols-2">

              <OperationCard
                icon={<Upload size={18} />}
                title="Import products"
                description="Import product data from a CSV file."
                button="Import CSV"
                onClick={() =>
                  alert(
                    "CSV import will be connected to the product workflow."
                  )
                }
              />

              <OperationCard
                icon={<Database size={18} />}
                title="Export audit data"
                description="Export the latest audit results for analysis."
                button="Export data"
                onClick={() =>
                  exportLatestReport()
                }
              />

            </div>
          </SettingsSection>

          {/* Current data */}
          <SettingsSection
            icon={<RefreshCw size={19} />}
            title="Application Data"
            description="Manage locally stored audit information."
          >
            <div className="flex flex-col gap-4 rounded-xl border border-[var(--app-border)] bg-[var(--acr-panel)] p-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="font-semibold text-[var(--app-text)]">
                  Reset local configuration
                </div>

                <p className="mt-1 text-sm text-[var(--app-muted)]">
                  Resets application preferences stored
                  in this browser.
                </p>
              </div>

              <button
                onClick={resetSettings}
                className="rounded-lg border border-[var(--app-border)] bg-white px-4 py-2 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
              >
                Reset settings
              </button>
            </div>
          </SettingsSection>

          {/* Version / status */}
          <div className="pb-8 text-center text-xs text-[var(--app-muted)]">
            Agentic Commerce Readiness · Powered by Propero
          </div>

        </div>
      </div>
    </main>
  );
}

function SettingsSection({
  icon,
  title,
  description,
  children,
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-[var(--app-border)] bg-white">
      <div className="border-b border-[var(--app-border)] px-5 py-5">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 text-[var(--app-green)]">
            {icon}
          </div>

          <div>
            <h2 className="font-semibold text-[var(--app-text)]">
              {title}
            </h2>

            <p className="mt-1 text-sm text-[var(--app-muted)]">
              {description}
            </p>
          </div>
        </div>
      </div>

      <div className="p-5">
        {children}
      </div>
    </section>
  );
}

function SettingRow({
  title,
  description,
  children,
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="text-sm font-semibold text-[var(--app-text)]">
          {title}
        </div>

        <p className="mt-1 max-w-xl text-sm leading-5 text-[var(--app-muted)]">
          {description}
        </p>
      </div>

      <div className="shrink-0">
        {children}
      </div>
    </div>
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
        checked
          ? "bg-[var(--app-green)]"
          : "bg-gray-300"
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

function OperationCard({
  icon,
  title,
  description,
  button,
  onClick,
}) {
  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-[var(--acr-panel)] p-5">
      <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--app-orange-light)] text-[var(--app-green)]">
        {icon}
      </div>

      <h3 className="font-semibold text-[var(--app-text)]">
        {title}
      </h3>

      <p className="mt-1 mb-4 text-sm leading-5 text-[var(--app-muted)]">
        {description}
      </p>

      <button
        onClick={onClick}
        className="rounded-lg border border-[var(--app-border)] bg-white px-3 py-2 text-sm font-semibold text-[var(--app-text)] hover:bg-[var(--acr-cream)]"
      >
        {button}
      </button>
    </div>
  );
}

function exportLatestReport() {
  const stored =
    localStorage.getItem("acr_latest_report");

  if (!stored) {
    alert(
      "No completed audit report is available to export."
    );

    return;
  }

  try {
    const report = JSON.parse(stored);

    const blob = new Blob(
      [JSON.stringify(report, null, 2)],
      {
        type: "application/json;charset=utf-8",
      }
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
    console.error(
      "Unable to export report:",
      error
    );

    alert(
      "Unable to export the latest report."
    );
  }
}