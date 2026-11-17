// app/components/fix-shared.jsx

import PropTypes from "prop-types";

export const FIELD_CLS =
  "w-full rounded-md border border-[var(--app-border,#E1E3E5)] bg-white px-3 py-2 text-xs text-[#202223] outline-none focus:border-[var(--app-green,#D97706)] disabled:opacity-60";

/* -------------------------------------------------------------------------- */
/* Status                                                                     */
/* -------------------------------------------------------------------------- */

export function isLocked(status) {
  return status === "submitting" || status === "done" || status === "partial";
}

export function errorText(data, fallback) {
  const detail = data?.detail;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail) && detail.length) {
    const joined = detail.map((item) => item?.msg).filter(Boolean).join("; ");
    if (joined) return joined;
  }
  return data?.message || fallback;
}

export function failureMessages(data) {
  const items = [...(data?.results || []), ...(data?.updates || [])];
  return items
    .filter((item) => item && item.success === false && item.error)
    .map((item) => String(item.error));
}

/* -------------------------------------------------------------------------- */
/* Validation                                                                 */
/* -------------------------------------------------------------------------- */

export function isValidGtin(value) {
  const v = String(value || "").trim();
  if (!/^\d+$/.test(v) || ![8, 12, 13, 14].includes(v.length)) return false;
  const digits = v.split("").map(Number);
  const check = digits.pop();
  const total = digits
    .reverse()
    .reduce((sum, digit, index) => sum + digit * (index % 2 === 0 ? 3 : 1), 0);
  return (10 - (total % 10)) % 10 === check;
}

/* -------------------------------------------------------------------------- */
/* Metafield rows                                                             */
/* -------------------------------------------------------------------------- */

export const METAFIELD_TYPES = [
  { value: "single_line_text_field", label: "Text (single line)" },
  { value: "multi_line_text_field", label: "Text (multi-line)" },
  { value: "number_integer", label: "Number (integer)" },
  { value: "number_decimal", label: "Number (decimal)" },
  { value: "dimension", label: "Dimension" },
  { value: "list.single_line_text_field", label: "List of text" },
];

export const METAFIELD_TYPE_HELP = {
  single_line_text_field: "A single line of text.",
  multi_line_text_field: "Text that can contain multiple lines.",
  number_integer: "A whole number without decimal places.",
  number_decimal: "A number that may contain decimal places.",
  dimension: "A numeric measurement with a unit.",
  "list.single_line_text_field": "One or more text values stored as a list.",
};

export const DIMENSION_UNITS = [
  "MILLIMETERS",
  "CENTIMETERS",
  "METERS",
  "INCHES",
  "FEET",
  "YARDS",
];

export const emptyMetaRow = () => ({
  namespace: "details",
  key: "",
  type: "single_line_text_field",
  value: "",
  unit: "CENTIMETERS",
  values: [""],
});

export function isMetaRowValid(row) {
  if (!row.key.trim() || !row.namespace.trim()) return false;
  if (row.type === "list.single_line_text_field") return row.values.some((v) => v.trim());
  if (row.type === "dimension") {
    return row.value.trim() !== "" && Number.isFinite(Number(row.value));
  }
  if (row.type === "number_integer") {
    return row.value.trim() !== "" && Number.isInteger(Number(row.value));
  }
  if (row.type === "number_decimal") {
    return row.value.trim() !== "" && Number.isFinite(Number(row.value));
  }
  return row.value.trim() !== "";
}

export function buildMetaEntry(row) {
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

// The engine rejects duplicate namespace.key pairs. Catch them before submit.
export function findDuplicateMetafield(rows) {
  const seen = new Set();
  for (const row of rows) {
    if (!row.key.trim()) continue;
    const id = `${row.namespace.trim()}.${row.key.trim()}`;
    if (seen.has(id)) return id;
    seen.add(id);
  }
  return null;
}

function prettyUnit(unit) {
  return unit.charAt(0) + unit.slice(1).toLowerCase();
}

export function MetafieldRowEditor({ row, onChange, onRemove, disabled, showNamespace }) {
  const setListValue = (i, v) =>
    onChange({ values: row.values.map((item, idx) => (idx === i ? v : item)) });

  const selectCls =
    "rounded-md border border-[var(--app-border,#E1E3E5)] bg-white px-2 py-2 text-xs outline-none focus:border-[var(--app-green,#D97706)] disabled:opacity-60";

  return (
    <div className="space-y-2 rounded-md border border-[var(--app-border,#E1E3E5)] bg-[#FAFAFA] p-3">
      <div className="flex flex-wrap items-center gap-2">
        {showNamespace && (
          <input
            type="text"
            value={row.namespace}
            onChange={(e) => onChange({ namespace: e.target.value })}
            disabled={disabled}
            placeholder="namespace"
            aria-label="Namespace"
            className={`${FIELD_CLS} !w-28 font-mono`}
          />
        )}
        <input
          type="text"
          value={row.key}
          onChange={(e) => onChange({ key: e.target.value })}
          disabled={disabled}
          placeholder="Attribute name"
          aria-label="Attribute name"
          className={`${FIELD_CLS} !w-auto min-w-[140px] flex-1 font-mono`}
        />
        <select
          value={row.type}
          onChange={(e) => onChange({ type: e.target.value })}
          disabled={disabled}
          aria-label="Attribute type"
          className={selectCls}
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
          className={FIELD_CLS}
        />
      )}

      {row.type === "multi_line_text_field" && (
        <textarea
          rows={3}
          value={row.value}
          onChange={(e) => onChange({ value: e.target.value })}
          disabled={disabled}
          placeholder="Value"
          className={`${FIELD_CLS} resize-y`}
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
          className={FIELD_CLS}
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
            className={`${FIELD_CLS} min-w-0 flex-1`}
          />
          <select
            value={row.unit}
            onChange={(e) => onChange({ unit: e.target.value })}
            disabled={disabled}
            aria-label="Unit"
            className={selectCls}
          >
            {DIMENSION_UNITS.map((u) => (
              <option key={u} value={u}>
                {prettyUnit(u)}
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
                className={`${FIELD_CLS} min-w-0 flex-1`}
              />
              {row.values.length > 1 && !disabled && (
                <button
                  type="button"
                  onClick={() => onChange({ values: row.values.filter((_, idx) => idx !== i) })}
                  aria-label="Remove value"
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

MetafieldRowEditor.propTypes = {
  row: PropTypes.object.isRequired,
  onChange: PropTypes.func.isRequired,
  onRemove: PropTypes.func,
  disabled: PropTypes.bool,
  showNamespace: PropTypes.bool,
};


export function ApprovalCheck({ checked, onChange, disabled, children }) {
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

ApprovalCheck.propTypes = {
  checked: PropTypes.bool.isRequired,
  onChange: PropTypes.func.isRequired,
  disabled: PropTypes.bool,
  children: PropTypes.node,
};

const FIX_STATUS_STYLES = {
  applied: "border-[#BBE5B9] bg-[#F1F8F5] text-[#065F46]",
  partially_applied: "border-[#FFE0A3] bg-[#FFF5E5] text-[#8A6116]",
  failed: "border-[#FFC9C5] bg-[#FFF0EF] text-[#D72C0D]",
};

const FIX_STATUS_LABELS = {
  applied: "Fix saved. Re-run the audit to confirm.",
  partially_applied: "Partly saved. Check Shopify, then re-run the audit.",
  failed: "Last attempt failed.",
};

export function FixStatusBadge({ status }) {
  if (!FIX_STATUS_STYLES[status]) return null;
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${FIX_STATUS_STYLES[status]}`}
    >
      {FIX_STATUS_LABELS[status]}
    </span>
  );
}

FixStatusBadge.propTypes = { status: PropTypes.string };