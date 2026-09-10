//agentic-commerce-readiness/app/routes/app.issues.jsx
import { useEffect, useMemo, useState, Fragment } from "react";
import { useNavigate, useRouteLoaderData } from "react-router";
import { Search, AlertCircle, ChevronDown, ChevronUp } from "lucide-react";

function SeverityBadge({ priority }) {
  if (priority === "high") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-[#FFC9C5] bg-[#FFF0EF] px-2.5 py-0.5 text-xs font-semibold text-[#D72C0D]">
        <span className="h-2 w-2 rounded-full bg-[#D72C0D]" />
        High
      </span>
    );
  }

  if (priority === "low") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-[#E1E3E5] bg-[#F1F2F3] px-2.5 py-0.5 text-xs font-semibold text-[#6D7175]">
        <span className="h-2 w-2 rounded-full bg-[#6D7175]" />
        Low
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[#FFE0A3] bg-[#FFF5E5] px-2.5 py-0.5 text-xs font-semibold text-[#8A6116]">
      <span className="h-2 w-2 rounded-full bg-[#FFB100]" />
      Medium
    </span>
  );
}

export default function Issues() {
  const navigate = useNavigate();
  const { shopDomain } = useRouteLoaderData("routes/app");

  const [report, setReport] = useState(null);
  const [search, setSearch] = useState("");
  const [severity, setSeverity] = useState("All");
  const [expandedKey, setExpandedKey] = useState(null);

  useEffect(() => {
    if (!shopDomain) return;

    let cancelled = false;

    const loadAudit = async () => {
      try {
        const response = await fetch(
          `https://geo.properoapps.in/api/audits/latest?shop_domain=${encodeURIComponent(shopDomain)}`
        );

        if (response.status === 404) {
          if (!cancelled) setReport(null);
          return;
        }

        if (!response.ok) throw new Error(`Failed to load audit: ${response.status}`);

        const data = await response.json();
        if (!cancelled) setReport(data);
      } catch (err) {
        console.error("Failed to load latest audit:", err);
        if (!cancelled) setReport(null);
      }
    };

    loadAudit();

    return () => {
      cancelled = true;
    };
  }, [shopDomain]);

  const products = report?.products || [];
  const storeRecs = report?.store_level_recommendations || [];
  const allIssues = useMemo(() => {
  return storeRecs.map((rec, index) => {
    const affectedProducts = Array.isArray(rec.affected_product_ids)
      ? products.filter((p) =>
          rec.affected_product_ids.map(String).includes(String(p.product_id))
        )
      : [];

    return {
      key: `store-${index}`,
      priority: rec.priority,
      enrichment: rec.enrichment,
      why_it_matters_for_agents: rec.why_it_matters_for_agents,
      example: rec.example,
      affectedProducts,
    };
  });
}, [storeRecs, products]);

  const highCount = allIssues.filter((i) => i.priority === "high").length;
  const mediumCount = allIssues.filter((i) => i.priority === "medium").length;
  const lowCount = allIssues.filter((i) => i.priority === "low").length;

  const filteredIssues = useMemo(() => {
  const query = search.trim().toLowerCase();

  return allIssues.filter((issue) => {
    const matchesSeverity =
      severity === "All" ||
      issue.priority === severity.toLowerCase();

    const matchesSearch =
      !query ||
      (issue.enrichment || "").toLowerCase().includes(query) ||
      issue.affectedProducts.some((p) =>
        (p.title || "").toLowerCase().includes(query)
      );

    return matchesSeverity && matchesSearch;
  });
}, [allIssues, search, severity]);

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#202223]">Issues</h1>
          <p className="text-sm text-[#6D7175] mt-0.5">
            Store-level issues and recommendations identified in your latest audit.
          </p>
        </div>

        <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-lg border border-[#E1E3E5] text-xs shadow-sm">
          <span className="font-semibold text-[#202223]">Audit Status:</span>
          <span className="text-[#D72C0D] font-bold">{highCount} High</span>
          <span className="text-[#E1E3E5]">•</span>
          <span className="text-[#8A6116] font-bold">{mediumCount} Medium</span>
          <span className="text-[#E1E3E5]">•</span>
          <span className="text-[#6D7175] font-bold">{lowCount} Low</span>
        </div>
      </div>

      {/* Search + filters */}
      <div className="bg-white rounded-xl border border-[#E1E3E5] p-4 shadow-sm space-y-3">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[#6D7175] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search issues or products..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-xs rounded-md border border-[#E1E3E5] focus:border-[#008060] focus:ring-1 focus:ring-[#008060] outline-none text-[#202223] placeholder:text-[#6D7175]"
            />
          </div>

          <div className="flex items-center gap-1 bg-[#F1F2F3] p-1 rounded-md shrink-0">
            {["All", "High", "Medium", "Low"].map((sev) => (
              <button
                key={sev}
                onClick={() => setSeverity(sev)}
                className={`px-3 py-1.5 rounded text-xs font-semibold transition-colors cursor-pointer ${
                  severity === sev ? "bg-white text-[#202223] shadow-sm" : "text-[#6D7175] hover:text-[#202223]"
                }`}
              >
                {sev}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Issues table */}
      <div className="bg-white rounded-xl border border-[#E1E3E5] shadow-sm overflow-hidden">
        <div className="p-4 border-b border-[#E1E3E5] flex items-center justify-between text-xs text-[#6D7175]">
          <div>
            Showing <span className="font-bold text-[#202223]">{filteredIssues.length}</span> issues
          </div>
          <div className="text-[11px] text-[#6D7175]">Click any row to view diagnostic details</div>
        </div>

        {!report ? (
          <div className="py-16 text-center">
            <AlertCircle className="w-8 h-8 text-[#E1E3E5] mx-auto mb-2" />
            <p className="font-semibold text-sm text-[#202223]">No audit report available</p>
            <p className="text-xs text-[#6D7175] mt-1">Run an audit from the Dashboard first.</p>
          </div>
        ) : filteredIssues.length === 0 ? (
          <div className="py-12 text-center text-[#6D7175]">
            <AlertCircle className="w-8 h-8 text-[#E1E3E5] mx-auto mb-2" />
            <p className="font-semibold text-sm text-[#202223]">No issues matching your filters</p>
            <p className="text-xs text-[#6D7175] mt-1">Try adjusting the search or reset the filters.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-[#F8F9FA] text-[10px] font-bold text-[#6D7175] uppercase tracking-wider">
                <tr>
                  <th className="py-3 px-5 border-b border-[#E1E3E5] w-28">Severity</th>
                  <th className="py-3 px-5 border-b border-[#E1E3E5]">Issue</th>
                  <th className="py-3 px-5 border-b border-[#E1E3E5]">Affected Products</th>
                  <th className="py-3 px-5 border-b border-[#E1E3E5] text-right">View Issue</th>
                </tr>
              </thead>
              <tbody className="text-xs divide-y divide-[#E1E3E5]">
                {filteredIssues.map((issue) => {
                  const isExpanded = expandedKey === issue.key;
                  const affectedLabel =
                    issue.affectedProducts.length > 0
                      ? `${issue.affectedProducts.length} product${
                          issue.affectedProducts.length === 1 ? "" : "s"
                        }`
                      : "Store-wide";

                  return (
                    <Fragment key={issue.key}>
                      <tr
                        className="hover:bg-[#F9FAFB] transition-colors cursor-pointer group"
                        onClick={() => setExpandedKey(isExpanded ? null : issue.key)}
                      >
                        <td className="py-4 px-5 whitespace-nowrap align-top">
                          <SeverityBadge priority={issue.priority} />
                        </td>

                        <td className="py-4 px-5 align-top">
                          <div className="font-semibold text-[#202223] group-hover:text-[#008060] transition-colors">
                            {issue.enrichment || "Missing enrichment"}
                          </div>
                        </td>

                        <td className="py-4 px-5 whitespace-nowrap align-top">
                          <span className="text-[#202223] font-medium inline-flex items-center gap-1.5">
                            {affectedLabel}
                          </span>
                        </td>

                        <td className="py-4 px-5 text-right whitespace-nowrap align-top">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setExpandedKey(isExpanded ? null : issue.key);
                            }}
                            className="text-xs font-semibold text-[#008060] hover:underline px-2.5 py-1 rounded transition-colors inline-flex items-center gap-1 cursor-pointer"
                          >
                            <span>View Issue</span>
                            {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </button>
                        </td>
                      </tr>

                      {isExpanded && (
                        <tr>
                          <td colSpan={4} className="border-t border-[#F1F2F3] bg-[#FAFAFA] px-5 py-4">
                            {issue.why_it_matters_for_agents && (
                              <p className="text-xs leading-relaxed text-[#4a5568]">
                                {issue.why_it_matters_for_agents}
                              </p>
                            )}

                            {issue.example && (
                              <div className="mt-3 rounded-lg border-l-2 border-[#c47d52] bg-white px-3 py-2 font-mono text-[11px] text-[#6D7175] whitespace-pre-line">
                                {issue.example}
                              </div>
                            )}

                            {issue.affectedProducts.length > 0 && (
                              <div className="mt-3">
                                <div className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-[#6D7175]">
                                  Affected products
                                </div>
                                <div className="flex flex-wrap gap-2">
                                  {issue.affectedProducts.map((p) => (
                                    <button
                                      key={p.product_id}
                                      onClick={(e) => {
                                        e.stopPropagation();
                                        navigate(
                                          `/app/products/detail?id=${encodeURIComponent(p.product_id)}`
                                        );
                                      }}
                                      className="rounded-full border border-[#E1E3E5] bg-white px-3 py-1 text-xs font-semibold text-[#008060] hover:underline"
                                    >
                                      {p.title || p.product_id}
                                    </button>
                                  ))}
                                </div>
                              </div>
                            )}
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
    </div>
  );
}