// app/routes/app.products_.$id.jsx 

import { useEffect, useState } from "react";
import {
  useFetcher,
  useNavigate,
  useSearchParams,
  useRouteLoaderData,
} from "react-router";
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  AlertOctagon,
  AlertCircle,
  Package,
  Wrench,
} from "lucide-react";
import { authenticate } from "../shopify.server";
import {
  ApprovalCheck,
  FixStatusBadge,
  METAFIELD_TYPES,
  METAFIELD_TYPE_HELP,
  MetafieldRowEditor,
  buildMetaEntry,
  emptyMetaRow,
  errorText,
  findDuplicateMetafield,
  isLocked,
  isMetaRowValid,
  isValidGtin,
} from "../components/fix-shared";

const API_BASE = "https://geo.properoapps.in/api";


const ALLOWED_ENDPOINTS = new Set(["/products/fix", "/products/variant-options-state"]);



const FIX_ACTION_PANEL = {
  update_product_handle: "handle",
  set_metafield: "metafields",
  set_product_type: "product_type",
  update_product_type: "product_type",
  update_product_description: "description",
  review_product_claim: "review_claim",
  update_product_title: "title",
  rename_product_option: "rename_option",
  generate_sku: "sku",
  update_sku: "sku",
  set_gtin: "gtin",
  set_mpn: "mpn",
  fix_variant_options: "variant_options",
  set_variant_price: "price",
  set_product_image: "image",
  set_product_image_alt: "image_alt",
  set_guardrail_metafield: "guardrail",
};

const FIX_ACTION_LABEL = {
  update_product_handle: "Product URL",
  set_metafield: "Attributes",
  set_product_type: "Product type",
  update_product_type: "Product type",
  update_product_description: "Description",
  review_product_claim: "Product claim",
  update_product_title: "Title",
  rename_product_option: "Option name",
  generate_sku: "SKU",
  update_sku: "SKU",
  set_gtin: "GTIN",
  set_mpn: "MPN",
  fix_variant_options: "Option values",
  set_variant_price: "Price",
  set_product_image: "Product image",
  set_product_image_alt: "Image alt text",
  set_guardrail_metafield: "Age and warning details",
};

const VARIANT_OPTIONS_SOLVABLE = new Set([
  "incomplete_selected_options",
  "inconsistent_variant_options",
  "inconsistent_option_values",
  "generic_option_value",
]);

function getFixablePanels(issues) {
  const seen = new Set();
  const out = [];
  for (const issue of issues || []) {
    if (issue.fix_mode === "unsupported") continue;
    const panel = FIX_ACTION_PANEL[issue.fix_action];
    if (!panel || seen.has(issue.fix_action)) continue;
    if (panel === "variant_options" && !VARIANT_OPTIONS_SOLVABLE.has(issue.issue_type)) continue;
    seen.add(issue.fix_action);
    out.push({ ...issue, panel });
  }
  return out;
}

function getProductStatus(product) {
  const issues = product?.missing_enrichments || [];

  const hasHigh = issues.some((item) => item.priority === "high");
  const hasOtherIssues = issues.some(
    (item) => item.priority === "medium" || item.priority === "low"
  );

  if (hasHigh) {
    return {
      label: "Critical",
      text: "text-red-700",
      bg: "bg-red-50",
      ring: "border-red-200",
      icon: AlertOctagon,
      blurb:
        "AI shopping agents may misrepresent or fail to recommend this product until high-priority gaps are fixed.",
    };
  }

  if (hasOtherIssues) {
    return {
      label: "Needs Attention",
      text: "text-orange-700",
      bg: "bg-orange-50",
      ring: "border-orange-200",
      icon: AlertTriangle,
      blurb:
        "This product is discoverable, but addressing the remaining gaps will improve how confidently agents can act on it.",
    };
  }

  return {
    label: "Ready",
    text: "text-[var(--app-green)]",
    bg: "bg-green-50",
    ring: "border-green-200",
    icon: CheckCircle2,
    blurb: "This product currently meets the checks included in the audit.",
  };
}

function SeverityBadge({ priority }) {
  if (priority === "high") {
    return (
      <span className="rounded-full bg-red-50 px-2.5 py-1 text-[10px] font-bold text-red-700">
        High
      </span>
    );
  }

  if (priority === "low") {
    return (
      <span className="rounded-full bg-green-50 px-2.5 py-1 text-[10px] font-bold text-[var(--app-green)]">
        Low
      </span>
    );
  }

  return (
    <span className="rounded-full bg-orange-50 px-2.5 py-1 text-[10px] font-bold text-orange-700">
      Medium
    </span>
  );
}


function useApplyFix({ issue, productId }) {
  const fetcher = useFetcher();
  const [state, setState] = useState({ status: "idle", message: "", verify: false });

  const submit = (extraFields) => {
    setState({ status: "submitting", message: "", verify: false });

    fetcher.submit(
      {
        product_id: productId,
        issue_id: issue.id,
        check_id: issue.check_id,
        issue_type: issue.issue_type,
        ...extraFields,
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

    if (data.success) {
      setState({
        status: "done",
        message: data.message || "Changes saved.",
        verify: data.verification_required !== false,
      });
    } else {
      setState({
        status: "error",
        message: errorText(data, "Failed to save changes."),
        verify: false,
      });
    }
  }, [fetcher.state, fetcher.data]);

  return { submit, ...state };
}



function EmptyPanel({ children }) {
  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-white p-3">
      <p className="text-xs text-[var(--app-muted)]">{children}</p>
    </div>
  );
}

function Notice({ children, tone = "warn" }) {
  const cls =
    tone === "info"
      ? "bg-[var(--app-bg)] text-[var(--app-muted)]"
      : "bg-orange-50 text-orange-800";
  return <p className={`rounded-md p-2 text-[11px] leading-relaxed ${cls}`}>{children}</p>;
}

function StatusMessage({ status, message, verify, className = "mt-1" }) {
  if (!message) return null;
  return (
    <div className={className}>
      <p className={`text-xs ${status === "error" ? "text-red-600" : "text-[var(--app-green)]"}`}>
        {message}
      </p>
      {status === "done" && verify && (
        <p className="mt-1 text-[11px] text-[var(--app-muted)]">
          Re-run the audit to confirm this is resolved.
        </p>
      )}
    </div>
  );
}

function ApplyButton({ status, ready, onClick, label = "Approve and save", busy = "Saving...", done = "Saved", className = "" }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={isLocked(status) || !ready}
      className={`rounded-md bg-[var(--app-green)] px-3 py-1.5 text-xs font-bold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
    >
      {status === "submitting" ? busy : status === "done" ? done : label}
    </button>
  );
}

const INPUT_CLS =
  "rounded-md border border-[var(--app-border)] px-2.5 py-1.5 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60";

const LABEL_CLS =
  "block text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]";

const PANEL_CLS = "space-y-3 rounded-lg border border-[var(--app-border)] bg-white p-3";

/* -------------------------------------------------------------------------- */
/* Fix panels                                                                 */
/* -------------------------------------------------------------------------- */

const HANDLE_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

function HandleFixPanel({ issue, productId }) {
  const [handle, setHandle] = useState(issue.suggested_handle || "");
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);
  const clean = handle.trim().toLowerCase();
  const valid = HANDLE_RE.test(clean);

  return (
    <div className={PANEL_CLS}>
      <div>
        <label className={LABEL_CLS}>Product URL handle</label>
        <input
          type="text"
          value={handle}
          onChange={(e) => setHandle(e.target.value)}
          disabled={disabled}
          placeholder="product-handle-slug"
          className={`mt-2 w-full font-mono ${INPUT_CLS}`}
        />
        <p className={`mt-1 text-[11px] ${handle && !valid ? "text-red-600" : "text-[var(--app-muted)]"}`}>
          {handle && !valid
            ? "Use lowercase letters, numbers and single hyphens only."
            : `New URL: /products/${clean || "…"}`}
        </p>
      </div>
      <Notice>
        Changing the handle changes the product's web address. Old links, bookmarks and search results
        may stop working unless you add a redirect in Shopify admin.
      </Notice>
      <ApplyButton
        status={fix.status}
        ready={valid}
        onClick={() => valid && fix.submit({ handle: clean })}
      />
      <StatusMessage {...fix} />
    </div>
  );
}

function MetafieldsFixPanel({ issue, productId }) {
  const [rows, setRows] = useState([emptyMetaRow()]);
  const [showTypeGuide, setShowTypeGuide] = useState(false);
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);

  const updateRow = (index, patch) =>
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const validRows = rows.filter(isMetaRowValid);
  const duplicate = findDuplicateMetafield(rows);
  const ready = validRows.length > 0 && !duplicate && validRows.length <= 25;

  return (
    <div className={PANEL_CLS}>
      <label className={LABEL_CLS}>Product attributes</label>
      <p className="text-[11px] text-[var(--app-muted)]">
        Enter the real values for this product. Only rows you complete are saved.
      </p>

      <div className="space-y-3">
        {rows.map((row, index) => (
          <MetafieldRowEditor
            key={index}
            row={row}
            disabled={disabled}
            onChange={(patch) => updateRow(index, patch)}
            onRemove={rows.length > 1 ? () => setRows((prev) => prev.filter((_, i) => i !== index)) : null}
          />
        ))}
      </div>

      {duplicate && (
        <p className="text-[11px] text-red-600">
          "{duplicate.split(".").slice(1).join(".")}" appears more than once. Each attribute can be set once.
        </p>
      )}

      <div className="flex items-center justify-between gap-3">
        {!disabled && rows.length < 25 ? (
          <button
            type="button"
            onClick={() => setRows((prev) => [...prev, emptyMetaRow()])}
            className="rounded-md border border-[var(--app-border)] px-2.5 py-1.5 text-xs font-semibold text-[var(--app-text)] hover:bg-[var(--app-bg)]"
          >
            + Add attribute
          </button>
        ) : (
          <span />
        )}
        <ApplyButton
          status={fix.status}
          ready={ready}
          label={`Approve and save ${validRows.length || ""} attribute${validRows.length === 1 ? "" : "s"}`.replace("  ", " ")}
          onClick={() => ready && fix.submit({ attributes: validRows.map(buildMetaEntry) })}
        />
      </div>

      <div>
        <button
          type="button"
          onClick={() => setShowTypeGuide((v) => !v)}
          className="text-xs font-semibold text-[var(--app-muted)] underline hover:text-[var(--app-text)]"
        >
          {showTypeGuide ? "Hide type guide" : "What type should I pick?"}
        </button>
      </div>

      {showTypeGuide && (
        <div className="rounded-md border border-[var(--app-border)] bg-[var(--app-bg)] p-3 text-[11px] leading-relaxed text-[var(--app-muted)]">
          <ul className="space-y-1.5">
            {METAFIELD_TYPES.map((type) => (
              <li key={type.value}>
                <span className="font-mono font-semibold text-[var(--app-text)]">{type.value}</span>
                {" – "}
                {METAFIELD_TYPE_HELP[type.value]}
              </li>
            ))}
          </ul>
        </div>
      )}

      <StatusMessage {...fix} className="" />
    </div>
  );
}


function TextFixPanel({
  issue,
  productId,
  field,
  label,
  placeholder,
  multiline,
  current,
  replaceWarning,
}) {
  const [value, setValue] = useState("");
  const [approved, setApproved] = useState(false);
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);
  const Field = multiline ? "textarea" : "input";
  const ready = value.trim() && (!replaceWarning || approved);

  return (
    <div className={PANEL_CLS}>
      <div>
        <label className={LABEL_CLS}>{label}</label>
        {current && (
          <p className="mt-1.5 text-[11px] text-[var(--app-muted)]">
            Current: <span className="text-[var(--app-text)]">{current}</span>
          </p>
        )}
        <Field
          {...(!multiline && { type: "text" })}
          {...(multiline && { rows: 6 })}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          placeholder={placeholder || `Enter ${label.toLowerCase()}`}
          className={`mt-2 w-full ${INPUT_CLS} ${multiline ? "resize-y py-2" : ""}`}
        />
      </div>
      {replaceWarning && (
        <>
          <Notice>{replaceWarning}</Notice>
          <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
            I approve replacing the current {label.toLowerCase()} with this text.
          </ApprovalCheck>
        </>
      )}
      <ApplyButton
        status={fix.status}
        ready={ready}
        onClick={() => ready && fix.submit({ [field]: value.trim() })}
      />
      <StatusMessage {...fix} />
    </div>
  );
}

function ReviewClaimFixPanel({ issue, productId }) {
  const [value, setValue] = useState("");
  const [approved, setApproved] = useState(false);
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);
  const ready = value.trim() && approved;

  return (
    <div className={PANEL_CLS}>
      <Notice>
        Rewrite the description so every claim is one you can back up, or remove it. Saving replaces
        the <strong>whole</strong> description. It does not certify the claim and does not remove it
        from ads, product feeds, theme content or metafields, so check those separately.
      </Notice>
      <div>
        <label className={LABEL_CLS}>Reviewed replacement description</label>
        <textarea
          rows={7}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          placeholder="Complete description, with the claim reworded or removed..."
          className={`mt-2 w-full resize-y py-2 ${INPUT_CLS}`}
        />
      </div>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I have reviewed this text, can support what it says, and approve saving it as the description.
      </ApprovalCheck>
      <ApplyButton
        status={fix.status}
        ready={ready}
        onClick={() => ready && fix.submit({ description_html: value.trim() })}
      />
      <StatusMessage {...fix} />
    </div>
  );
}

function GuardrailFixPanel({ issue, productId }) {
  const [age, setAge] = useState("");
  const [warning, setWarning] = useState("");
  const [approved, setApproved] = useState(false);
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);

  const ageText = age.trim();
  const ageNumber = Number(ageText);
  const ageOk = ageText === "" || (Number.isInteger(ageNumber) && ageNumber >= 0 && ageNumber <= 120);
  const hasInput = ageText !== "" || warning.trim() !== "";
  const ready = approved && hasInput && ageOk;

  return (
    <div className={PANEL_CLS}>
      <Notice>
        This saves age and warning details on the product so AI agents can read them. It does{" "}
        <strong>not</strong> show a warning on your storefront and does not stop anyone from buying.
      </Notice>
      <div>
        <label className={LABEL_CLS}>Minimum age (optional)</label>
        <input
          type="number"
          min="0"
          max="120"
          step="1"
          value={age}
          onChange={(e) => setAge(e.target.value)}
          disabled={disabled}
          className={`mt-2 w-32 ${INPUT_CLS}`}
        />
        {!ageOk && <p className="mt-1 text-[11px] text-red-600">Enter a whole number from 0 to 120.</p>}
      </div>
      <div>
        <label className={LABEL_CLS}>Product warning (optional)</label>
        <textarea
          rows={3}
          value={warning}
          onChange={(e) => setWarning(e.target.value)}
          disabled={disabled}
          placeholder="Update Product warning..."
          className={`mt-2 w-full resize-y py-2 ${INPUT_CLS}`}
        />
      </div>
      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I confirm these details are accurate for this product.
      </ApprovalCheck>
      <ApplyButton
        status={fix.status}
        ready={ready}
        onClick={() =>
          ready &&
          fix.submit({
            ...(ageText !== "" && { minimum_age: ageNumber }),
            ...(warning.trim() && { warning_text: warning.trim() }),
          })
        }
      />
      <StatusMessage {...fix} />
    </div>
  );
}

function RenameOptionFixPanel({ issue, productId }) {
  const options = issue.affected_options || [];

  if (options.length === 0) {
    return <EmptyPanel>No specific option identified for this issue.</EmptyPanel>;
  }

  return (
    <div className="space-y-3">
      {options.map((option) => (
        <RenameOneOption key={option.id} option={option} issue={issue} productId={productId} />
      ))}
    </div>
  );
}

function RenameOneOption({ option, issue, productId }) {
  const [value, setValue] = useState("");
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);
  const ready = value.trim() && value.trim() !== (option.name || "");

  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-white p-3">
      <p className="text-xs font-semibold text-[var(--app-text)]">
        Current name: <span className="font-mono">{option.name || "(unnamed)"}</span>
      </p>
      {option.values?.length > 0 && (
        <p className="mt-0.5 text-[11px] text-[var(--app-muted)]">Values: {option.values.join(", ")}</p>
      )}
      <div className="mt-2 flex items-center gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          aria-label="New option name"
          placeholder="What these values describe"
          className={`min-w-0 flex-1 ${INPUT_CLS}`}
        />
        <ApplyButton
          status={fix.status}
          ready={ready}
          label="Approve and rename"
          busy="Renaming..."
          done="Renamed"
          className="shrink-0"
          onClick={() => ready && fix.submit({ option_id: option.id, new_name: value.trim() })}
        />
      </div>
      <StatusMessage {...fix} />
    </div>
  );
}

function SkuFixPanel({ issue, productId }) {
  const variants = issue.affected_variants || [];
  const [values, setValues] = useState(() =>
    Object.fromEntries(variants.map((v) => [v.id, v.suggested_sku || v.sku || ""]))
  );
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);

  if (variants.length === 0) {
    return <EmptyPanel>No specific variant identified for this issue.</EmptyPanel>;
  }

  const ready = variants.filter((v) => values[v.id]?.trim());
  const lowered = ready.map((v) => values[v.id].trim().toLowerCase());
  const hasDuplicates = new Set(lowered).size !== lowered.length;

  return (
    <div className={PANEL_CLS}>
      <label className={LABEL_CLS}>SKU for each variant</label>
      <p className="text-[11px] text-[var(--app-muted)]">
        Edit any suggested value. Shopify doesn't enforce unique SKUs, so make sure these don't clash
        with SKUs in your inventory or order-management system.
      </p>

      {variants.map((v) => (
        <div key={v.id} className="flex items-center gap-2">
          {v.image_url && <img src={v.image_url} alt="" className="h-8 w-8 shrink-0 rounded object-cover" />}
          <span className="min-w-0 flex-1 truncate text-xs text-[var(--app-muted)]">
            {v.title || v.selected_options?.map((o) => o.value).join(" / ") || "Variant"}
          </span>
          <input
            type="text"
            value={values[v.id] || ""}
            onChange={(e) => setValues((prev) => ({ ...prev, [v.id]: e.target.value }))}
            disabled={disabled}
            aria-label="SKU"
            className="w-36 shrink-0 rounded-md border border-[var(--app-border)] px-2 py-1 font-mono text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
          />
        </div>
      ))}

      {hasDuplicates && (
        <p className="text-[11px] text-red-600">Two variants have the same SKU. Make each one different.</p>
      )}

      <ApplyButton
        status={fix.status}
        ready={ready.length > 0 && !hasDuplicates}
        label={`Approve and save ${ready.length} SKU${ready.length === 1 ? "" : "s"}`}
        onClick={() =>
          ready.length > 0 &&
          !hasDuplicates &&
          fix.submit({ variants: ready.map((v) => ({ id: v.id, sku: values[v.id].trim() })) })
        }
      />
      <StatusMessage {...fix} className="" />
    </div>
  );
}

function PriceFixPanel({ issue, productId }) {
  const variants = issue.affected_variants || [];
  const [values, setValues] = useState(() =>
    Object.fromEntries(variants.map((v) => [v.id, Number(v.price) > 0 ? String(v.price) : ""]))
  );
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);

  if (variants.length === 0) {
    return <EmptyPanel>No specific variant identified for this issue.</EmptyPanel>;
  }

  const isValid = (v) => {
    const raw = (values[v.id] || "").trim();
    const n = Number(raw);
    return raw !== "" && Number.isFinite(n) && n > 0;
  };
  const ready = variants.filter(isValid);

  return (
    <div className={PANEL_CLS}>
      <label className={LABEL_CLS}>Price for each variant</label>
      <p className="text-[11px] text-[var(--app-muted)]">
        Enter the price in your store's currency. Prices must be greater than zero.
      </p>

      {variants.map((v) => (
        <div key={v.id} className="flex items-center gap-2">
          {v.image_url && <img src={v.image_url} alt="" className="h-8 w-8 shrink-0 rounded object-cover" />}
          <span className="min-w-0 flex-1 truncate text-xs text-[var(--app-muted)]">
            {v.title || v.selected_options?.map((o) => o.value).join(" / ") || "Variant"}
            {v.sku && <span className="font-mono"> · {v.sku}</span>}
          </span>
          <input
            type="number"
            step="0.01"
            min="0"
            value={values[v.id] || ""}
            onChange={(e) => setValues((prev) => ({ ...prev, [v.id]: e.target.value }))}
            disabled={disabled}
            placeholder="0.00"
            aria-label="Price"
            className="w-28 shrink-0 rounded-md border border-[var(--app-border)] px-2 py-1 font-mono text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
          />
        </div>
      ))}

      <ApplyButton
        status={fix.status}
        ready={ready.length > 0}
        label={`Approve and save ${ready.length} price${ready.length === 1 ? "" : "s"}`}
        onClick={() =>
          ready.length > 0 &&
          fix.submit({ variants: ready.map((v) => ({ id: v.id, price: values[v.id].trim() })) })
        }
      />
      <StatusMessage {...fix} className="" />
    </div>
  );
}

function ImageFixPanel({ issue, productId }) {
  const [imageUrl, setImageUrl] = useState("");
  const [altText, setAltText] = useState("");
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);

  const urlOk = /^https:\/\/\S+$/i.test(imageUrl.trim());
  const ready = urlOk && altText.trim();

  return (
    <div className={PANEL_CLS}>
      <div>
        <label className={LABEL_CLS}>Image URL (https)</label>
        <input
          type="url"
          value={imageUrl}
          onChange={(e) => setImageUrl(e.target.value)}
          disabled={disabled}
          placeholder="Enter a publicly reachable image URL"
          className={`mt-2 w-full font-mono ${INPUT_CLS}`}
        />
        {imageUrl && !urlOk && (
          <p className="mt-1 text-[11px] text-red-600">The link must start with https:// and be publicly reachable.</p>
        )}
      </div>
      <div>
        <label className={LABEL_CLS}>Alt text</label>
        <input
          type="text"
          value={altText}
          onChange={(e) => setAltText(e.target.value)}
          disabled={disabled}
          placeholder="Describe what the image shows"
          className={`mt-2 w-full ${INPUT_CLS}`}
        />
      </div>
      <ApplyButton
        status={fix.status}
        ready={ready}
        label="Approve and add image"
        busy="Uploading..."
        done="Submitted"
        onClick={() => ready && fix.submit({ image_url: imageUrl.trim(), alt_text: altText.trim() })}
      />
      <StatusMessage {...fix} />
    </div>
  );
}

function ImageAltFixPanel({ issue, productId }) {
  const images = issue.affected_images || [];
  const missing = images.filter((img) => !(img.alt || "").trim());
  const [values, setValues] = useState({});
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);

  if (images.length === 0) {
    return <EmptyPanel>No images were returned for this issue. Re-run the audit and try again.</EmptyPanel>;
  }

  const ready = missing.length > 0 && missing.every((img) => (values[img.id] || "").trim());

  return (
    <div className={PANEL_CLS}>
      <label className={LABEL_CLS}>Image alt text</label>
      <p className="text-[11px] text-[var(--app-muted)]">
        Describe what each image shows. Alt text is stored on the image file, so any other product
        using the same image gets this text too.
      </p>

      {missing.map((img) => (
        <div key={img.id} className="flex items-center gap-2">
          {img.url && <img src={img.url} alt="" className="h-12 w-12 shrink-0 rounded object-cover" />}
          <input
            type="text"
            value={values[img.id] || ""}
            onChange={(e) => setValues((prev) => ({ ...prev, [img.id]: e.target.value }))}
            disabled={disabled}
            placeholder="Describe this image"
            aria-label="Alt text"
            className={`min-w-0 flex-1 ${INPUT_CLS}`}
          />
        </div>
      ))}

      <ApplyButton
        status={fix.status}
        ready={ready}
        onClick={() =>
          ready &&
          fix.submit({
            image_alts: Object.fromEntries(missing.map((img) => [img.id, values[img.id].trim()])),
          })
        }
      />
      <StatusMessage {...fix} className="" />
    </div>
  );
}

function VariantFieldFixPanel({ issue, productId, field, label, placeholder, hint }) {
  const variants = issue.affected_variants || [];

  if (variants.length === 0) {
    return <EmptyPanel>No specific variant identified for this issue.</EmptyPanel>;
  }

  return (
    <div className="space-y-3">
      {hint && <p className="text-[11px] text-[var(--app-muted)]">{hint}</p>}
      {variants.map((v) => (
        <VariantFieldRow
          key={v.id}
          variant={v}
          field={field}
          label={label}
          placeholder={placeholder}
          issue={issue}
          productId={productId}
        />
      ))}
    </div>
  );
}

function VariantFieldRow({ variant, field, label, placeholder, issue, productId }) {
  const [value, setValue] = useState("");
  const fix = useApplyFix({ issue, productId });
  const disabled = isLocked(fix.status);

  const trimmed = value.trim();
  const gtinError =
    field === "gtin" && trimmed && !isValidGtin(trimmed)
      ? "A GTIN has 8, 12, 13 or 14 digits and a valid check digit. Re-check the number on the packaging."
      : "";
  const ready = trimmed && !gtinError;

  return (
    <div className="rounded-lg border border-[var(--app-border)] bg-white p-3">
      <div className="flex items-center gap-2">
        {variant.image_url && (
          <img src={variant.image_url} alt="" className="h-10 w-10 shrink-0 rounded object-cover" />
        )}
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold text-[var(--app-text)]">
            {variant.title || variant.selected_options?.map((o) => o.value).join(" / ") || "Variant"}
          </p>
          {variant.sku && <p className="text-[11px] text-[var(--app-muted)]">SKU: {variant.sku}</p>}
        </div>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={disabled}
          placeholder={placeholder}
          aria-label={label}
          className={`min-w-0 flex-1 font-mono ${INPUT_CLS}`}
        />
        <ApplyButton
          status={fix.status}
          ready={ready}
          label={`Approve and save ${label}`}
          className="shrink-0"
          onClick={() => ready && fix.submit({ variant_id: variant.id, [field]: trimmed })}
        />
      </div>
      {gtinError && <p className="mt-1 text-[11px] text-red-600">{gtinError}</p>}
      <StatusMessage {...fix} />
    </div>
  );
}

/* ---------- Option values on existing variants ---------- */

const currentValueMap = (variant) =>
  Object.fromEntries((variant.selected_options || []).map((o) => [o.name, o.value]));

function VariantOptionsFixPanel({ issue, productId }) {
  const stateFetcher = useFetcher();
  const fix = useApplyFix({ issue, productId });

  const [live, setLive] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [values, setValues] = useState({});
  const [approved, setApproved] = useState(false);

  const isNormalizeMode = issue.issue_type === "inconsistent_option_values";
  const disabled = isLocked(fix.status);

  useEffect(() => {
    setLoading(true);
    setLoadError("");
    setLive(null);
    setValues({});
    setApproved(false);

    stateFetcher.submit(
      { __endpoint: "/products/variant-options-state", product_id: productId },
      {
        method: "post",
        action: window.location.pathname + window.location.search,
        encType: "application/json",
      }
    );
   
  }, [issue.issue_type, productId]);

  useEffect(() => {
    if (stateFetcher.state !== "idle" || !stateFetcher.data) return;

    if (stateFetcher.data.detail) {
      setLoadError(errorText(stateFetcher.data, "Unable to load the current variants."));
      setLive(null);
    } else {
      setLive(stateFetcher.data);
      setLoadError("");
    }
    setLoading(false);
  }, [stateFetcher.state, stateFetcher.data]);

  const optionNames = live?.options || [];
  const allVariants = live?.variants || [];
  const flaggedIds = new Set((issue.affected_variants || []).map((v) => v.id));
  const variants = isNormalizeMode
    ? allVariants
    : allVariants.filter((v) => flaggedIds.size === 0 || flaggedIds.has(v.id));

  useEffect(() => {
    if (!live) return;
    setValues(
      Object.fromEntries(
        variants.map((variant) => {
          const current = currentValueMap(variant);
          const suggested = Object.fromEntries(
            (variant.selected_options || []).map((o) => [o.name, o.suggested_value])
          );
          return [
            variant.id,
            Object.fromEntries(
              optionNames.map((name) => [
                name,
                isNormalizeMode ? suggested[name] || current[name] || "" : current[name] || "",
              ])
            ),
          ];
        })
      )
    );
    
  }, [live]);

  if (loading) {
    return <p className="text-xs text-[var(--app-muted)]">Loading current variants…</p>;
  }
  if (loadError) {
    return <p className="text-xs text-red-600">{loadError}</p>;
  }
  if (!live) {
    return <p className="text-xs text-red-600">Unable to load the current variant state.</p>;
  }

  const setCell = (variantId, optionName, value) =>
    setValues((previous) => ({
      ...previous,
      [variantId]: { ...previous[variantId], [optionName]: value },
    }));

  const cell = (variant, name) => (values[variant.id]?.[name] ?? "").trim();

  const allFilled =
    variants.length > 0 && variants.every((v) => optionNames.every((name) => cell(v, name)));

  const changed = variants.filter((v) => {
    const current = currentValueMap(v);
    return optionNames.some((name) => cell(v, name) !== (current[name] || ""));
  });

  const comboOf = (v) =>
    optionNames
      .map((name) => (values[v.id] ? cell(v, name) : (currentValueMap(v)[name] || "").trim()).toLowerCase())
      .join("\u0000");
  const combos = allVariants.map(comboOf);
  const hasCollision = new Set(combos).size !== combos.length;

  const ready = approved && changed.length > 0 && allFilled && !hasCollision;

  const submit = () => {
    if (!ready || disabled) return;
    fix.submit({
      variant_option_values: Object.fromEntries(
        changed.map((v) => [
          v.id,
          Object.fromEntries(optionNames.map((name) => [name, cell(v, name)])),
        ])
      ),
    });
  };

  return (
    <div className={PANEL_CLS}>
      <p className="text-[11px] text-[var(--app-muted)]">
        {isNormalizeMode
          ? "Suggested consistent formatting is pre-filled. Edit any value, then approve."
          : "Enter the real value for every option on the affected variants."}{" "}
        Only the option values on existing variants change; no variants are added or removed.
      </p>

      {variants.length === 0 ? (
        <p className="text-xs text-[var(--app-muted)]">
          No affected variants were found in the current product state.
        </p>
      ) : (
        variants.map((variant) => {
          const current = currentValueMap(variant);
          return (
            <div
              key={variant.id}
              className="rounded-md border border-[var(--app-border)] bg-[var(--app-bg)] p-2"
            >
              <p className="mb-1.5 text-xs font-semibold text-[var(--app-text)]">
                {variant.title || "Variant"}
                {variant.sku && <span className="font-mono text-[var(--app-muted)]"> · {variant.sku}</span>}
              </p>

              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {optionNames.map((name) => {
                  const before = current[name] || "";
                  const after = values[variant.id]?.[name] ?? "";
                  const differs = after.trim() !== before;
                  return (
                    <div key={name}>
                      <label className="block text-[10px] font-semibold text-[var(--app-muted)]">{name}</label>
                      <input
                        type="text"
                        value={after}
                        onChange={(e) => setCell(variant.id, name, e.target.value)}
                        disabled={disabled}
                        className="mt-0.5 w-full rounded-md border border-[var(--app-border)] px-2 py-1 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
                      />
                      {differs && (
                        <p className="mt-0.5 text-[10px] text-[var(--app-muted)]">
                          was: {before || "(empty)"}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })
      )}

      {hasCollision && (
        <p className="text-[11px] text-red-600">
          These values would give two variants identical options. Make each combination unique.
        </p>
      )}

      <ApprovalCheck checked={approved} onChange={setApproved} disabled={disabled}>
        I approve changing the option values on {changed.length} variant{changed.length === 1 ? "" : "s"}.
      </ApprovalCheck>

      <ApplyButton
        status={fix.status}
        ready={ready}
        label={`Approve and save ${changed.length} variant${changed.length === 1 ? "" : "s"}`}
        onClick={submit}
      />
      <StatusMessage {...fix} className="" />
    </div>
  );
}

function FixPanel({ fixIssue, productId, product }) {
  switch (fixIssue.panel) {
    case "handle":
      return <HandleFixPanel issue={fixIssue} productId={productId} />;
    case "metafields":
      return <MetafieldsFixPanel issue={fixIssue} productId={productId} />;
    case "product_type":
      return (
        <TextFixPanel
          issue={fixIssue}
          productId={productId}
          field="product_type"
          label="Product type"
          placeholder="A specific category"
        />
      );
    case "title":
      return (
        <TextFixPanel
          issue={fixIssue}
          productId={productId}
          field="title"
          label="Product title"
          current={product?.title}
        />
      );
    case "description":
      return (
        <TextFixPanel
          issue={fixIssue}
          productId={productId}
          field="description_html"
          label="Product description"
          placeholder="Describe what this product is, who it's for, and what's included..."
          multiline
          replaceWarning="Saving replaces the entire current description. Include everything you want to keep."
        />
      );
    case "review_claim":
      return <ReviewClaimFixPanel issue={fixIssue} productId={productId} />;
    case "guardrail":
      return <GuardrailFixPanel issue={fixIssue} productId={productId} />;
    case "rename_option":
      return <RenameOptionFixPanel issue={fixIssue} productId={productId} />;
    case "sku":
      return <SkuFixPanel issue={fixIssue} productId={productId} />;
    case "price":
      return <PriceFixPanel issue={fixIssue} productId={productId} />;
    case "image":
      return <ImageFixPanel issue={fixIssue} productId={productId} />;
    case "image_alt":
      return <ImageAltFixPanel issue={fixIssue} productId={productId} />;
    case "gtin":
      return (
        <VariantFieldFixPanel
          issue={fixIssue}
          productId={productId}
          field="gtin"
          label="GTIN"
          hint="Use the number assigned by the manufacturer (printed under the barcode). Keep any leading zeros."
        />
      );
    case "mpn":
      return (
        <VariantFieldFixPanel
          issue={fixIssue}
          productId={productId}
          field="mpn"
          label="MPN"
          placeholder="Manufacturer part number"
        />
      );
    case "variant_options":
      return <VariantOptionsFixPanel issue={fixIssue} productId={productId} />;
    default:
      return null;
  }
}

/* -------------------------------------------------------------------------- */
/* Issue row                                                                  */
/* -------------------------------------------------------------------------- */

function modeIntro(panels) {
  const mode = panels.find((p) => p.fix_mode)?.fix_mode;
  if (mode === "approval") return "Review the change below, then approve it before it's saved to your store.";
  if (mode === "user_input") return "We need a few details from you. Fill them in, then approve the change.";
  return null;
}

function IssueRow({ issue, productId, product }) {
  const [showFix, setShowFix] = useState(false);
  const fixablePanels = issue.fixablePanels || [];
  const fixable = fixablePanels.length > 0;
  const intro = modeIntro(fixablePanels);
  const fixStatuses = [...new Set(fixablePanels.map((p) => p.fix_status).filter(Boolean))];

  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <SeverityBadge priority={issue.priority} />
            {fixStatuses.map((s) => (
              <FixStatusBadge key={s} status={s} />
            ))}
          </div>

          <h3 className="text-sm font-bold text-[var(--app-text)]">
            {issue.enrichment || "Missing enrichment"}
          </h3>

          {issue.why_it_matters_for_agents && (
            <p className="mt-1.5 text-xs leading-relaxed text-[var(--app-muted)]">
              {issue.why_it_matters_for_agents}
            </p>
          )}

          {issue.example && (
            <div className="mt-3 rounded-lg border-l-2 border-[var(--app-orange)] bg-white px-3 py-2 font-mono text-[11px] text-[var(--app-muted)]">
              {issue.example}
            </div>
          )}

          {!fixable && (
            <p className="mt-3 text-[11px] leading-relaxed text-[var(--app-muted)]">
              This can't be fixed automatically yet. Resolve it in your Shopify admin, then re-run the audit.
            </p>
          )}

          {showFix && fixable && (
            <div className="mt-3 space-y-3">
              {intro && <p className="text-[11px] text-[var(--app-muted)]">{intro}</p>}
              {fixablePanels.map((fixIssue) => (
                <div key={fixIssue.fix_action}>
                  {fixablePanels.length > 1 && (
                    <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
                      {FIX_ACTION_LABEL[fixIssue.fix_action] || "Fix"}
                    </p>
                  )}
                  <FixPanel fixIssue={fixIssue} productId={productId} product={product} />
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {fixable && (
            <button
              type="button"
              onClick={() => setShowFix((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--app-green)] px-2.5 py-1.5 text-xs font-bold text-[var(--app-green)] transition-colors hover:bg-green-50"
            >
              <Wrench size={13} />
              {showFix ? "Hide" : "Fix"}
            </button>
          )}
          <AlertCircle
            size={17}
            className={issue.priority === "high" ? "text-red-600" : "text-[var(--app-orange)]"}
          />
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/* Route action + page                                                        */
/* -------------------------------------------------------------------------- */

export async function action({ request }) {
  const { session } = await authenticate.admin(request);
  if (!session?.shop || !session?.accessToken) {
    return Response.json({ detail: "Shopify session is not authenticated." }, { status: 401 });
  }

  const payload = await request.json();
  const endpoint = payload.__endpoint || "/products/fix";
  delete payload.__endpoint;

  if (!ALLOWED_ENDPOINTS.has(endpoint)) {
    return Response.json({ detail: "Unsupported fix endpoint." }, { status: 400 });
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...payload, shop_domain: session.shop, access_token: session.accessToken }),
  });
  const data = await response.json().catch(() => ({ detail: "Invalid response from fix backend." }));
  return Response.json(data, { status: response.status });
}

export default function ProductDetails() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { shopDomain } = useRouteLoaderData("routes/app");

  const id = searchParams.get("id");

  const [report, setReport] = useState(null);

  useEffect(() => {
    if (!shopDomain || !id) return;

    let cancelled = false;

    const loadProduct = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/products/detail?shop_domain=${encodeURIComponent(shopDomain)}&product_id=${encodeURIComponent(id)}`
        );

        if (response.status === 404) {
          if (!cancelled) setReport(null);
          return;
        }

        if (!response.ok) {
          throw new Error(`Failed to load product: ${response.status}`);
        }

        const data = await response.json();

        if (!cancelled) setReport(data.product);
      } catch (error) {
        console.error("Failed to load product:", error);
        if (!cancelled) setReport(null);
      }
    };

    loadProduct();

    return () => {
      cancelled = true;
    };
  }, [shopDomain, id]);

  const product = report;

  if (!report) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] px-5 py-10 md:px-8">
        <div className="mx-auto max-w-5xl">
          <button
            type="button"
            onClick={() => navigate("/app/products")}
            className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-[var(--app-green)]"
          >
            <ArrowLeft size={17} />
            Back to Products
          </button>

          <div className="rounded-2xl border border-[var(--app-border)] bg-white px-6 py-16 text-center">
            <Package size={30} className="mx-auto mb-4 text-[var(--app-muted)]" />
            <h1 className="text-xl font-extrabold text-[var(--app-green)]">No Previous Audit Data</h1>
            <p className="mx-auto mt-2 max-w-md text-sm text-[var(--app-muted)]">
              This product has not been included in any completed audit for this store.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const status = getProductStatus(product);
  const StatusIcon = status.icon;
  const enrichments = product.missing_enrichments || [];

  const issuesByCheckId = new Map();
  for (const issue of product.issues || []) {
    if (!issuesByCheckId.has(issue.check_id)) issuesByCheckId.set(issue.check_id, []);
    issuesByCheckId.get(issue.check_id).push(issue);
  }

  const rows = enrichments.map((enrichment, index) => {
    const matched = issuesByCheckId.get(enrichment.check_id) || [];
    return {
      key: `${enrichment.check_id}-${index}`,
      ...enrichment,
      fixablePanels: getFixablePanels(matched),
    };
  });

  const highIssues = rows.filter((r) => r.priority === "high").length;
  const mediumIssues = rows.filter((r) => r.priority === "medium").length;
  const lowIssues = rows.filter((r) => r.priority === "low").length;

  return (
    <div className="min-h-screen bg-[var(--app-bg)] px-5 py-8 text-[var(--app-text)] md:px-8">
      <div className="mx-auto max-w-6xl">
        <button
          type="button"
          onClick={() => navigate("/app/products")}
          className="mb-4 inline-flex items-center gap-2 text-sm font-bold text-[var(--app-green)] transition-opacity hover:opacity-70"
        >
          <ArrowLeft size={17} />
          Back to Products
        </button>

        <div className="mb-6 rounded-2xl border border-[var(--app-border)] bg-white p-6 md:p-8">
          <div className="flex flex-col gap-8 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-6">
              <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-[var(--app-border)] bg-[var(--app-bg)] sm:h-28 sm:w-28">
                {product.image_url ? (
                  <img src={product.image_url} alt={product.title || "Product"} className="h-full w-full object-cover" />
                ) : (
                  <Package size={36} className="text-[var(--app-muted)]" />
                )}
              </div>

              <div className="min-w-0">
                <div className="mb-1.5 text-[10px] font-extrabold uppercase tracking-[0.1em] text-[var(--app-orange)]">
                  Product Health
                </div>
                <h1 className="text-xl font-extrabold text-[var(--app-text)] md:text-2xl">
                  {product.title || "Untitled product"}
                </h1>
                <p className="mt-2 max-w-md text-xs leading-relaxed text-[var(--app-muted)]">{status.blurb}</p>
              </div>
            </div>

            <div
              className={`flex shrink-0 flex-col items-center justify-center gap-1.5 rounded-2xl border-2 ${status.ring} bg-[var(--app-bg)] p-5`}
              style={{ minWidth: 132 }}
            >
              <StatusIcon size={30} className={status.text} />
              <span className={`text-sm font-extrabold ${status.text}`}>{status.label}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-1">
            <div className="rounded-2xl border border-[var(--app-border)] bg-white p-5">
              <h3 className="mb-4 border-b border-[var(--app-border)] pb-2 text-xs font-bold uppercase tracking-wider text-[var(--app-text)]">
                Product Information
              </h3>
              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between border-b border-[var(--app-bg)] py-1">
                  <span className="font-medium text-[var(--app-muted)]">Product ID:</span>
                  <span className="max-w-[60%] truncate text-right font-mono font-semibold text-[var(--app-text)]">
                    {product.product_id || "Unavailable"}
                  </span>
                </div>
                <div className="flex items-center justify-between py-1">
                  <span className="font-medium text-[var(--app-muted)]">Total issues:</span>
                  <span className="font-bold text-[var(--app-text)]">{rows.length}</span>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-[var(--app-border)] bg-white p-5">
              <h3 className="mb-4 border-b border-[var(--app-border)] pb-2 text-xs font-bold uppercase tracking-wider text-[var(--app-text)]">
                Issue Breakdown
              </h3>
              <div className="space-y-3 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[var(--app-muted)]">High priority</span>
                  <span className="font-extrabold text-red-700">{highIssues}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[var(--app-muted)]">Medium priority</span>
                  <span className="font-extrabold text-orange-700">{mediumIssues}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="font-medium text-[var(--app-muted)]">Low priority</span>
                  <span className="font-extrabold text-[var(--app-green)]">{lowIssues}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="lg:col-span-2">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-bold text-[var(--app-text)]">Issues ({rows.length})</h2>
              <span className="text-xs text-[var(--app-muted)]">Resolve these to elevate product readiness</span>
            </div>

            {rows.length > 0 ? (
              <div className="flex flex-col gap-3">
                {rows.map((issue) => (
                  <IssueRow key={issue.key} issue={issue} productId={product.product_id} product={product} />
                ))}
              </div>
            ) : (
              <div className="rounded-2xl border border-green-100 bg-green-50 p-10 text-center">
                <CheckCircle2 size={30} className="mx-auto mb-3 text-[var(--app-green)]" />
                <h3 className="text-sm font-extrabold text-[var(--app-green)]">All checks passed</h3>
                <p className="mx-auto mt-1.5 max-w-sm text-xs text-[var(--app-muted)]">
                  This product currently meets the checks included in the audit.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}