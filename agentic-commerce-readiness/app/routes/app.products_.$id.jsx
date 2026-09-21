import { useEffect, useState } from "react";
import {
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
import { useFetcher } from "react-router";

const API_BASE = "https://geo.properoapps.in/api";

const FIX_KIND_BY_ISSUE = {
  "missing_product_url:update_product_handle": "handle",
  "invalid_product_url:update_product_handle": "handle",
  "missing_required_attribute:set_metafield": "metafields",
  "unstructured_product_attribute:set_metafield": "metafields",
};

function getFixKind(issue) {
  return FIX_KIND_BY_ISSUE[`${issue.issue_type}:${issue.fix_action}`] || null;
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


function useApplyFix({ issue, productId, onDone }) {
  const fetcher = useFetcher();
  const [status, setStatus] = useState("idle"); 
  const [message, setMessage] = useState("");

  const submit = (extraFields) => {
    setStatus("submitting");
    setMessage("");

    fetcher.submit(
      {
        product_id: productId,
        issue_id: issue.id,
        check_id: issue.check_id,
        issue_type: issue.issue_type,
        ...extraFields,
      },
      {
        method: "post",
        action: window.location.pathname + window.location.search,
        encType: "application/json",
      }
    );
  };

  useEffect(() => {
    if (fetcher.state !== "idle") return;
    if (!fetcher.data) return;

    if (fetcher.data.success) {
      setStatus("done");
      setMessage(fetcher.data.message || "Fix applied.");
      onDone?.();
    } else {
      setStatus("error");
      setMessage(fetcher.data.message || fetcher.data.detail || "Failed to apply fix.");
    }
  }, [fetcher.state, fetcher.data, onDone]);

  return { submit, status, message };
}

function HandleFixPanel({ issue, productId, onDone }) {
  const [handle, setHandle] = useState(issue.suggested_handle || "");
  const { submit, status, message } = useApplyFix({ issue, productId, onDone });
  const disabled = status === "submitting" || status === "done";

  const handleApprove = () => {
    if (!handle.trim()) return;
    submit({ handle: handle.trim() });
  };

  return (
    <div className="mt-3 space-y-2 rounded-lg border border-[var(--app-border)] bg-white p-3">
      <label className="block text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
        Product handle
      </label>

      <input
        type="text"
        value={handle}
        onChange={(e) => setHandle(e.target.value)}
        disabled={disabled}
        placeholder="product-handle-slug"
        className="w-full rounded-md border border-[var(--app-border)] px-2.5 py-1.5 font-mono text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
      />

      <div className="flex items-center gap-2 pt-1">
        <button
          type="button"
          onClick={handleApprove}
          disabled={disabled || !handle.trim()}
          className="rounded-md bg-[var(--app-green)] px-3 py-1.5 text-xs font-bold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
        >
          {status === "submitting" ? "Applying..." : status === "done" ? "Applied" : "Approve & Apply"}
        </button>
      </div>

      {message && (
        <p className={`text-xs ${status === "error" ? "text-red-600" : "text-[var(--app-green)]"}`}>
          {message}
        </p>
      )}
    </div>
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

const METAFIELD_TYPE_HELP = {
  single_line_text_field:
    "Enter a single line of text.",

  multi_line_text_field:
    "Enter text that can contain multiple lines.",

  number_integer:
    "Enter a whole number without decimal places.",

  number_decimal:
    "Enter a number that may contain decimal places.",

  dimension:
    "Enter a numeric measurement and select its unit.",

  "list.single_line_text_field":
    "Add one or more text values. Each value is stored as an item in the list.",
};

function emptyAttributeRow() {
  return {
    key: "",
    type: "single_line_text_field",
    value: "",
    unit: "CENTIMETERS",
    values: [""],
  };
}

function MetafieldsFixPanel({ issue, productId, onDone }) {
  const [rows, setRows] = useState([emptyAttributeRow()]);
  const [showTypeGuide, setShowTypeGuide] = useState(false);

  const { submit, status, message } = useApplyFix({
    issue,
    productId,
    onDone,
  });

  const disabled = status === "submitting" || status === "done";

  const updateRow = (index, field, value) => {
    setRows((prev) =>
      prev.map((row, i) =>
        i === index
          ? {
              ...row,
              [field]: value,
            }
          : row
      )
    );
  };

  const addRow = () => {
    setRows((prev) => [...prev, emptyAttributeRow()]);
  };

  const removeRow = (index) => {
    setRows((prev) =>
      prev.length === 1
        ? prev
        : prev.filter((_, i) => i !== index)
    );
  };

  const addListValue = (rowIndex) => {
    setRows((prev) =>
      prev.map((row, i) =>
        i === rowIndex
          ? {
              ...row,
              values: [...row.values, ""],
            }
          : row
      )
    );
  };

  const updateListValue = (rowIndex, valueIndex, value) => {
    setRows((prev) =>
      prev.map((row, i) =>
        i === rowIndex
          ? {
              ...row,
              values: row.values.map((item, valueI) =>
                valueI === valueIndex ? value : item
              ),
            }
          : row
      )
    );
  };

  const removeListValue = (rowIndex, valueIndex) => {
    setRows((prev) =>
      prev.map((row, i) =>
        i === rowIndex
          ? {
              ...row,
              values:
                row.values.length === 1
                  ? row.values
                  : row.values.filter(
                      (_, valueI) => valueI !== valueIndex
                    ),
            }
          : row
      )
    );
  };

  const buildAttribute = (row) => {
    const key = row.key.trim();

    if (row.type === "dimension") {
      return {
        key,
        type: row.type,
        value: JSON.stringify({
          unit: row.unit,
          value: Number(row.value),
        }),
      };
    }

    if (row.type === "list.single_line_text_field") {
      return {
        key,
        type: row.type,
        value: JSON.stringify(
          row.values
            .map((item) => item.trim())
            .filter(Boolean)
        ),
      };
    }

    return {
      key,
      type: row.type,
      value: row.value.trim(),
    };
  };

  const isRowValid = (row) => {
    if (!row.key.trim()) return false;

    if (row.type === "list.single_line_text_field") {
      return row.values.some((item) => item.trim());
    }

    if (row.type === "dimension") {
      return (
        row.value.trim() !== "" &&
        Number.isFinite(Number(row.value))
      );
    }

    return row.value.trim() !== "";
  };

  const validRows = rows.filter(isRowValid);

  const handleApply = () => {
    if (validRows.length === 0) return;

    submit({
      attributes: validRows.map(buildAttribute),
    });
  };

  return (
    <div className="mt-3 space-y-3 rounded-lg border border-[var(--app-border)] bg-white p-3">
      <label className="block text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
        Metafield attributes
      </label>

      <div className="space-y-4">
        {rows.map((row, index) => (
          <div
            key={index}
            className="rounded-md border border-[var(--app-border)] bg-[var(--app-bg)] p-3"
          >
            <div className="flex flex-wrap items-start gap-2">
              {/* Attribute name */}
              <input
                type="text"
                value={row.key}
                onChange={(e) =>
                  updateRow(index, "key", e.target.value)
                }
                disabled={disabled}
                placeholder="Attribute name"
                className="min-w-[150px] flex-1 rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 font-mono text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
              />

              {/* Type */}
              <select
                value={row.type}
                onChange={(e) =>
                  updateRow(index, "type", e.target.value)
                }
                disabled={disabled}
                className="rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
              >
                {METAFIELD_TYPES.map((type) => (
                  <option
                    key={type.value}
                    value={type.value}
                  >
                    {type.label}
                  </option>
                ))}
              </select>

              {rows.length > 1 && !disabled && (
                <button
                  type="button"
                  onClick={() => removeRow(index)}
                  aria-label="Remove attribute"
                  className="px-1 py-1.5 text-xs font-bold text-red-500 hover:text-red-700"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Single-line text */}
            {row.type === "single_line_text_field" && (
              <input
                type="text"
                value={row.value}
                onChange={(e) =>
                  updateRow(index, "value", e.target.value)
                }
                disabled={disabled}
                placeholder="Value"
                className="mt-2 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
              />
            )}

            {/* Multi-line text */}
            {row.type === "multi_line_text_field" && (
              <textarea
                value={row.value}
                onChange={(e) =>
                  updateRow(index, "value", e.target.value)
                }
                disabled={disabled}
                placeholder="Enter value..."
                rows={4}
                className="mt-2 w-full resize-y rounded-md border border-[var(--app-border)] bg-white px-2.5 py-2 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
              />
            )}

            {/* Integer */}
            {row.type === "number_integer" && (
              <input
                type="number"
                step="1"
                value={row.value}
                onChange={(e) =>
                  updateRow(index, "value", e.target.value)
                }
                disabled={disabled}
                placeholder="Enter whole number"
                className="mt-2 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
              />
            )}

            {/* Decimal */}
            {row.type === "number_decimal" && (
              <input
                type="number"
                step="any"
                value={row.value}
                onChange={(e) =>
                  updateRow(index, "value", e.target.value)
                }
                disabled={disabled}
                placeholder="Enter decimal"
                className="mt-2 w-full rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
              />
            )}

            {/* Dimension */}
            {row.type === "dimension" && (
              <div className="mt-2 flex gap-2">
                <input
                  type="number"
                  step="any"
                  value={row.value}
                  onChange={(e) =>
                    updateRow(index, "value", e.target.value)
                  }
                  disabled={disabled}
                  placeholder="Value"
                  className="min-w-0 flex-1 rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
                />

                <select
                  value={row.unit}
                  onChange={(e) =>
                    updateRow(index, "unit", e.target.value)
                  }
                  disabled={disabled}
                  className="rounded-md border border-[var(--app-border)] bg-white px-2 py-1.5 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
                >
                  <option value="MILLIMETERS">Millimeters</option>
                  <option value="CENTIMETERS">Centimeters</option>
                  <option value="METERS">Meters</option>
                  <option value="INCHES">Inches</option>
                  <option value="FEET">Feet</option>
                  <option value="YARDS">Yards</option>
                </select>
              </div>
            )}

            {/* List of text */}
            {row.type === "list.single_line_text_field" && (
              <div className="mt-2 space-y-2">
                {row.values.map((value, valueIndex) => (
                  <div
                    key={valueIndex}
                    className="flex items-center gap-2"
                  >
                    <input
                      type="text"
                      value={value}
                      onChange={(e) =>
                        updateListValue(
                          index,
                          valueIndex,
                          e.target.value
                        )
                      }
                      disabled={disabled}
                      placeholder={`Value ${valueIndex + 1}`}
                      className="min-w-0 flex-1 rounded-md border border-[var(--app-border)] bg-white px-2.5 py-1.5 text-xs outline-none focus:border-[var(--app-green)] disabled:opacity-60"
                    />

                    {row.values.length > 1 && !disabled && (
                      <button
                        type="button"
                        onClick={() =>
                          removeListValue(index, valueIndex)
                        }
                        className="text-xs font-bold text-red-500 hover:text-red-700"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                ))}

                {!disabled && (
                  <button
                    type="button"
                    onClick={() => addListValue(index)}
                    className="text-xs font-semibold text-[var(--app-green)] hover:underline"
                  >
                    + Add value
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="space-y-2">
        {/* Top row */}
        <div className="flex items-center justify-between gap-3">
          {!disabled && (
            <button
              type="button"
              onClick={addRow}
              className="rounded-md border border-[var(--app-border)] px-2.5 py-1.5 text-xs font-semibold text-[var(--app-text)] hover:bg-[var(--app-bg)]"
            >
              + Add Attribute
            </button>
          )}

          <button
            type="button"
            onClick={handleApply}
            disabled={disabled || validRows.length === 0}
            className="rounded-md bg-[var(--app-green)] px-3 py-1.5 text-xs font-bold text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
          >
            {status === "submitting"
              ? "Applying..."
              : status === "done"
                ? "Applied"
                : "Apply Fix"}
          </button>
        </div>

        {/* Second row — left aligned */}
        <div>
          <button
            type="button"
            onClick={() => setShowTypeGuide((v) => !v)}
            className="text-xs font-semibold text-[var(--app-muted)] underline hover:text-[var(--app-text)]"
          >
            {showTypeGuide
              ? "Hide type guide"
              : "What type should I pick?"}
          </button>
        </div>
      </div>

      {showTypeGuide && (
        <div className="rounded-md border border-[var(--app-border)] bg-[var(--app-bg)] p-3 text-[11px] leading-relaxed text-[var(--app-muted)]">
          <ul className="space-y-1.5">
            {METAFIELD_TYPES.map((type) => (
              <li key={type.value}>
                <span className="font-mono font-semibold text-[var(--app-text)]">
                  {type.value}
                </span>
                {" — "}
                {METAFIELD_TYPE_HELP[type.value]}
              </li>
            ))}
          </ul>
        </div>
      )}

      {message && (
        <p
          className={`text-xs ${
            status === "error"
              ? "text-red-600"
              : "text-[var(--app-green)]"
          }`}
        >
          {message}
        </p>
      )}
    </div>
  );
}

function IssueRow({ issue, productId }) {
  const [showFix, setShowFix] = useState(false);
  const fixKind = getFixKind(issue);
  const fixable = Boolean(fixKind);

  return (
    <div className="rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)] p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <SeverityBadge priority={issue.priority} />
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

          {fixable && showFix && fixKind === "handle" && (
            <HandleFixPanel issue={issue} productId={productId} onDone={() => {}} />
          )}

          {fixable && showFix && fixKind === "metafields" && (
            <MetafieldsFixPanel issue={issue} productId={productId} onDone={() => {}} />
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
            className={
              issue.priority === "high"
                ? "text-red-600"
                : "text-[var(--app-orange)]"
            }
          />
        </div>
      </div>
    </div>
  );
}

export async function action({ request }) {
  const { session } = await authenticate.admin(request);

  if (!session?.shop || !session?.accessToken) {
    return Response.json(
      { detail: "Shopify session is not authenticated." },
      { status: 401 }
    );
  }

  const payload = await request.json();

  const response = await fetch(`${API_BASE}/products/fix`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ...payload,
      shop_domain: session.shop,
      access_token: session.accessToken,
    }),
  });

  const data = await response.json().catch(() => ({
    detail: "Invalid response from fix backend.",
  }));

  return Response.json(data, {
    status: response.status,
  });
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
          `${API_BASE}/products/detail?shop_domain=${encodeURIComponent(
            shopDomain
          )}&product_id=${encodeURIComponent(id)}`
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

            <h1 className="text-xl font-extrabold text-[var(--app-green)]">
              No Previous Audit Data
            </h1>

            <p className="mx-auto mt-2 max-w-md text-sm text-[var(--app-muted)]">
              This product has not been included in any completed audit for this
              store.
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
    if (!issuesByCheckId.has(issue.check_id)) {
      issuesByCheckId.set(issue.check_id, issue);
    }
  }

  const rows = enrichments.map((enrichment, index) => {
    const matchedIssue = issuesByCheckId.get(enrichment.check_id);
    return {
      key: `${enrichment.check_id}-${index}`,
      ...enrichment,
      id: matchedIssue?.id,
      issue_type: matchedIssue?.issue_type,
      fix_action: matchedIssue?.fix_action,
      suggested_handle: matchedIssue?.suggested_handle,
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

        {/* Hero card — image + title on the left, status (real, derived)
            on the right in place of the mockup's fabricated numeric gauge */}
        <div className="mb-6 rounded-2xl border border-[var(--app-border)] bg-white p-6 md:p-8">
          <div className="flex flex-col gap-8 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-6">
              <div className="flex h-24 w-24 shrink-0 items-center justify-center rounded-2xl border border-[var(--app-border)] bg-[var(--app-bg)] sm:h-28 sm:w-28">
                <Package size={36} className="text-[var(--app-muted)]" />
              </div>

              <div className="min-w-0">
                <div className="mb-1.5 text-[10px] font-extrabold uppercase tracking-[0.1em] text-[var(--app-orange)]">
                  Product Health
                </div>
                <h1 className="text-xl font-extrabold text-[var(--app-text)] md:text-2xl">
                  {product.title || "Untitled product"}
                </h1>
                <p className="mt-2 max-w-md text-xs leading-relaxed text-[var(--app-muted)]">
                  {status.blurb}
                </p>
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
          {/* Left column — only real fields: product ID and issue counts */}
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

          {/* Right column — issues list */}
          <div className="lg:col-span-2">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-bold text-[var(--app-text)]">
                Issues ({rows.length})
              </h2>
              <span className="text-xs text-[var(--app-muted)]">
                Resolve these to elevate product readiness
              </span>
            </div>

            {rows.length > 0 ? (
              <div className="flex flex-col gap-3">
                {rows.map((issue) => (
                  <IssueRow
                    key={issue.key}
                    issue={issue}
                    productId={product.product_id}
                  />
                ))}
              </div>
            ) : (
              <div className="rounded-2xl border border-green-100 bg-green-50 p-10 text-center">
                <CheckCircle2 size={30} className="mx-auto mb-3 text-[var(--app-green)]" />
                <h3 className="text-sm font-extrabold text-[var(--app-green)]">
                  All checks passed
                </h3>
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