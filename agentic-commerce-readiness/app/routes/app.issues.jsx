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
} from "lucide-react";
import { authenticate } from "../shopify.server";
import {
  FIELD_CLS,
  ApprovalCheck,
  FixStatusBadge,
  MetafieldRowEditor,
  buildMetaEntry,
  emptyMetaRow,
  errorText,
  failureMessages,
  findDuplicateMetafield,
  isLocked,
  isMetaRowValid,
} from "../components/fix-shared";

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

  const response = await fetch(`${API_BASE}/store/fix`, {
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

function resolveStoreCheckId(recommendation) {
  return recommendation?.check_id || recommendation?.fix_payload?.check_id || "";
}

const STORE_FIX_PANEL = {
  update_policy: "policy",
  update_store_contact: "contact",
  update_brand_information: "brand",
  configure_store_guardrail: "guardrail",
  update_fulfillment_information: "fulfillment",
  create_faq: "faq",
  normalize_option_structure: "norm_options",
  normalize_metafield_structure: "norm_metafields",
  normalize_attribute_formats: "norm_metafields",
  normalize_attribute_units: "norm_metafields",
};

const STORE_FIX_LABEL = {
  update_policy: "Store policies",
  update_store_contact: "Contact information",
  update_brand_information: "About / brand page",
  configure_store_guardrail: "Store disclosure",
  update_fulfillment_information: "Shipping & fulfillment",
  create_faq: "FAQ page",
  normalize_option_structure: "Option names",
  normalize_metafield_structure: "Missing attributes",
  normalize_attribute_formats: "Attribute formats",
  normalize_attribute_units: "Attribute units",
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
    case "faq_or_guidance":
      return "create_faq";
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
  return (issues || [])
    .map((issue) => {
      if (issue?.fix_mode === "unsupported") return null;

      const action = inferStoreFixAction(issue);
      const panel = STORE_FIX_PANEL[action];

      if (!issue.id || !issue.check_id || !issue.issue_type || !panel) {
        return null;
      }

      return { ...issue, fix_action: action, panel };
    })
    .filter(Boolean);
}

const escapeHtml = (value) =>
  String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");



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

function Notice({ tone = "warn", children }) {
  const styles =
    tone === "error"
      ? "bg-[#FFF0EF] text-[#D72C0D]"
      : tone === "info"
        ? "bg-[#F1F2F3] text-[#6D7175]"
        : "bg-[#FFF5E5] text-[#8A6116]";
  return (
    <p className={`rounded-md p-2 text-[11px] leading-relaxed ${styles}`}>{children}</p>
  );
}

function ApplyBar({
  status,
  message,
  errors = [],
  verify = false,
  ready,
  onApply,
  label = "Save changes",
}) {
  const locked = isLocked(status);
  const buttonText =
    status === "submitting"
      ? "Saving..."
      : status === "done"
        ? "Saved"
        : status === "partial"
          ? "Partly saved"
          : label;

  const messageColor =
    status === "error"
      ? "text-[#D72C0D]"
      : status === "partial"
        ? "text-[#8A6116]"
        : "text-[#065F46]";

  return (
    <div>
      <button
        type="button"
        onClick={onApply}
        disabled={locked || !ready}
        className="rounded-md bg-[#111111] px-3 py-1.5 text-xs font-bold text-white transition-opacity hover:bg-[#333333] disabled:cursor-not-allowed disabled:opacity-50"
      >
        {buttonText}
      </button>

      {message && <p className={`mt-1.5 text-xs ${messageColor}`}>{message}</p>}

      {errors.length > 0 && (
        <ul className="mt-1.5 list-disc space-y-0.5 pl-4 text-[11px] text-[#D72C0D]">
          {errors.map((error, index) => (
            <li key={index}>{error}</li>
          ))}
        </ul>
      )}

      {verify && (status === "done" || status === "partial") && (
        <p className="mt-1.5 text-[11px] text-[#6D7175]">
          Re-run the audit from the Dashboard to confirm this is resolved.
        </p>
      )}

      {status === "partial" && (
        <p className="mt-1 text-[11px] text-[#6D7175]">
          Saved changes are not rolled back. Review them in Shopify admin before trying again.
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
  const [state, setState] = useState({
    status: "idle",
    message: "",
    errors: [],
    verify: false,
  });

  const submit = (changes) => {
    setState({ status: "submitting", message: "", errors: [], verify: false });
    fetcher.submit(
      {
        issue_id: fixIssue.id,
        check_id: fixIssue.check_id,
        issue_type: fixIssue.issue_type,
        changes,
        merchant_approved: true,
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
    const errors = failureMessages(data);

    if (data.success) {
      setState({
        status: "done",
        message: data.message || "Changes saved.",
        errors: [],
        verify: data.verification_required !== false,
      });
    } else if (data.partial_success) {
      setState({
        status: "partial",
        message: data.message || "Some changes were saved and some failed.",
        errors,
        verify: true,
      });
    } else {
      setState({
        status: "error",
        message: errorText(data, "Failed to save changes."),
        errors,
        verify: false,
      });
    }
  }, [fetcher.state, fetcher.data]);

  return { submit, ...state };
}

/* -------------------------------------------------------------------------- */
/* Policies (update_policy)                                                   */
/* -------------------------------------------------------------------------- */

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
  const store = useStoreFix(fixIssue);
  const [rows, setRows] = useState(() => [
    { policy_type: inferPolicyType(fixIssue.issue_type), body: "" },
  ]);
  const [approved, setApproved] = useState(false);
  const disabled = isLocked(store.status);

  const update = (index, patch) =>
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  const valid = rows.filter((r) => r.body.trim());
  const types = valid.map((r) => r.policy_type);
  const hasDuplicateTypes = new Set(types).size !== types.length;
  const ready = approved && valid.length > 0 && !hasDuplicateTypes;

  const nextUnusedType = () =>
    POLICY_OPTIONS.find((o) => !rows.some((r) => r.policy_type === o.value))?.value ||
    "REFUND_POLICY";

  return (
    <PanelShell>
      <Notice>
        Saving replaces the <strong>entire</strong> existing policy with the text below. Paste the
        complete policy, not just the missing part. Write the real terms of your business; this
        text is not reviewed for legal compliance.
      </Notice>

      {rows.map((row, index) => (
        <div key={index} className="space-y-2 rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3">
          <div className="flex items-center gap-2">
            <select
              value={row.policy_type}
              onChange={(e) => update(index, { policy_type: e.target.value })}
              disabled={disabled}
              aria-label="Policy type"
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
            className={`${FIELD_CLS} resize-y`}
          />
        </div>
      ))}

      {hasDuplicateTypes && (
        <p className="text-[11px] text-[#D72C0D]">
          Each policy type can only be saved once per request. Remove the duplicate.
        </p>
      )}

      {!disabled && rows.length < POLICY_OPTIONS.length && (
        <button
          type="button"
          onClick={() => setRows((prev) => [...prev, { policy_type: nextUnusedType(), body: "" }])}
          className="rounded-md border border-[#E1E3E5] px-2.5 py-1.5 text-xs font-semibold hover:bg-[#F8F9FA]"
        >
          + Add policy
        </button>
      )}

      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve replacing the selected polic{valid.length === 1 ? "y" : "ies"} with this text on my
        store.
      </ApprovalCheck>

      <ApplyBar
        {...store}
        ready={ready}
        label="Approve and save"
        onApply={() =>
          ready &&
          store.submit(
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

/* -------------------------------------------------------------------------- */
/* Contact (update_store_contact)                                             */
/* -------------------------------------------------------------------------- */

function ContactFixPanel({ fixIssue }) {
  const store = useStoreFix(fixIssue);
  const [body, setBody] = useState("");
  const [approved, setApproved] = useState(false);
  const disabled = isLocked(store.status);
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
          placeholder={"Update your store's contact information..."}
          className={`${FIELD_CLS} resize-y`}
        />
        <p className="mt-1 text-[10px] text-[#6D7175]">
          Replaces your store's contact information policy. Include only details you want shown
          publicly.
        </p>
      </div>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve publishing this contact information on my store.
      </ApprovalCheck>
      <ApplyBar
        {...store}
        ready={ready}
        label="Approve and save"
        onApply={() => ready && store.submit([{ body: body.trim(), merchant_approved: true }])}
      />
    </PanelShell>
  );
}

/* -------------------------------------------------------------------------- */
/* About / brand page (update_brand_information)                              */
/* -------------------------------------------------------------------------- */

const PAGE_GID_RE = /^gid:\/\/shopify\/Page\/\d+$/;

function BrandFixPanel({ fixIssue }) {
  const store = useStoreFix(fixIssue);
  const [pageId, setPageId] = useState(fixIssue.page_id || "");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [publish, setPublish] = useState(false);
  const [approved, setApproved] = useState(false);
  const disabled = isLocked(store.status);

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
          placeholder="Enter the page ID"
          className={`${FIELD_CLS} font-mono`}
        />
        <p className={`mt-1 text-[10px] ${pageId && !pageOk ? "text-[#D72C0D]" : "text-[#6D7175]"}`}>
          This updates an existing page and can't create one. If you don't have an About page yet,
          create an empty one in Shopify admin first.
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
          className={FIELD_CLS}
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
          className={`${FIELD_CLS} resize-y`}
        />
        <p className="mt-1 text-[10px] text-[#6D7175]">Replaces the page's entire current content.</p>
      </div>
      <ApprovalCheck checked={publish} onChange={setPublish} disabled={disabled}>
        Publish the page if it is currently hidden.
      </ApprovalCheck>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve replacing this page's content with the text above.
      </ApprovalCheck>
      <ApplyBar
        {...store}
        ready={ready}
        label="Approve and save"
        onApply={() =>
          ready &&
          store.submit([
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
/* Store disclosure (configure_store_guardrail)                               */
/* -------------------------------------------------------------------------- */

function GuardrailFixPanel({ fixIssue }) {
  const store = useStoreFix(fixIssue);
  const [text, setText] = useState("");
  const [approved, setApproved] = useState(false);
  const disabled = isLocked(store.status);
  const ready = approved && text.trim();

  return (
    <PanelShell>
      <Notice>
        This saves a disclosure for AI shopping agents to read. It does <strong>not</strong> show a
        warning on your storefront and does not block under-age purchases. Age verification needs
        a separate tool.
      </Notice>
      <div>
        <FieldLabel>Disclosure text</FieldLabel>
        <textarea
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          placeholder="Enter disclosure text here..."
          className={`${FIELD_CLS} resize-y`}
        />
      </div>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve this disclosure text.
      </ApprovalCheck>
      <ApplyBar
        {...store}
        ready={ready}
        label="Approve and save"
        onApply={() => ready && store.submit([{ warning_text: text.trim(), merchant_approved: true }])}
      />
    </PanelShell>
  );
}

/* -------------------------------------------------------------------------- */
/* Fulfillment (update_fulfillment_information)                               */
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
  const store = useStoreFix(fixIssue);
  const [shippingBody, setShippingBody] = useState("");
  const [pickups, setPickups] = useState([]);
  const [showProfile, setShowProfile] = useState(false);
  const [profileId, setProfileId] = useState("");
  const [profileJson, setProfileJson] = useState("");
  const [approved, setApproved] = useState(false);
  const disabled = isLocked(store.status);

  const updatePickup = (index, patch) =>
    setPickups((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));

  const pickupComplete = (p) => p.locationId.trim() && p.instructions.trim();
  const pickupIncomplete = pickups.some(
    (p) => (p.locationId.trim() || p.instructions.trim()) && !pickupComplete(p)
  );

  const profileUsed = profileId.trim() || profileJson.trim();
  const profileObject = profileUsed ? parseJsonObject(profileJson) : null;
  const profileOk = !profileUsed || (profileId.trim() && profileObject);

  const change = { merchant_approved: true };
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

  const hasUpdate = Object.keys(change).length > 1;
  const ready = approved && hasUpdate && !pickupIncomplete && profileOk;

  return (
    <PanelShell>
      <Notice>
        Fill in any of the sections below. Updates are applied in order and are not rolled back if a
        later one fails. Policy text describes your shipping but doesn't change your actual
        shipping rates in Shopify.
      </Notice>

      <div>
        <FieldLabel>Shipping policy (delivery times, methods, regions)</FieldLabel>
        <textarea
          rows={6}
          value={shippingBody}
          onChange={(e) => setShippingBody(e.target.value)}
          disabled={disabled}
          placeholder="Complete shipping policy. Replaces the existing shipping policy."
          className={`${FIELD_CLS} resize-y`}
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
                placeholder="Enter location ID "
                aria-label="Location ID"
                className={`${FIELD_CLS} font-mono`}
              />
              <select
                value={p.pickupTime}
                onChange={(e) => updatePickup(index, { pickupTime: e.target.value })}
                disabled={disabled}
                aria-label="Pickup ready time"
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
              placeholder="Update pickup instructions..."
              className={`${FIELD_CLS} resize-y`}
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
            + Add pickup location
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
              placeholder="Enter profile ID"
              aria-label="Delivery profile ID"
              className={`${FIELD_CLS} font-mono`}
            />
            <textarea
              rows={6}
              value={profileJson}
              onChange={(e) => setProfileJson(e.target.value)}
              disabled={disabled}
              spellCheck={false}
              aria-label="Delivery profile update (JSON)"
              placeholder={'DeliveryProfileInput as JSON'}
              className={`${FIELD_CLS} resize-y font-mono`}
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
        {...store}
        ready={ready}
        label="Approve and save"
        onApply={() => ready && store.submit([change])}
      />
    </PanelShell>
  );
}

/* -------------------------------------------------------------------------- */
/* FAQ page (create_faq)                                                      */
/* -------------------------------------------------------------------------- */

const emptyFaqRow = () => ({ question: "", answer: "" });

function buildFaqHtml(rows) {
  return rows
    .map((row) => {
      const answer = row.answer
        .trim()
        .split(/\n{2,}/)
        .map((paragraph) => `<p>${escapeHtml(paragraph).replace(/\n/g, "<br>")}</p>`)
        .join("");
      return `<h3>${escapeHtml(row.question.trim())}</h3>${answer}`;
    })
    .join("\n");
}

function FaqFixPanel({ fixIssue }) {
  const store = useStoreFix(fixIssue);
  const [title, setTitle] = useState("Frequently asked questions");
  const [rows, setRows] = useState([emptyFaqRow()]);
  const [publish, setPublish] = useState(false);
  const [approved, setApproved] = useState(false);
  const disabled = isLocked(store.status);

  const update = (index, patch) =>
    setRows((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));

  const valid = rows.filter((r) => r.question.trim() && r.answer.trim());
  const incomplete = rows.some(
    (r) => (r.question.trim() || r.answer.trim()) && !(r.question.trim() && r.answer.trim())
  );
  const ready = approved && title.trim() && valid.length > 0 && !incomplete;

  return (
    <PanelShell>
      <Notice tone="info">
        This creates a <strong>new page</strong> each time it is saved. It isn't added to your
        navigation menu, and it is saved as a hidden draft unless you choose to publish it. Write
        answers that are true for your store.
      </Notice>

      <div>
        <FieldLabel>Page title</FieldLabel>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={disabled}
          className={FIELD_CLS}
        />
      </div>

      {rows.map((row, index) => (
        <div key={index} className="space-y-2 rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={row.question}
              onChange={(e) => update(index, { question: e.target.value })}
              disabled={disabled}
              placeholder="Question"
              aria-label="Question"
              className={FIELD_CLS}
            />
            {rows.length > 1 && !disabled && (
              <button
                type="button"
                onClick={() => setRows((prev) => prev.filter((_, i) => i !== index))}
                aria-label="Remove question"
                className="px-1 text-xs font-bold text-[#D72C0D]"
              >
                ✕
              </button>
            )}
          </div>
          <textarea
            rows={3}
            value={row.answer}
            onChange={(e) => update(index, { answer: e.target.value })}
            disabled={disabled}
            placeholder="Answer"
            aria-label="Answer"
            className={`${FIELD_CLS} resize-y`}
          />
        </div>
      ))}

      {incomplete && (
        <p className="text-[11px] text-[#D72C0D]">Each question needs an answer, and each answer a question.</p>
      )}

      {!disabled && rows.length < 20 && (
        <button
          type="button"
          onClick={() => setRows((prev) => [...prev, emptyFaqRow()])}
          className="rounded-md border border-[#E1E3E5] px-2.5 py-1.5 text-xs font-semibold hover:bg-[#F8F9FA]"
        >
          + Add question
        </button>
      )}

      <ApprovalCheck checked={publish} onChange={setPublish} disabled={disabled}>
        Publish the page now. Otherwise it is saved as a draft.
      </ApprovalCheck>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve creating this FAQ page with the questions and answers above.
      </ApprovalCheck>

      {store.status === "error" && (
        <p className="text-[11px] text-[#6D7175]">
          If this failed with a timeout, check your Pages in Shopify admin before trying again so you
          don't create a duplicate.
        </p>
      )}

      <ApplyBar
        {...store}
        ready={ready}
        label="Approve and create page"
        onApply={() =>
          ready &&
          store.submit([
            {
              title: title.trim(),
              body: buildFaqHtml(valid),
              publish,
              merchant_approved: true,
            },
          ])
        }
      />
    </PanelShell>
  );
}

/* -------------------------------------------------------------------------- */
/* Catalog consistency (normalize_*)                                          */
/* -------------------------------------------------------------------------- */

const NORMALIZE_HINTS = {
  normalize_option_structure:
    "Rename each product's options so they use the same names across your catalog. Change only the names you want to update.",
  normalize_metafield_structure:
    "Add the missing attributes for each product. Use the exact namespace and key your other products use, and enter the real value for each product.",
  normalize_attribute_formats:
    "Enter each value in the canonical format used across your catalog.",
  normalize_attribute_units:
    "Enter values already converted to the unit you want to standardize on. Nothing is converted for you.",
};

function NormalizePanel({ fixIssue, mode, products }) {
  const isOptions = mode === "options";
  const store = useStoreFix(fixIssue);
  const disabled = isLocked(store.status);

  const [entries, setEntries] = useState(() =>
    products.map((p) => ({
      product_id: String(p.product_id),
      title: p.title || "",
      rows: isOptions
        ? (Array.isArray(p.options) ? p.options : [])
            .filter((o) => o?.id)
            .map((o) => ({ id: o.id, current: o.name || "", name: o.name || "" }))
        : [emptyMetaRow()],
    }))
  );
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
      prev.map((e, i) => (i === entryIndex ? { ...e, rows: [...e.rows, emptyMetaRow()] } : e))
    );

  const removeRow = (entryIndex, rowIndex) =>
    setEntries((prev) =>
      prev.map((e, i) =>
        i === entryIndex && e.rows.length > 1
          ? { ...e, rows: e.rows.filter((_, ri) => ri !== rowIndex) }
          : e
      )
    );

  const validRows = (entry) =>
    isOptions
      ? entry.rows.filter((r) => r.name.trim() && r.name.trim() !== r.current.trim())
      : entry.rows.filter(isMetaRowValid);

  const duplicates = entries
    .map((entry) => (isOptions ? null : findDuplicateMetafield(entry.rows)))
    .filter(Boolean);

  const changes = entries
    .map((entry) => {
      const rows = validRows(entry);
      if (rows.length === 0) return null;
      return isOptions
        ? {
            product_id: entry.product_id,
            options: rows.map((r) => ({ id: r.id, name: r.name.trim() })),
          }
        : { product_id: entry.product_id, metafields: rows.map(buildMetaEntry) };
    })
    .filter(Boolean);

  const ready = approved && changes.length > 0 && duplicates.length === 0;

  return (
    <PanelShell>
      <p className="text-[11px] leading-relaxed text-[#6D7175]">
        {NORMALIZE_HINTS[fixIssue.fix_action]}
      </p>

      {entries.length === 0 && (
        <Notice tone="info">
          The audit didn't list which products are affected. Re-run the audit and try again.
        </Notice>
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

          {isOptions && entry.rows.length === 0 && (
            <p className="text-[11px] text-[#6D7175]">
              Option details aren't available for this product in the audit. Re-run the audit, or
              rename the option from the product's page.
            </p>
          )}

          {entry.rows.map((row, rowIndex) =>
            isOptions ? (
              <div key={row.id} className="flex items-center gap-2">
                <span className="w-1/3 truncate text-xs text-[#6D7175]" title={row.current}>
                  {row.current || "(unnamed)"}
                </span>
                <input
                  type="text"
                  value={row.name}
                  onChange={(e) => updateRow(entryIndex, rowIndex, { name: e.target.value })}
                  disabled={disabled}
                  aria-label={`New name for option ${row.current}`}
                  placeholder="New option name"
                  className={`${FIELD_CLS} min-w-0 flex-1`}
                />
              </div>
            ) : (
              <MetafieldRowEditor
                key={rowIndex}
                row={row}
                showNamespace
                disabled={disabled}
                onChange={(patch) => updateRow(entryIndex, rowIndex, patch)}
                onRemove={entry.rows.length > 1 ? () => removeRow(entryIndex, rowIndex) : null}
              />
            )
          )}

          {!isOptions && !disabled && (
            <button
              type="button"
              onClick={() => addRow(entryIndex)}
              className="text-xs font-semibold text-[#8A6116] hover:underline"
            >
              + Add attribute
            </button>
          )}
        </div>
      ))}

      {duplicates.length > 0 && (
        <p className="text-[11px] text-[#D72C0D]">
          Duplicate attribute for one product: {duplicates.join(", ")}. Each namespace and key can
          appear once per product.
        </p>
      )}

      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve these changes to {changes.length} product{changes.length === 1 ? "" : "s"}.
      </ApprovalCheck>

      <ApplyBar
        {...store}
        ready={ready}
        label={`Approve and save ${changes.length} product${changes.length === 1 ? "" : "s"}`}
        onApply={() => ready && store.submit(changes)}
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
    case "faq":
      return <FaqFixPanel fixIssue={fixIssue} />;
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

function modeIntro(panels) {
  const mode = panels.find((p) => p.fix_mode)?.fix_mode;
  if (mode === "approval") return "Review the change below, then approve it before it's saved to your store.";
  if (mode === "user_input") return "We need a few details from you. Fill them in, then approve the change.";
  return "Review and approve the changes before they are applied to your Shopify store.";
}

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
            <p className="mt-1 text-xs text-[#6D7175]">{modeIntro(panels)}</p>
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

          {panels.map((fixIssue) => {
            const issueProducts = Array.isArray(fixIssue.affected_product_ids)
              ? issue.affectedProducts.filter((product) =>
                  fixIssue.affected_product_ids.map(String).includes(String(product.product_id))
                )
              : issue.affectedProducts;

            return (
              <div key={fixIssue.id} className="space-y-2 rounded-lg border border-[#E1E3E5] p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-xs font-bold text-[#202223]">
                      {STORE_FIX_LABEL[fixIssue.fix_action] || "Fix"}
                    </p>
                    <p className="mt-1 text-[11px] text-[#6D7175]">
                      {prettyLabel(fixIssue.issue_type)}
                    </p>
                  </div>
                  <FixStatusBadge status={fixIssue.fix_status} />
                </div>

                <StoreFixPanel fixIssue={fixIssue} products={issueProducts} />
              </div>
            );
          })}

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
      const checkId = resolveStoreCheckId(recommendation);

      const matched = checkId
        ? storeIssues.filter((issue) => String(issue.check_id) === String(checkId))
        : [];

      const fixablePanels = getStoreFixablePanels(matched);

      return {
        key: `store-${index}`,
        priority: getPriority(recommendation.priority),
        enrichment: recommendation.enrichment || "Missing enrichment",
        why_it_matters_for_agents: recommendation.why_it_matters_for_agents || "",
        example: recommendation.example || "",
        affectedProducts: getAffectedProducts(recommendation, products),
        checkId,
        fixablePanels,
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
      const matchesSeverity = severity === "All" || issue.priority === severity.toLowerCase();

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
                  const fixStatuses = [
                    ...new Set(issue.fixablePanels.map((p) => p.fix_status).filter(Boolean)),
                  ];

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
                          {fixStatuses.length > 0 && (
                            <div className="mt-1.5 flex flex-wrap gap-1.5">
                              {fixStatuses.map((s) => (
                                <FixStatusBadge key={s} status={s} />
                              ))}
                            </div>
                          )}
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
                                  Fix issue
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