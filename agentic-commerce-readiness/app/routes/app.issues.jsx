// app/routes/app.issues.jsx

import { useEffect, useMemo, useState, Fragment } from "react";
import PropTypes from "prop-types";
import { useFetcher, useNavigate, useRouteLoaderData } from "react-router";
import {
  Search,
  AlertCircle,
  ChevronDown,
  ChevronUp,
  Wrench,
  X,
  LoaderCircle,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import { authenticate } from "../shopify.server";

const API_BASE = "https://geo.properoapps.in/api";



export async function action({ request }) {
  const { session } = await authenticate.admin(request);
  if (!session?.shop || !session?.accessToken) {
    return Response.json(
      { detail: "Shopify session is not authenticated." },
      { status: 401 }
    );
  }

  const payload = await request.json();
  const endpoint = payload.__endpoint || "/store/fix";
  delete payload.__endpoint;

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload,
      shop_domain: session.shop,
      access_token: session.accessToken,
    }),
  });

  const data = await response
    .json()
    .catch(() => ({ detail: "Invalid response from fix backend." }));
  return Response.json(data, { status: response.status });
}

/* -------------------------------------------------------------------------- */
/* Helpers                                                                    */
/* -------------------------------------------------------------------------- */

function getPriority(value) {
  const priority = String(value || "medium").toLowerCase();
  return ["high", "medium", "low"].includes(priority) ? priority : "medium";
}

function getAffectedProducts(recommendation, products) {
  const ids = Array.isArray(recommendation?.affected_product_ids)
    ? recommendation.affected_product_ids.map(String)
    : [];
  if (ids.length === 0) return [];
  return products.filter((product) => ids.includes(String(product.product_id)));
}

function prettyLabel(value) {
  return String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

const STORE_CHECK_LABELS = {
  fulfillment_context: "Shipping & Fulfillment",
  faq_or_guidance: "FAQ & Help Content",
  legal_pages: "Legal Pages",
  store_guardrails: "Store Guardrails",
  contact_brand: "Contact & Brand Information",
  consistency: "Catalog Consistency",
};

function resolveStoreCheckId(recommendation, storeIssues) {
  const direct = recommendation?.check_id || recommendation?.fix_payload?.check_id;
  if (direct) return direct;

  const label = String(recommendation?.enrichment || "").trim().toLowerCase();
  const matches = new Set(
    storeIssues
      .filter((issue) => {
        const issueLabel =
          STORE_CHECK_LABELS[issue.check_id] || prettyLabel(issue.check_id);
        return issueLabel.toLowerCase() === label;
      })
      .map((issue) => issue.check_id)
      .filter(Boolean)
  );
  if (matches.size === 1) return [...matches][0];

  const all = new Set(storeIssues.map((issue) => issue.check_id).filter(Boolean));
  return all.size === 1 ? [...all][0] : "";
}

const STORE_FIX_PANEL = {
  update_policy: "policy",
  update_store_contact: "contact",
  update_brand_information: "brand",
  configure_store_guardrail: "guardrail",
  update_fulfillment_information: "fulfillment",
  normalize_option_structure: "norm_options",
  normalize_metafield_structure: "norm_metafields",
  normalize_attribute_formats: "norm_metafields",
  normalize_attribute_units: "norm_metafields",
};

const STORE_FIX_LABEL = {
  update_policy: "Store Policies",
  update_store_contact: "Contact Information",
  update_brand_information: "About / Brand Page",
  configure_store_guardrail: "Store Disclosure",
  update_fulfillment_information: "Shipping & Fulfillment",
  normalize_option_structure: "Option Names",
  normalize_metafield_structure: "Missing Attributes",
  normalize_attribute_formats: "Attribute Formats",
  normalize_attribute_units: "Attribute Units",
};

const CONSISTENCY_ACTIONS = {
  inconsistent_option_structure: "normalize_option_structure",
  inconsistent_metafield_structure: "normalize_metafield_structure",
  inconsistent_attribute_format: "normalize_attribute_formats",
  inconsistent_attribute_units: "normalize_attribute_units",
};


function inferStoreFixAction(issue) {
  if (issue?.fix_action) return issue.fix_action;
  switch (issue?.check_id) {
    case "fulfillment_context":
      return "update_fulfillment_information";
    case "policy_semantics":
    case "legal_pages":
      return "update_policy";
    case "store_guardrails":
      return "configure_store_guardrail";
    case "contact_brand":
      return issue.issue_type === "missing_brand_information"
        ? "update_brand_information"
        : "update_store_contact";
    case "consistency":
      return CONSISTENCY_ACTIONS[issue.issue_type] || "";
    default:
      return "";
  }
}

function getStoreFixablePanels(issues) {
  const byAction = new Map();
  for (const issue of issues || []) {
    const action = inferStoreFixAction(issue);
    const panel = STORE_FIX_PANEL[action];
    if (!panel) continue;
    if (!byAction.has(action)) {
      byAction.set(action, { ...issue, fix_action: action, panel, issues: [] });
    }
    byAction.get(action).issues.push(issue);
  }
  return [...byAction.values()];
}


const INPUT_CLS =
  "w-full rounded-md border border-[#E1E3E5] bg-white px-3 py-2 text-xs text-[#202223] outline-none focus:border-[#D97706] disabled:opacity-60";

function FieldLabel({ children }) {
  return (
    <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
      {children}
    </label>
  );
}

function PanelShell({ children }) {
  return (
    <div className="space-y-3 rounded-lg border border-[#E1E3E5] bg-white p-3">
      {children}
    </div>
  );
}

function ApprovalCheck({ checked, onChange, disabled, children }) {
  return (
    <label className="flex items-start gap-2 text-[11px] leading-relaxed text-[#202223]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
        className="mt-0.5"
      />
      <span>{children}</span>
    </label>
  );
}

function ApplyBar({ status, message, ready, onApply, label = "Apply Fix" }) {
  const disabled = status === "submitting" || status === "done";
  return (
    <div>
      <button
        type="button"
        onClick={onApply}
        disabled={disabled || !ready}
        className="rounded-md bg-[#111111] px-3 py-1.5 text-xs font-bold text-white transition-opacity hover:bg-[#333333] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {status === "submitting" ? "Applying..." : status === "done" ? "Applied" : label}
      </button>
      {message && (
        <p
          className={`mt-1.5 text-xs ${
            status === "error" ? "text-[#D72C0D]" : "text-[#065F46]"
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}

function SeverityBadge({ priority }) {
  const severity = getPriority(priority);
  const styles = {
    high: "border-[#FFC9C5] bg-[#FFF0EF] text-[#D72C0D]",
    medium: "border-[#FFE0A3] bg-[#FFF5E5] text-[#8A6116]",
    low: "border-[#E1E3E5] bg-[#F1F2F3] text-[#6D7175]",
  };
  const dotStyles = {
    high: "bg-[#D72C0D]",
    medium: "bg-[#FFB100]",
    low: "bg-[#6D7175]",
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${styles[severity]}`}
    >
      <span className={`h-2 w-2 rounded-full ${dotStyles[severity]}`} />
      {prettyLabel(severity)}
    </span>
  );
}

SeverityBadge.propTypes = { priority: PropTypes.string };


function useStoreFix(fixIssue) {
  const fetcher = useFetcher();
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");

  const submit = (changes) => {
    setStatus("submitting");
    setMessage("");
    fetcher.submit(
      {
        __endpoint: "/store/fix",
        issue_id: fixIssue.id,
        check_id: fixIssue.check_id,
        issue_type: fixIssue.issue_type,
        changes,
      },
      {
        method: "post",
        action: window.location.pathname + window.location.search,
        encType: "application/json",
      }
    );
  };

  useEffect(() => {
    if (fetcher.state !== "idle" || !fetcher.data) return;
    const data = fetcher.data;
    if (data.success) {
      setStatus("done");
      setMessage(data.message || "Fix applied.");
    } else {
      setStatus("error");
      setMessage(data.detail || data.message || "Failed to apply fix.");
    }
  }, [fetcher.state, fetcher.data]);

  return { submit, status, message };
}



const POLICY_OPTIONS = [
  { value: "REFUND_POLICY", label: "Refund policy" },
  { value: "SHIPPING_POLICY", label: "Shipping policy" },
  { value: "PRIVACY_POLICY", label: "Privacy policy" },
  { value: "TERMS_OF_SERVICE", label: "Terms of service" },
  { value: "CONTACT_INFORMATION", label: "Contact information" },
];

function inferPolicyType(issueType) {
  const t = String(issueType || "");
  if (t.includes("privacy")) return "PRIVACY_POLICY";
  if (t.includes("terms")) return "TERMS_OF_SERVICE";
  if (t.includes("shipping")) return "SHIPPING_POLICY";
  return "REFUND_POLICY";
}

function PolicyFixPanel({ fixIssue }) {
  const { submit, status, message } = useStoreFix(fixIssue);
  const [rows, setRows] = useState(() => {
    const types = [
      ...new Set((fixIssue.issues || []).map((i) => inferPolicyType(i.issue_type))),
    ];
    return (types.length ? types : ["REFUND_POLICY"]).map((policy_type) => ({
      policy_type,
      body: "",
    }));
  });
  const [approved, setApproved] = useState(false);
  const disabled = status === "submitting" || status === "done";

  const update = (index, patch) =>
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  const valid = rows.filter((r) => r.body.trim());
  const ready = approved && valid.length > 0;

  return (
    <PanelShell>
      <p className="rounded-md bg-[#FFF5E5] p-2 text-[11px] leading-relaxed text-[#8A6116]">
        Saving replaces the <strong>entire</strong> existing policy with the text below. Paste the
        complete policy, not just the missing part.
      </p>

      {rows.map((row, index) => (
        <div key={index} className="space-y-2 rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3">
          <div className="flex items-center gap-2">
            <select
              value={row.policy_type}
              onChange={(e) => update(index, { policy_type: e.target.value })}
              disabled={disabled}
              className="rounded-md border border-[#E1E3E5] bg-white px-2 py-1.5 text-xs outline-none focus:border-[#D97706] disabled:opacity-60"
            >
              {POLICY_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            {rows.length > 1 && !disabled && (
              <button
                type="button"
                onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                aria-label="Remove policy"
                className="px-1 text-xs font-bold text-[#D72C0D]"
              >
                ✕
              </button>
            )}
          </div>
          <textarea
            rows={7}
            value={row.body}
            onChange={(e) => update(index, { body: e.target.value })}
            disabled={disabled}
            placeholder="Complete policy text..."
            className={`${INPUT_CLS} resize-y`}
          />
        </div>
      ))}

      {!disabled && (
        <button
          type="button"
          onClick={() => setRows((prev) => [...prev, { policy_type: "REFUND_POLICY", body: "" }])}
          className="rounded-md border border-[#E1E3E5] px-2.5 py-1.5 text-xs font-semibold hover:bg-[#F8F9FA]"
        >
          + Add Policy
        </button>
      )}

      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve this text to be published on my store.
      </ApprovalCheck>

      <ApplyBar
        status={status}
        message={message}
        ready={ready}
        onApply={() =>
          ready &&
          submit(
            valid.map((r) => ({
              policy_type: r.policy_type,
              body: r.body.trim(),
              merchant_approved: true,
            }))
          )
        }
      />
    </PanelShell>
  );
}



function ContactFixPanel({ fixIssue }) {
  const { submit, status, message } = useStoreFix(fixIssue);
  const [body, setBody] = useState("");
  const [approved, setApproved] = useState(false);
  const disabled = status === "submitting" || status === "done";
  const ready = approved && body.trim();

  return (
    <PanelShell>
      <div>
        <FieldLabel>Contact information</FieldLabel>
        <textarea
          rows={6}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          disabled={disabled}
          placeholder={"Email: support@example.com\nPhone: +1 555 000 0000\nAddress: ..."}
          className={`${INPUT_CLS} resize-y`}
        />
        <p className="mt-1 text-[10px] text-[#6D7175]">
          Replaces your store's contact information policy.
        </p>
      </div>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve this text to be published on my store.
      </ApprovalCheck>
      <ApplyBar
        status={status}
        message={message}
        ready={ready}
        onApply={() => ready && submit([{ body: body.trim(), merchant_approved: true }])}
      />
    </PanelShell>
  );
}


const PAGE_GID_RE = /^gid:\/\/shopify\/Page\/\d+$/;

function BrandFixPanel({ fixIssue }) {
  const { submit, status, message } = useStoreFix(fixIssue);
  const [pageId, setPageId] = useState(fixIssue.page_id || "");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [publish, setPublish] = useState(false);
  const [approved, setApproved] = useState(false);
  const disabled = status === "submitting" || status === "done";

  const pageOk = PAGE_GID_RE.test(pageId.trim());
  const ready = approved && pageOk && body.trim();

  return (
    <PanelShell>
      <div>
        <FieldLabel>About page ID</FieldLabel>
        <input
          type="text"
          value={pageId}
          onChange={(e) => setPageId(e.target.value)}
          disabled={disabled}
          placeholder="gid://shopify/Page/123456789"
          className={`${INPUT_CLS} font-mono`}
        />
        <p className={`mt-1 text-[10px] ${pageId && !pageOk ? "text-[#D72C0D]" : "text-[#6D7175]"}`}>
          An existing Shopify page is required. Create an empty About page in Shopify admin first if
          you don't have one.
        </p>
      </div>
      <div>
        <FieldLabel>Page title (optional)</FieldLabel>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={disabled}
          placeholder="About us"
          className={INPUT_CLS}
        />
      </div>
      <div>
        <FieldLabel>Page content</FieldLabel>
        <textarea
          rows={8}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          disabled={disabled}
          placeholder="Who you are, what you sell, and what makes your brand different..."
          className={`${INPUT_CLS} resize-y`}
        />
        <p className="mt-1 text-[10px] text-[#6D7175]">Replaces the page's entire current content.</p>
      </div>
      <ApprovalCheck checked={publish} onChange={setPublish} disabled={disabled}>
        Publish the page if it is currently hidden.
      </ApprovalCheck>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve this content to be saved on my store.
      </ApprovalCheck>
      <ApplyBar
        status={status}
        message={message}
        ready={ready}
        onApply={() =>
          ready &&
          submit([
            {
              page_id: pageId.trim(),
              body: body.trim(),
              merchant_approved: true,
              ...(title.trim() && { title: title.trim() }),
              ...(publish && { publish: true }),
            },
          ])
        }
      />
    </PanelShell>
  );
}

/* -------------------------------------------------------------------------- */
/* Guardrail panel (configure_store_guardrail)                                */
/* -------------------------------------------------------------------------- */

function GuardrailFixPanel({ fixIssue }) {
  const { submit, status, message } = useStoreFix(fixIssue);
  const [text, setText] = useState("");
  const [approved, setApproved] = useState(false);
  const disabled = status === "submitting" || status === "done";
  const ready = approved && text.trim();

  return (
    <PanelShell>
      <div>
        <FieldLabel>Store disclosure / warning text</FieldLabel>
        <textarea
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          placeholder="e.g. Products on this store are for adults 18+. Age verification is required at delivery."
          className={`${INPUT_CLS} resize-y`}
        />
        <p className="mt-1 text-[10px] text-[#6D7175]">
          Saved as store-level evidence for AI agents. It does not display a warning on your storefront
          or enforce age restrictions.
        </p>
      </div>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve this disclosure text.
      </ApprovalCheck>
      <ApplyBar
        status={status}
        message={message}
        ready={ready}
        onApply={() => ready && submit([{ warning_text: text.trim(), merchant_approved: true }])}
      />
    </PanelShell>
  );
}

/* -------------------------------------------------------------------------- */
/* Fulfillment panel (update_fulfillment_information)                         */
/* -------------------------------------------------------------------------- */

const PICKUP_TIMES = [
  { value: "ONE_HOUR", label: "1 hour" },
  { value: "TWO_HOURS", label: "2 hours" },
  { value: "FOUR_HOURS", label: "4 hours" },
  { value: "TWENTY_FOUR_HOURS", label: "24 hours" },
  { value: "TWO_TO_FOUR_DAYS", label: "2–4 days" },
  { value: "FIVE_OR_MORE_DAYS", label: "5 or more days" },
];

function parseJsonObject(text) {
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function FulfillmentFixPanel({ fixIssue }) {
  const { submit, status, message } = useStoreFix(fixIssue);
  const [shippingBody, setShippingBody] = useState("");
  const [pickups, setPickups] = useState([]);
  const [showProfile, setShowProfile] = useState(false);
  const [profileId, setProfileId] = useState("");
  const [profileJson, setProfileJson] = useState("");
  const [approved, setApproved] = useState(false);
  const disabled = status === "submitting" || status === "done";

  const updatePickup = (index, patch) =>
    setPickups((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));

  const pickupComplete = (p) => p.locationId.trim() && p.instructions.trim();
  const pickupIncomplete = pickups.some(
    (p) => (p.locationId.trim() || p.instructions.trim()) && !pickupComplete(p)
  );

  const profileUsed = profileId.trim() || profileJson.trim();
  const profileObject = profileUsed ? parseJsonObject(profileJson) : null;
  const profileOk = !profileUsed || (profileId.trim() && profileObject);

  const change = {};
  if (shippingBody.trim()) change.shipping_policy_body = shippingBody.trim();
  const readyPickups = pickups.filter(pickupComplete);
  if (readyPickups.length) {
    change.pickup_settings = readyPickups.map((p) => ({
      locationId: p.locationId.trim(),
      pickupTime: p.pickupTime,
      instructions: p.instructions.trim(),
    }));
  }
  if (profileUsed && profileOk) {
    change.delivery_profile_id = profileId.trim();
    change.delivery_profile_update = profileObject;
  }

  const ready = approved && Object.keys(change).length > 0 && !pickupIncomplete && profileOk;

  return (
    <PanelShell>
      <p className="rounded-md bg-[#FFF5E5] p-2 text-[11px] leading-relaxed text-[#8A6116]">
        Fill in any of the sections below. Updates are applied in order and are not rolled back if a
        later one fails.
      </p>

      <div>
        <FieldLabel>Shipping policy (delivery times, methods, regions)</FieldLabel>
        <textarea
          rows={6}
          value={shippingBody}
          onChange={(e) => setShippingBody(e.target.value)}
          disabled={disabled}
          placeholder="Complete shipping policy. Replaces the existing shipping policy."
          className={`${INPUT_CLS} resize-y`}
        />
      </div>

      <div className="space-y-2">
        <FieldLabel>Local pickup</FieldLabel>
        {pickups.map((p, index) => (
          <div key={index} className="space-y-2 rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={p.locationId}
                onChange={(e) => updatePickup(index, { locationId: e.target.value })}
                disabled={disabled}
                placeholder="gid://shopify/Location/123456789"
                className={`${INPUT_CLS} font-mono`}
              />
              <select
                value={p.pickupTime}
                onChange={(e) => updatePickup(index, { pickupTime: e.target.value })}
                disabled={disabled}
                className="rounded-md border border-[#E1E3E5] bg-white px-2 py-2 text-xs outline-none focus:border-[#D97706] disabled:opacity-60"
              >
                {PICKUP_TIMES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
              {!disabled && (
                <button
                  type="button"
                  onClick={() => setPickups((prev) => prev.filter((_, i) => i !== index))}
                  aria-label="Remove pickup location"
                  className="px-1 text-xs font-bold text-[#D72C0D]"
                >
                  ✕
                </button>
              )}
            </div>
            <textarea
              rows={2}
              value={p.instructions}
              onChange={(e) => updatePickup(index, { instructions: e.target.value })}
              disabled={disabled}
              placeholder="Pickup instructions (e.g. bring your order confirmation to the front desk)"
              className={`${INPUT_CLS} resize-y`}
            />
          </div>
        ))}
        {pickupIncomplete && (
          <p className="text-[11px] text-[#D72C0D]">
            Each pickup location needs both a location ID and instructions.
          </p>
        )}
        {!disabled && (
          <button
            type="button"
            onClick={() =>
              setPickups((prev) => [
                ...prev,
                { locationId: "", pickupTime: "TWO_TO_FOUR_DAYS", instructions: "" },
              ])
            }
            className="rounded-md border border-[#E1E3E5] px-2.5 py-1.5 text-xs font-semibold hover:bg-[#F8F9FA]"
          >
            + Add Pickup Location
          </button>
        )}
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowProfile((v) => !v)}
          className="text-xs font-semibold text-[#6D7175] underline hover:text-[#202223]"
        >
          {showProfile ? "Hide delivery profile (advanced)" : "Delivery profile (advanced)"}
        </button>
        {showProfile && (
          <div className="mt-2 space-y-2">
            <input
              type="text"
              value={profileId}
              onChange={(e) => setProfileId(e.target.value)}
              disabled={disabled}
              placeholder="gid://shopify/DeliveryProfile/123456789"
              className={`${INPUT_CLS} font-mono`}
            />
            <textarea
              rows={6}
              value={profileJson}
              onChange={(e) => setProfileJson(e.target.value)}
              disabled={disabled}
              spellCheck={false}
              placeholder={'DeliveryProfileInput as JSON, e.g. {"name": "General profile", ...}'}
              className={`${INPUT_CLS} resize-y font-mono`}
            />
            {profileUsed && !profileOk && (
              <p className="text-[11px] text-[#D72C0D]">
                Provide both the profile ID and a valid JSON object.
              </p>
            )}
          </div>
        )}
      </div>

      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve these fulfillment changes.
      </ApprovalCheck>

      <ApplyBar
        status={status}
        message={message}
        ready={ready}
        onApply={() => ready && submit([change])}
      />
    </PanelShell>
  );
}


const METAFIELD_TYPES = [
  { value: "single_line_text_field", label: "Text (single line)" },
  { value: "multi_line_text_field", label: "Text (multi-line)" },
  { value: "number_integer", label: "Number (integer)" },
  { value: "number_decimal", label: "Number (decimal)" },
  { value: "dimension", label: "Dimension" },
  { value: "list.single_line_text_field", label: "List of text" },
];

const DIMENSION_UNITS = ["MILLIMETERS", "CENTIMETERS", "METERS", "INCHES", "FEET", "YARDS"];

const emptyMetaRow = () => ({
  namespace: "details",
  key: "",
  type: "single_line_text_field",
  value: "",
  unit: "CENTIMETERS",
  values: [""],
});

function isMetaRowValid(row) {
  if (!row.key.trim() || !row.namespace.trim()) return false;
  if (row.type === "list.single_line_text_field") return row.values.some((v) => v.trim());
  if (row.type === "dimension") return row.value.trim() !== "" && Number.isFinite(Number(row.value));
  return row.value.trim() !== "";
}

function buildMetaEntry(row) {
  let value;
  if (row.type === "dimension") {
    value = JSON.stringify({ unit: row.unit, value: Number(row.value) });
  } else if (row.type === "list.single_line_text_field") {
    value = JSON.stringify(row.values.map((v) => v.trim()).filter(Boolean));
  } else {
    value = row.value.trim();
  }
  return {
    namespace: row.namespace.trim(),
    key: row.key.trim(),
    type: row.type,
    value,
  };
}

function MetafieldRowEditor({ row, onChange, onRemove, disabled }) {
  const setListValue = (i, v) =>
    onChange({ values: row.values.map((item, idx) => (idx === i ? v : item)) });

  return (
    <div className="space-y-2 rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={row.namespace}
          onChange={(e) => onChange({ namespace: e.target.value })}
          disabled={disabled}
          placeholder="namespace"
          className={`${INPUT_CLS} w-28 font-mono`}
        />
        <input
          type="text"
          value={row.key}
          onChange={(e) => onChange({ key: e.target.value })}
          disabled={disabled}
          placeholder="Attribute key"
          className={`${INPUT_CLS} min-w-[120px] flex-1 font-mono`}
        />
        <select
          value={row.type}
          onChange={(e) => onChange({ type: e.target.value })}
          disabled={disabled}
          className="rounded-md border border-[#E1E3E5] bg-white px-2 py-2 text-xs outline-none focus:border-[#D97706] disabled:opacity-60"
        >
          {METAFIELD_TYPES.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
        {onRemove && !disabled && (
          <button
            type="button"
            onClick={onRemove}
            aria-label="Remove attribute"
            className="px-1 text-xs font-bold text-[#D72C0D]"
          >
            ✕
          </button>
        )}
      </div>

      {row.type === "single_line_text_field" && (
        <input
          type="text"
          value={row.value}
          onChange={(e) => onChange({ value: e.target.value })}
          disabled={disabled}
          placeholder="Value"
          className={INPUT_CLS}
        />
      )}
      {row.type === "multi_line_text_field" && (
        <textarea
          rows={3}
          value={row.value}
          onChange={(e) => onChange({ value: e.target.value })}
          disabled={disabled}
          placeholder="Value"
          className={`${INPUT_CLS} resize-y`}
        />
      )}
      {(row.type === "number_integer" || row.type === "number_decimal") && (
        <input
          type="number"
          step={row.type === "number_integer" ? "1" : "any"}
          value={row.value}
          onChange={(e) => onChange({ value: e.target.value })}
          disabled={disabled}
          placeholder={row.type === "number_integer" ? "Whole number" : "Decimal number"}
          className={INPUT_CLS}
        />
      )}
      {row.type === "dimension" && (
        <div className="flex gap-2">
          <input
            type="number"
            step="any"
            value={row.value}
            onChange={(e) => onChange({ value: e.target.value })}
            disabled={disabled}
            placeholder="Value"
            className={`${INPUT_CLS} min-w-0 flex-1`}
          />
          <select
            value={row.unit}
            onChange={(e) => onChange({ unit: e.target.value })}
            disabled={disabled}
            className="rounded-md border border-[#E1E3E5] bg-white px-2 py-2 text-xs outline-none focus:border-[#D97706] disabled:opacity-60"
          >
            {DIMENSION_UNITS.map((u) => (
              <option key={u} value={u}>
                {prettyLabel(u.toLowerCase())}
              </option>
            ))}
          </select>
        </div>
      )}
      {row.type === "list.single_line_text_field" && (
        <div className="space-y-2">
          {row.values.map((v, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                type="text"
                value={v}
                onChange={(e) => setListValue(i, e.target.value)}
                disabled={disabled}
                placeholder={`Value ${i + 1}`}
                className={`${INPUT_CLS} min-w-0 flex-1`}
              />
              {row.values.length > 1 && !disabled && (
                <button
                  type="button"
                  onClick={() => onChange({ values: row.values.filter((_, idx) => idx !== i) })}
                  className="text-xs font-bold text-[#D72C0D]"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
          {!disabled && (
            <button
              type="button"
              onClick={() => onChange({ values: [...row.values, ""] })}
              className="text-xs font-semibold text-[#8A6116] hover:underline"
            >
              + Add value
            </button>
          )}
        </div>
      )}
    </div>
  );
}


const emptyOptionRow = () => ({ id: "", name: "" });

const NORMALIZE_HINTS = {
  normalize_option_structure:
    "Rename each product's options so they use the same names across the catalog.",
  normalize_metafield_structure:
    "Add the missing attributes for each product. Use the exact namespace and key used by your other products.",
  normalize_attribute_formats:
    "Enter each value in the canonical format used across your catalog.",
  normalize_attribute_units:
    "Enter values already converted to the unit you want to standardize on.",
};

function NormalizePanel({ fixIssue, mode, products }) {
  const isOptions = mode === "options";
  const { submit, status, message } = useStoreFix(fixIssue);
  const disabled = status === "submitting" || status === "done";

  const [entries, setEntries] = useState(() =>
    products.map((p) => ({
      product_id: String(p.product_id),
      title: p.title || "",
      rows:
        isOptions && Array.isArray(p.options) && p.options.length > 0
          ? p.options.map((o) => ({ id: o.id || "", name: o.name || "" }))
          : [isOptions ? emptyOptionRow() : emptyMetaRow()],
    }))
  );
  const [newProductId, setNewProductId] = useState("");
  const [approved, setApproved] = useState(false);

  const updateRow = (entryIndex, rowIndex, patch) =>
    setEntries((prev) =>
      prev.map((e, i) =>
        i === entryIndex
          ? { ...e, rows: e.rows.map((r, ri) => (ri === rowIndex ? { ...r, ...patch } : r)) }
          : e
      )
    );

  const addRow = (entryIndex) =>
    setEntries((prev) =>
      prev.map((e, i) =>
        i === entryIndex
          ? { ...e, rows: [...e.rows, isOptions ? emptyOptionRow() : emptyMetaRow()] }
          : e
      )
    );

  const removeRow = (entryIndex, rowIndex) =>
    setEntries((prev) =>
      prev.map((e, i) =>
        i === entryIndex && e.rows.length > 1
          ? { ...e, rows: e.rows.filter((_, ri) => ri !== rowIndex) }
          : e
      )
    );

  const addProduct = () => {
    const id = newProductId.trim();
    if (!/^gid:\/\/shopify\/Product\/\d+$/.test(id)) return;
    if (entries.some((e) => e.product_id === id)) return;
    setEntries((prev) => [
      ...prev,
      { product_id: id, title: "", rows: [isOptions ? emptyOptionRow() : emptyMetaRow()] },
    ]);
    setNewProductId("");
  };

  const validRows = (entry) =>
    isOptions
      ? entry.rows.filter((r) => r.id.trim() && r.name.trim())
      : entry.rows.filter(isMetaRowValid);

  const changes = entries
    .map((entry) => {
      const rows = validRows(entry);
      if (rows.length === 0) return null;
      return isOptions
        ? {
            product_id: entry.product_id,
            options: rows.map((r) => ({ id: r.id.trim(), name: r.name.trim() })),
          }
        : { product_id: entry.product_id, metafields: rows.map(buildMetaEntry) };
    })
    .filter(Boolean);

  const ready = approved && changes.length > 0;

  return (
    <PanelShell>
      <p className="text-[11px] leading-relaxed text-[#6D7175]">
        {NORMALIZE_HINTS[fixIssue.fix_action]}
      </p>

      {entries.length === 0 && (
        <p className="text-xs text-[#6D7175]">
          No affected products were listed. Add a product ID below.
        </p>
      )}

      {entries.map((entry, entryIndex) => (
        <div key={entry.product_id} className="space-y-2 rounded-lg border border-[#E1E3E5] p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="truncate text-xs font-semibold text-[#202223]">
              {entry.title || entry.product_id}
            </p>
            {!disabled && (
              <button
                type="button"
                onClick={() => setEntries((prev) => prev.filter((_, i) => i !== entryIndex))}
                className="text-[11px] font-semibold text-[#D72C0D] hover:underline"
              >
                Skip product
              </button>
            )}
          </div>

          {entry.rows.map((row, rowIndex) =>
            isOptions ? (
              <div key={rowIndex} className="flex items-center gap-2">
                <input
                  type="text"
                  value={row.id}
                  onChange={(e) => updateRow(entryIndex, rowIndex, { id: e.target.value })}
                  disabled={disabled}
                  placeholder="gid://shopify/ProductOption/…"
                  className={`${INPUT_CLS} min-w-0 flex-1 font-mono`}
                />
                <input
                  type="text"
                  value={row.name}
                  onChange={(e) => updateRow(entryIndex, rowIndex, { name: e.target.value })}
                  disabled={disabled}
                  placeholder="New option name"
                  className={`${INPUT_CLS} min-w-0 flex-1`}
                />
                {entry.rows.length > 1 && !disabled && (
                  <button
                    type="button"
                    onClick={() => removeRow(entryIndex, rowIndex)}
                    className="px-1 text-xs font-bold text-[#D72C0D]"
                  >
                    ✕
                  </button>
                )}
              </div>
            ) : (
              <MetafieldRowEditor
                key={rowIndex}
                row={row}
                disabled={disabled}
                onChange={(patch) => updateRow(entryIndex, rowIndex, patch)}
                onRemove={entry.rows.length > 1 ? () => removeRow(entryIndex, rowIndex) : null}
              />
            )
          )}

          {!disabled && (
            <button
              type="button"
              onClick={() => addRow(entryIndex)}
              className="text-xs font-semibold text-[#8A6116] hover:underline"
            >
              {isOptions ? "+ Add option" : "+ Add attribute"}
            </button>
          )}
        </div>
      ))}

      {!disabled && (
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={newProductId}
            onChange={(e) => setNewProductId(e.target.value)}
            placeholder="Add another product: gid://shopify/Product/…"
            className={`${INPUT_CLS} min-w-0 flex-1 font-mono`}
          />
          <button
            type="button"
            onClick={addProduct}
            className="shrink-0 rounded-md border border-[#E1E3E5] px-2.5 py-2 text-xs font-semibold hover:bg-[#F8F9FA]"
          >
            Add
          </button>
        </div>
      )}

      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve these changes to {changes.length} product(s).
      </ApprovalCheck>

      <ApplyBar
        status={status}
        message={message}
        ready={ready}
        label={`Apply to ${changes.length} product(s)`}
        onApply={() => ready && submit(changes)}
      />
    </PanelShell>
  );
}

/* -------------------------------------------------------------------------- */
/* Panel router                                                               */
/* -------------------------------------------------------------------------- */

function StoreFixPanel({ fixIssue, products }) {
  switch (fixIssue.panel) {
    case "policy":
      return <PolicyFixPanel fixIssue={fixIssue} />;
    case "contact":
      return <ContactFixPanel fixIssue={fixIssue} />;
    case "brand":
      return <BrandFixPanel fixIssue={fixIssue} />;
    case "guardrail":
      return <GuardrailFixPanel fixIssue={fixIssue} />;
    case "fulfillment":
      return <FulfillmentFixPanel fixIssue={fixIssue} />;
    case "norm_options":
      return <NormalizePanel fixIssue={fixIssue} mode="options" products={products} />;
    case "norm_metafields":
      return <NormalizePanel fixIssue={fixIssue} mode="metafields" products={products} />;
    default:
      return null;
  }
}

/* -------------------------------------------------------------------------- */
/* Fix modal                                                                  */
/* -------------------------------------------------------------------------- */

function StoreFixModal({ issue, onClose }) {
  const panels = issue.fixablePanels || [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="store-fix-title"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-[#E1E3E5] bg-white shadow-xl"
      >
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[#E1E3E5] bg-white p-5">
          <div>
            <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-[#FFF5E5] text-[#8A6116]">
              <Wrench className="h-4 w-4" />
            </div>
            <h2 id="store-fix-title" className="text-base font-bold text-[#202223]">
              {issue.enrichment}
            </h2>
            <p className="mt-1 text-xs text-[#6D7175]">
              Review and approve the changes before they are applied to your Shopify store.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close fix dialog"
            className="rounded-md p-2 text-[#6D7175] hover:bg-[#F1F2F3]"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="space-y-5 p-5">
          <div className="rounded-lg border border-[#E1E3E5] bg-[#FAFAFA] p-4">
            <div className="mb-2 flex items-center justify-between gap-3">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                Audit recommendation
              </span>
              <SeverityBadge priority={issue.priority} />
            </div>
            {issue.why_it_matters_for_agents && (
              <p className="text-xs leading-relaxed text-[#6D7175]">
                {issue.why_it_matters_for_agents}
              </p>
            )}
            {issue.example && (
              <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-[#6D7175]">
                {issue.example}
              </p>
            )}
            {issue.affectedProducts.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-2">
                {issue.affectedProducts.map((product) => (
                  <span
                    key={product.product_id}
                    className="rounded-full border border-[#E1E3E5] bg-white px-2.5 py-1 text-[11px] text-[#4A5568]"
                  >
                    {product.title || String(product.product_id)}
                  </span>
                ))}
              </div>
            )}
          </div>

          {panels.map((fixIssue) => (
            <div key={fixIssue.fix_action}>
              {panels.length > 1 && (
                <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                  {STORE_FIX_LABEL[fixIssue.fix_action] || "Fix"}
                </p>
              )}
              <StoreFixPanel fixIssue={fixIssue} products={issue.affectedProducts} />
            </div>
          ))}

          <div className="flex justify-end border-t border-[#E1E3E5] pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-[#E1E3E5] px-4 py-2 text-xs font-semibold text-[#202223] hover:bg-[#F8F9FA]"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

StoreFixModal.propTypes = {
  issue: PropTypes.shape({
    priority: PropTypes.string,
    enrichment: PropTypes.string,
    why_it_matters_for_agents: PropTypes.string,
    example: PropTypes.string,
    affectedProducts: PropTypes.array.isRequired,
    fixablePanels: PropTypes.array,
  }).isRequired,
  onClose: PropTypes.func.isRequired,
};

/* -------------------------------------------------------------------------- */
/* Issues page                                                                */
/* -------------------------------------------------------------------------- */

export default function Issues() {
  const navigate = useNavigate();
  const { shopDomain } = useRouteLoaderData("routes/app");

  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("All");
  const [expandedKey, setExpandedKey] = useState(null);
  const [selectedIssue, setSelectedIssue] = useState(null);

  useEffect(() => {
    if (!shopDomain) {
      setLoading(false);
      setReport(null);
      return;
    }

    let cancelled = false;

    async function loadAudit() {
      setLoading(true);
      setLoadError("");

      try {
        const response = await fetch(
          `${API_BASE}/audits/latest?shop_domain=${encodeURIComponent(shopDomain)}`
        );

        if (response.status === 404) {
          if (!cancelled) {
            setReport(null);
            setLoading(false);
          }
          return;
        }

        if (!response.ok) {
          throw new Error(`Failed to load the latest audit (${response.status}).`);
        }

        const data = await response.json();
        if (!cancelled) {
          setReport(data);
          setLoading(false);
        }
      } catch (error) {
        console.error("Failed to load latest audit:", error);
        if (!cancelled) {
          setReport(null);
          setLoadError(error.message || "Unable to load the latest audit.");
          setLoading(false);
        }
      }
    }

    loadAudit();
    return () => {
      cancelled = true;
    };
  }, [shopDomain]);

  const allIssues = useMemo(() => {
    const products = Array.isArray(report?.products) ? report.products : [];
    const storeRecs = Array.isArray(report?.store_level_recommendations)
      ? report.store_level_recommendations
      : [];
    const storeIssues = (Array.isArray(report?.issues) ? report.issues : []).filter(
      (issue) => issue?.scope === "store"
    );

    return storeRecs.map((recommendation, index) => {
      const checkId = resolveStoreCheckId(recommendation, storeIssues);
      const matched = checkId
        ? storeIssues.filter((issue) => issue.check_id === checkId)
        : [];

      return {
        key: `store-${index}`,
        priority: getPriority(recommendation.priority),
        enrichment: recommendation.enrichment || "Missing enrichment",
        why_it_matters_for_agents: recommendation.why_it_matters_for_agents || "",
        example: recommendation.example || "",
        affectedProducts: getAffectedProducts(recommendation, products),
        fixablePanels: getStoreFixablePanels(matched),
        hasMatchedIssues: matched.length > 0,
        raw: recommendation,
      };
    });
  }, [report?.store_level_recommendations, report?.products, report?.issues]);

  const highCount = allIssues.filter((i) => i.priority === "high").length;
  const mediumCount = allIssues.filter((i) => i.priority === "medium").length;
  const lowCount = allIssues.filter((i) => i.priority === "low").length;

  const filteredIssues = useMemo(() => {
    const query = search.trim().toLowerCase();

    return allIssues.filter((issue) => {
      const matchesSeverity =
        severity === "All" || issue.priority === severity.toLowerCase();

      const matchesSearch =
        !query ||
        issue.enrichment.toLowerCase().includes(query) ||
        issue.affectedProducts.some((product) =>
          String(product.title || "").toLowerCase().includes(query)
        );

      return matchesSeverity && matchesSearch;
    });
  }, [allIssues, search, severity]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-8">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#202223]">Issues</h1>
          <p className="mt-0.5 text-sm text-[#6D7175]">
            Store-level issues and recommendations identified in your latest audit.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#E1E3E5] bg-white px-3 py-1.5 text-xs shadow-sm">
          <span className="font-semibold text-[#202223]">Audit Status:</span>
          <span className="font-bold text-[#D72C0D]">{highCount} High</span>
          <span className="text-[#E1E3E5]">•</span>
          <span className="font-bold text-[#8A6116]">{mediumCount} Medium</span>
          <span className="text-[#E1E3E5]">•</span>
          <span className="font-bold text-[#6D7175]">{lowCount} Low</span>
        </div>
      </div>

      {/* Filters */}
      <div className="space-y-3 rounded-xl border border-[#E1E3E5] bg-white p-4 shadow-sm">
        <div className="flex flex-col items-stretch justify-between gap-3 md:flex-row md:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#6D7175]" />
            <input
              type="text"
              placeholder="Search issues or products..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-full rounded-md border border-[#E1E3E5] py-2 pl-9 pr-4 text-xs text-[#202223] outline-none placeholder:text-[#6D7175] focus:border-[#D97706] focus:ring-1 focus:ring-[#D97706]"
            />
          </div>

          <div className="flex shrink-0 items-center gap-1 rounded-md bg-[#F1F2F3] p-1">
            {["All", "High", "Medium", "Low"].map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setSeverity(value)}
                className={`cursor-pointer rounded px-3 py-1.5 text-xs font-semibold transition-colors ${
                  severity === value
                    ? "bg-white text-[#202223] shadow-sm"
                    : "text-[#6D7175] hover:text-[#202223]"
                }`}
              >
                {value}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Issues table */}
      <div className="overflow-hidden rounded-xl border border-[#E1E3E5] bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-[#E1E3E5] p-4 text-xs text-[#6D7175]">
          <div>
            Showing <span className="font-bold text-[#202223]">{filteredIssues.length}</span> issues
          </div>
          <div className="text-[11px] text-[#6D7175]">Expand an issue to view details</div>
        </div>

        {loading ? (
          <div className="py-16 text-center">
            <LoaderCircle className="mx-auto mb-3 h-7 w-7 animate-spin text-[#D97706]" />
            <p className="text-sm font-semibold text-[#202223]">Loading audit issues...</p>
          </div>
        ) : loadError ? (
          <div className="py-16 text-center">
            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#D72C0D]" />
            <p className="text-sm font-semibold text-[#202223]">Unable to load issues</p>
            <p className="mt-1 text-xs text-[#6D7175]">{loadError}</p>
          </div>
        ) : !report ? (
          <div className="py-16 text-center">
            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#E1E3E5]" />
            <p className="text-sm font-semibold text-[#202223]">No audit report available</p>
            <p className="mt-1 text-xs text-[#6D7175]">Run an audit from the Dashboard first.</p>
          </div>
        ) : filteredIssues.length === 0 ? (
          <div className="py-12 text-center text-[#6D7175]">
            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#E1E3E5]" />
            <p className="text-sm font-semibold text-[#202223]">No issues matching your filters</p>
            <p className="mt-1 text-xs">Try adjusting the search or severity filter.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead className="bg-[#F8F9FA] text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                <tr>
                  <th className="w-28 border-b border-[#E1E3E5] px-5 py-3">Severity</th>
                  <th className="border-b border-[#E1E3E5] px-5 py-3">Issue</th>
                  <th className="border-b border-[#E1E3E5] px-5 py-3">Affected Products</th>
                  <th className="border-b border-[#E1E3E5] px-5 py-3 text-right">View Issue</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-[#E1E3E5] text-xs">
                {filteredIssues.map((issue) => {
                  const isExpanded = expandedKey === issue.key;
                  const recommendation = issue.raw || {};
                  const fixable = issue.fixablePanels.length > 0;

                  const affectedLabel =
                    issue.affectedProducts.length > 0
                      ? `${issue.affectedProducts.length} product${
                          issue.affectedProducts.length === 1 ? "" : "s"
                        }`
                      : "Store-wide";

                  return (
                    <Fragment key={issue.key}>
                      <tr
                        className="group cursor-pointer transition-colors hover:bg-[#F9FAFB]"
                        onClick={() => setExpandedKey(isExpanded ? null : issue.key)}
                      >
                        <td className="whitespace-nowrap px-5 py-4 align-top">
                          <SeverityBadge priority={issue.priority} />
                        </td>

                        <td className="px-5 py-4 align-top">
                          <div className="font-semibold text-[#202223] transition-colors group-hover:text-[#D97706]">
                            {issue.enrichment}
                          </div>
                        </td>

                        <td className="whitespace-nowrap px-5 py-4 align-top">
                          <span className="inline-flex items-center gap-1.5 font-medium text-[#202223]">
                            {affectedLabel}
                          </span>
                        </td>

                        <td className="whitespace-nowrap px-5 py-4 text-right align-top">
                          <button
                            type="button"
                            onClick={(event) => {
                              event.stopPropagation();
                              setExpandedKey(isExpanded ? null : issue.key);
                            }}
                            className="inline-flex cursor-pointer items-center gap-1 rounded px-2.5 py-1 text-xs font-semibold text-[#8A6116] transition-colors hover:underline"
                          >
                            <span>{isExpanded ? "Hide Issue" : "View Issue"}</span>
                            {isExpanded ? (
                              <ChevronUp className="h-3.5 w-3.5" />
                            ) : (
                              <ChevronDown className="h-3.5 w-3.5" />
                            )}
                          </button>
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr>
                          <td
                            colSpan={4}
                            className="border-t border-[#F1F2F3] bg-[#FAFAFA] px-5 py-4"
                          >
                            {(issue.why_it_matters_for_agents ||
                              recommendation.description ||
                              recommendation.recommendation) && (
                              <div className="mt-3">
                                <p className="mb-1 text-xs font-semibold text-[#202223]">
                                  Recommendation
                                </p>
                                <p className="text-xs leading-relaxed text-[#6D7175]">
                                  {issue.why_it_matters_for_agents ||
                                    recommendation.description ||
                                    recommendation.recommendation}
                                </p>
                              </div>
                            )}

                            {issue.example && (
                              <div className="mt-3 whitespace-pre-line rounded-lg border-l-2 border-[#D97706] bg-white px-3 py-2 font-mono text-[11px] text-[#6D7175]">
                                {issue.example}
                              </div>
                            )}

                            {issue.affectedProducts.length > 0 && (
                              <div className="mt-3">
                                <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                                  Affected products
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  {issue.affectedProducts.map((product) => (
                                    <button
                                      key={product.product_id}
                                      type="button"
                                      onClick={(event) => {
                                        event.stopPropagation();
                                        navigate(
                                          `/app/products/detail?id=${encodeURIComponent(
                                            product.product_id
                                          )}`
                                        );
                                      }}
                                      className="rounded-full border border-[#E1E3E5] bg-white px-3 py-1 text-xs font-semibold text-[#8A6116] hover:underline"
                                    >
                                      {product.title || product.product_id}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            )}

                            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#E1E3E5] pt-3">
                              <p className="text-[11px] leading-relaxed text-[#6D7175]">
                                {fixable
                                  ? "Review and approve the changes before they are applied to your store."
                                  : "This issue can't be fixed automatically yet. Resolve it in your Shopify admin."}
                              </p>

                              {fixable && (
                                <button
                                  type="button"
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    setSelectedIssue(issue);
                                  }}
                                  className="inline-flex items-center gap-2 rounded-md bg-[#111111] px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-[#333333]"
                                >
                                  <Wrench className="h-3.5 w-3.5" />
                                  Fix Issue
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedIssue && (
        <StoreFixModal
          key={selectedIssue.key}
          issue={selectedIssue}
          onClose={() => setSelectedIssue(null)}
        />
      )}
    </div>
  );
}