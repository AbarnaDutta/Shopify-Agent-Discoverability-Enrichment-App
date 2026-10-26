// app/routes/app.issues.jsx

import {
  useEffect,
  useMemo,
  useState,
  Fragment,
} from "react";
import PropTypes from "prop-types";

import {
  useFetcher,
  useNavigate,
  useRouteLoaderData,

} from "react-router";


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

/* -------------------------------------------------------------------------- */

/* Helpers                                                                    */

/* -------------------------------------------------------------------------- */


function getPriority(value) {
  const priority = String(value || "medium").toLowerCase();

  if (["high", "medium", "low"].includes(priority)) {

    return priority;

  }

  return "medium";

}

function getAffectedProducts(recommendation, products) {

  const ids = Array.isArray(recommendation?.affected_product_ids)

    ? recommendation.affected_product_ids.map(String)

    : [];

  if (ids.length === 0) {
    return [];
  }

  return products.filter((product) =>
    ids.includes(String(product.product_id))
  );

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


function resolveStoreFixMetadata(recommendation, auditIssues) {
  const storeIssues = Array.isArray(auditIssues)
    ? auditIssues.filter((issue) => issue?.scope === "store")
    : [];
  const label = String(recommendation?.enrichment || "").trim().toLowerCase();
  const matchingChecks = new Set(
    storeIssues
      .filter((issue) => {
        const issueLabel = STORE_CHECK_LABELS[issue.check_id] ||
          prettyLabel(issue.check_id).toLowerCase();
        return issueLabel.toLowerCase() === label;
      })
      .map((issue) => issue.check_id)
      .filter(Boolean)
  );

  let checkId = recommendation?.check_id ||
    recommendation?.fix_payload?.check_id ||
    (matchingChecks.size === 1 ? [...matchingChecks][0] : "");

  if (!checkId) {
    const auditChecks = new Set(storeIssues.map((issue) => issue.check_id).filter(Boolean));
    if (auditChecks.size === 1) checkId = [...auditChecks][0];
  }

  const matchingTypes = new Set(
    storeIssues
      .filter((issue) => issue.check_id === checkId && issue.issue_type)
      .map((issue) => issue.issue_type)
  );
  const issueType = recommendation?.issue_type ||
    recommendation?.fix_payload?.issue_type ||
    (matchingTypes.size === 1
      ? [...matchingTypes][0]
        : "");

  return { check_id: checkId, issue_type: issueType };
}


/* -------------------------------------------------------------------------- */

/* Severity badge                                                             */

/* -------------------------------------------------------------------------- */

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

SeverityBadge.propTypes = {
  priority: PropTypes.string,
};


/* -------------------------------------------------------------------------- */

/* Store-wide fix modal                                                       */

/* -------------------------------------------------------------------------- */

function StoreFixModal({ issue, shopDomain, onClose }) {
  const fetcher = useFetcher();
  const recommendation = issue.raw || {};

  const suppliedFix = recommendation.fix_payload || {};

  // Only use real metadata supplied by the audit.
  const initialCheckId =
    recommendation.check_id ||
    suppliedFix.check_id ||
    "";

  const initialIssueType =
    recommendation.issue_type ||
    suppliedFix.issue_type ||
    "";

  const initialChanges =
    recommendation.changes ??
    suppliedFix.changes ??
    [];

  const [checkId] = useState(initialCheckId);
  const [issueType] = useState(initialIssueType);
  const [changesText, setChangesText] = useState(() =>
    JSON.stringify(initialChanges, null, 2)
  );


  const [validationError, setValidationError] = useState("");
  const isSubmitting = fetcher.state !== "idle";
  const responseData = fetcher.data;
  const requestSucceeded =

    responseData?.success === true ||

    responseData?.data?.success === true;

  const requestFailed =

    responseData &&

    !isSubmitting &&

    !requestSucceeded &&

    (

      responseData.success === false ||

      responseData.ok === false ||

      Boolean(responseData.error) ||

      Boolean(responseData.detail)

    );

  const responseMessage =

    responseData?.message ||

    responseData?.detail ||

    responseData?.error ||
    responseData?.data?.message ||
    responseData?.data?.detail ||

    responseData?.data?.detail ||
    "";

  const parseChanges = () => {
    let parsedChanges;
    try {

      parsedChanges = JSON.parse(changesText);

    } catch {

      throw new Error(

        "Changes must be valid JSON. Check the brackets, commas, and quotation marks."

      );

    }

    if (!Array.isArray(parsedChanges) || parsedChanges.length === 0) {

      throw new Error(

        "Enter a non-empty JSON array containing the actual changes to apply."

      );

    }

    if (

      parsedChanges.some(

        (change) =>

          !change ||

          typeof change !== "object" ||

          Array.isArray(change)

      )

    ) {

      throw new Error(

        "Every item in changes must be a JSON object."

      );

    }

    return parsedChanges;

  };

  const handleSubmit = (event) => {
    event.preventDefault();
    setValidationError("");

    if (!shopDomain) {
      setValidationError(
        "The Shopify store domain is missing. Reload the app and try again."
      );
      return;
    }

    if (!checkId.trim()) {
      setValidationError(
        "Enter the actual check_id configured in the backend."
      );
      return;
    }
    if (!issueType.trim()) {
      setValidationError(
        "Enter the actual issue_type supported by the backend."
      );
      return;
    }

    let changes;

    try {
      changes = parseChanges();
    } catch (error) {
      setValidationError(error.message);
      return;
    }



    /*

     * This posts through the existing authenticated product-detail route.

     * That route forwards the request to POST /store/fix.

     */

    fetcher.submit(

      {

        __endpoint: "/store/fix",

        shop_domain: shopDomain,

        check_id: checkId.trim(),

        issue_type: issueType.trim(),

        changes,

      },

      {

        method: "post",

        action: "/app/products/detail",

        encType: "application/json",

      }

    );

  };



  return (

    <div

      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"

      role="presentation"

      onMouseDown={(event) => {

        if (event.target === event.currentTarget && !isSubmitting) {

          onClose();

        }

      }}

    >

      <div

        role="dialog"

        aria-modal="true"

        aria-labelledby="store-fix-title"

        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-xl border border-[#E1E3E5] bg-white shadow-xl"

      >

        {/* Modal header */}

        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-[#E1E3E5] bg-white p-5">

          <div>

            <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-[#FFF5E5] text-[#8A6116]">

              <Wrench className="h-4 w-4" />

            </div>



            <h2

              id="store-fix-title"

              className="text-base font-bold text-[#202223]"

            >

              Fix store-wide issue

            </h2>



            <p className="mt-1 text-xs text-[#6D7175]">

              Review the request before applying changes to your Shopify store.

            </p>

          </div>



          <button

            type="button"

            onClick={onClose}

            disabled={isSubmitting}

            aria-label="Close fix dialog"

            className="rounded-md p-2 text-[#6D7175] hover:bg-[#F1F2F3] disabled:opacity-50"

          >

            <X className="h-4 w-4" />

          </button>

        </div>



        <form onSubmit={handleSubmit} className="space-y-5 p-5">

          {/* Issue details */}

          <div className="rounded-lg border border-[#E1E3E5] bg-[#FAFAFA] p-4">

            <div className="mb-2 flex items-center justify-between gap-3">

              <span className="text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">

                Audit recommendation

              </span>



              <SeverityBadge priority={issue.priority} />

            </div>



            <h3 className="text-sm font-semibold text-[#202223]">
              Recommendation
            </h3>
            <p className="mt-2 whitespace-pre-line text-xs leading-relaxed text-[#6D7175]">
              {recommendation.example ||
                issue.example ||
                recommendation.description ||
                "No recommendation description available."}
            </p>



            <div className="mt-3 text-xs text-[#6D7175]">

              Store:{" "}

              <span className="font-semibold text-[#202223]">

                {shopDomain || "Unavailable"}

              </span>

            </div>



            <div className="mt-1 text-xs text-[#6D7175]">

              Affected products:{" "}

              <span className="font-semibold text-[#202223]">

                {issue.affectedProducts.length}

              </span>

            </div>



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



          {/* Backend issue configuration */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label
                htmlFor="store-fix-check-id"
                className="mb-1.5 block text-xs font-semibold text-[#202223]"
              >
                Check ID
              </label>
              <input
                id="store-fix-check-id"
                type="text"
                value={checkId}
                readOnly
                placeholder="Provided by audit metadata"
                className="w-full rounded-md border border-[#E1E3E5] bg-[#F1F2F3] px-3 py-2 text-xs"
              />
              <p className="mt-1 text-[10px] leading-relaxed text-[#6D7175]">
                Must match the check registered in your backend.
              </p>
            </div>



            <div>
              <label
                htmlFor="store-fix-issue-type"
                className="mb-1.5 block text-xs font-semibold text-[#202223]"
              >
                Issue type
              </label>
              <input
                id="store-fix-issue-type"
                type="text"
                value={issueType}
                readOnly
                placeholder="Provided by audit metadata"
                className="w-full rounded-md border border-[#E1E3E5] bg-[#F1F2F3] px-3 py-2 text-xs"
              />
              <p className="mt-1 text-[10px] leading-relaxed text-[#6D7175]">
                Must match a store-wide issue supported by the backend.
              </p>
            </div>

          </div>



          {/* Actual change payload */}

          <div>

            <div className="mb-1.5 flex items-center justify-between gap-3">

              <label

                htmlFor="store-fix-changes"

                className="block text-xs font-semibold text-[#202223]"

              >

                Changes payload

              </label>



              <span className="text-[10px] text-[#6D7175]">

                JSON array

              </span>

            </div>



            <textarea

              id="store-fix-changes"

              value={changesText}

              onChange={(event) => setChangesText(event.target.value)}

              disabled={isSubmitting || requestSucceeded}

              required

              rows={10}

              spellCheck={false}

              className="w-full resize-y rounded-md border border-[#E1E3E5] bg-[#FAFAFA] p-3 font-mono text-xs leading-relaxed text-[#202223] outline-none focus:border-[#D97706] disabled:opacity-60"

              placeholder={'Enter actual change objects as a JSON array'}

            />



            <p className="mt-2 text-[11px] leading-relaxed text-[#6D7175]">

              Use real Shopify IDs and the fields required by the selected

              backend handler. This editor does not invent product IDs,

              option IDs, attribute values, or units.

            </p>

          </div>



          {/* Validation error */}

          {validationError && (

            <div

              role="alert"

              className="flex gap-2 rounded-lg border border-[#FFC9C5] bg-[#FFF0EF] p-3 text-xs leading-relaxed text-[#D72C0D]"

            >

              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />

              <span>{validationError}</span>

            </div>

          )}



          {/* Request result */}

          {requestSucceeded && (

            <div

              role="status"

              className="flex gap-2 rounded-lg border border-[#A7F3D0] bg-[#ECFDF5] p-3 text-xs leading-relaxed text-[#065F46]"

            >

              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />

              <div>

                <p className="font-semibold">Backend reported success.</p>

                <p className="mt-1">

                  {responseMessage ||

                    "The store-wide fix request completed successfully."}

                </p>

              </div>

            </div>

          )}



          {requestFailed && (

            <div

              role="alert"

              className="flex gap-2 rounded-lg border border-[#FFC9C5] bg-[#FFF0EF] p-3 text-xs leading-relaxed text-[#D72C0D]"

            >

              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />

              <div>

                <p className="font-semibold">Could not apply the fix.</p>

                <p className="mt-1">

                  {responseMessage ||

                    "The request failed. Check the backend response and issue configuration."}

                </p>

              </div>

            </div>

          )}



          {/* Actions */}

          <div className="flex flex-col-reverse gap-2 border-t border-[#E1E3E5] pt-4 sm:flex-row sm:justify-end">

            <button

              type="button"

              onClick={onClose}

              disabled={isSubmitting}

              className="rounded-md border border-[#E1E3E5] px-4 py-2 text-xs font-semibold text-[#202223] hover:bg-[#F8F9FA] disabled:opacity-50"

            >

              {requestSucceeded ? "Close" : "Cancel"}

            </button>



            {!requestSucceeded && (

              <button

                type="submit"

                disabled={isSubmitting}

                className="inline-flex items-center justify-center gap-2 rounded-md bg-[#111111] px-4 py-2 text-xs font-semibold text-white hover:bg-[#333333] disabled:cursor-not-allowed disabled:opacity-50"

              >

                {isSubmitting ? (

                  <>

                    <LoaderCircle className="h-4 w-4 animate-spin" />

                    Applying fix...

                  </>

                ) : (

                  <>

                    <Wrench className="h-4 w-4" />

                    Review and apply fix

                  </>

                )}

              </button>

            )}

          </div>

        </form>

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
    affectedProducts: PropTypes.arrayOf(
      PropTypes.shape({
        product_id: PropTypes.oneOfType([
          PropTypes.string,
          PropTypes.number,
        ]),
        title: PropTypes.string,
      })
    ),
    raw: PropTypes.object,
  }).isRequired,
  shopDomain: PropTypes.string.isRequired,
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

          `https://geo.properoapps.in/api/audits/latest?shop_domain=${encodeURIComponent(

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

            `Failed to load the latest audit (${response.status}).`

          );

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

          setLoadError(

            error.message || "Unable to load the latest audit."

          );

          setLoading(false);

        }

      }

    }



    loadAudit();



    return () => {

      cancelled = true;

    };

  }, [shopDomain]);



  /*

   * Keep the complete recommendation in `raw`.

   * The Fix modal reads only real fields from this object.

   */

  
const allIssues = useMemo(() => {
  const products = Array.isArray(report?.products)
    ? report.products
    : [];

  const storeRecs = Array.isArray(report?.store_level_recommendations)
    ? report.store_level_recommendations
    : [];

  // The audit endpoint returns the registered issues for this audit.
  const auditIssues = Array.isArray(report?.issues)
    ? report.issues
    : [];

  return storeRecs.map((recommendation, index) => {
    const resolvedMetadata = resolveStoreFixMetadata(
      recommendation,
      auditIssues
    );

    // Prefer metadata attached to this recommendation by the backend.
    const raw = {
      ...recommendation,
      check_id:
        recommendation.check_id ||
        recommendation.fix_payload?.check_id ||
        resolvedMetadata.check_id,
      issue_type:
        recommendation.issue_type ||
        recommendation.fix_payload?.issue_type ||
        resolvedMetadata.issue_type,
    };

    return {
      key: `store-${index}`,
      priority: getPriority(recommendation.priority),
      enrichment: recommendation.enrichment || "Missing enrichment",
      why_it_matters_for_agents:
        recommendation.why_it_matters_for_agents || "",
      example: recommendation.example || "",
      affectedProducts: getAffectedProducts(recommendation, products),
      raw,
    };
  });
}, [
  report?.store_level_recommendations,
  report?.products,
  report?.issues,
]);



  const highCount = allIssues.filter(

    (issue) => issue.priority === "high"

  ).length;



  const mediumCount = allIssues.filter(

    (issue) => issue.priority === "medium"

  ).length;



  const lowCount = allIssues.filter(

    (issue) => issue.priority === "low"

  ).length;



  const filteredIssues = useMemo(() => {

    const query = search.trim().toLowerCase();



    return allIssues.filter((issue) => {

      const matchesSeverity =

        severity === "All" || issue.priority === severity.toLowerCase();



      const matchesSearch =

        !query ||

        issue.enrichment.toLowerCase().includes(query) ||

        issue.affectedProducts.some((product) =>

          String(product.title || "")

            .toLowerCase()

            .includes(query)

        );



      return matchesSeverity && matchesSearch;

    });

  }, [allIssues, search, severity]);



  return (

    <div className="mx-auto max-w-7xl space-y-6 p-8">

      {/* Header */}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">

        <div>

          <h1 className="text-xl font-bold tracking-tight text-[#202223]">

            Issues

          </h1>



          <p className="mt-0.5 text-sm text-[#6D7175]">

            Store-level issues and recommendations identified in your latest

            audit.

          </p>

        </div>



        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-[#E1E3E5] bg-white px-3 py-1.5 text-xs shadow-sm">

          <span className="font-semibold text-[#202223]">

            Audit Status:

          </span>



          <span className="font-bold text-[#D72C0D]">

            {highCount} High

          </span>



          <span className="text-[#E1E3E5]">•</span>



          <span className="font-bold text-[#8A6116]">

            {mediumCount} Medium

          </span>



          <span className="text-[#E1E3E5]">•</span>



          <span className="font-bold text-[#6D7175]">

            {lowCount} Low

          </span>

        </div>

      </div>



      {/* Search and severity filters */}

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

                className={`cursor-pointer rounded px-3 py-1.5 text-xs font-semibold transition-colors ${severity === value

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

            Showing{" "}

            <span className="font-bold text-[#202223]">

              {filteredIssues.length}

            </span>{" "}

            issues

          </div>



          <div className="text-[11px] text-[#6D7175]">

            Expand an issue to view details

          </div>

        </div>



        {loading ? (

          <div className="py-16 text-center">

            <LoaderCircle className="mx-auto mb-3 h-7 w-7 animate-spin text-[#D97706]" />

            <p className="text-sm font-semibold text-[#202223]">

              Loading audit issues...

            </p>

          </div>

        ) : loadError ? (

          <div className="py-16 text-center">

            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#D72C0D]" />



            <p className="text-sm font-semibold text-[#202223]">

              Unable to load issues

            </p>



            <p className="mt-1 text-xs text-[#6D7175]">

              {loadError}

            </p>

          </div>

        ) : !report ? (

          <div className="py-16 text-center">

            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#E1E3E5]" />



            <p className="text-sm font-semibold text-[#202223]">

              No audit report available

            </p>



            <p className="mt-1 text-xs text-[#6D7175]">

              Run an audit from the Dashboard first.

            </p>

          </div>

        ) : filteredIssues.length === 0 ? (

          <div className="py-12 text-center text-[#6D7175]">

            <AlertCircle className="mx-auto mb-2 h-8 w-8 text-[#E1E3E5]" />



            <p className="text-sm font-semibold text-[#202223]">

              No issues matching your filters

            </p>



            <p className="mt-1 text-xs">

              Try adjusting the search or severity filter.

            </p>

          </div>

        ) : (

          <div className="overflow-x-auto">

            <table className="w-full border-collapse text-left">

              <thead className="bg-[#F8F9FA] text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">

                <tr>

                  <th className="w-28 border-b border-[#E1E3E5] px-5 py-3">

                    Severity

                  </th>



                  <th className="border-b border-[#E1E3E5] px-5 py-3">

                    Issue

                  </th>



                  <th className="border-b border-[#E1E3E5] px-5 py-3">

                    Affected Products

                  </th>



                  <th className="border-b border-[#E1E3E5] px-5 py-3 text-right">

                    View Issue

                  </th>

                </tr>

              </thead>



              <tbody className="divide-y divide-[#E1E3E5] text-xs">

                {filteredIssues.map((issue) => {

                  const isExpanded = expandedKey === issue.key;
                  const recommendation = issue.raw || {};


                  const affectedLabel =

                    issue.affectedProducts.length > 0

                      ? `${issue.affectedProducts.length} product${issue.affectedProducts.length === 1 ? "" : "s"

                      }`

                      : "Store-wide";



                  return (

                    <Fragment key={issue.key}>

                      <tr

                        className="group cursor-pointer transition-colors hover:bg-[#F9FAFB]"

                        onClick={() =>

                          setExpandedKey(isExpanded ? null : issue.key)

                        }

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

                              setExpandedKey(

                                isExpanded ? null : issue.key

                              );

                            }}

                            className="inline-flex cursor-pointer items-center gap-1 rounded px-2.5 py-1 text-xs font-semibold text-[#8A6116] transition-colors hover:underline"

                          >

                            <span>

                              {isExpanded ? "Hide Issue" : "View Issue"}

                            </span>



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

                            {(
                              issue.why_it_matters_for_agents ||
                              recommendation.description ||
                              recommendation.recommendation ||
                              recommendation.enrichment
                            ) && (
                                <div className="mt-3">
                                  <p className="mb-1 text-xs font-semibold text-[#202223]">
                                    Recommendation
                                  </p>
                                  <p className="text-xs leading-relaxed text-[#6D7175]">
                                    {issue.why_it_matters_for_agents ||
                                      recommendation.description ||
                                      recommendation.recommendation ||
                                      recommendation.enrichment}
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

                                Review the actual change payload before

                                applying a store-wide fix.

                              </p>



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



      {/* Store-wide fix dialog */}

      {selectedIssue && (

        <StoreFixModal

          key={selectedIssue.key}

          issue={selectedIssue}

          shopDomain={shopDomain}

          onClose={() => setSelectedIssue(null)}

        />

      )}

    </div>

  );

}
