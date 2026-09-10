//agentic-commerce-readiness/app/routes/app.products.jsx
import { useEffect, useMemo, useState } from "react";
import { Search, Package } from "lucide-react";
import { useNavigate, useRouteLoaderData } from "react-router";

function getProductStatus(product) {
  const issues = product.missing_enrichments || [];

  const hasHigh = issues.some((item) => item.priority === "high");
  const hasOtherIssues = issues.some(
    (item) => item.priority === "medium" || item.priority === "low"
  );

  if (hasHigh) {
    return {
      label: "Critical",
      className: "bg-[#FFF0EF] text-[#D72C0D] border border-[#FFC9C5]",
    };
  }

  if (hasOtherIssues) {
    return {
      label: "Needs attention",
      className: "bg-[#FFF5E5] text-[#8A6116] border border-[#FFE0A3]",
    };
  }

  return {
    label: "Ready",
    className: "bg-[#E6F4EA] text-[#008060] border border-[#B4E3C8]",
  };
}

function MetricCard({ label, value, labelClassName, valueClassName }) {
  return (
    <div className="rounded-xl border border-[#E1E3E5] bg-white p-5 shadow-sm">
      <span className={`block text-xs font-bold uppercase ${labelClassName}`}>{label}</span>
      <span className={`mt-1 block text-2xl font-bold ${valueClassName}`}>{value}</span>
    </div>
  );
}

const PAGE_SIZE = 10;

export default function Products() {
  const navigate = useNavigate();
  const { shopDomain } = useRouteLoaderData("routes/app");

  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All");
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!shopDomain) return;

    let cancelled = false;

    const loadProducts = async () => {
      try {
        setError(null);

        const response = await fetch(
          `https://geo.properoapps.in/api/products?shop_domain=${encodeURIComponent(shopDomain)}`
        );

        if (response.status === 404) {
          if (!cancelled) setReport(null);
          return;
        }

        if (!response.ok) {
          throw new Error(`Failed to load products: ${response.status}`);
        }

        const data = await response.json();
        if (!cancelled) setReport(data);
      } catch (err) {
        console.error("Failed to load audited products:", err);
        if (!cancelled) setError("Could not load audited products.");
      }
    };

    loadProducts();

    return () => {
      cancelled = true;
    };
  }, [shopDomain]);

  const products = report?.products || [];

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();

    return products.filter((product) => {
      const title = String(product.title || "").toLowerCase();
      const id = String(product.product_id || "").toLowerCase();
      const matchesSearch = !query || title.includes(query) || id.includes(query);

      const productStatus = getProductStatus(product).label;
      const matchesStatus = status === "All" || productStatus === status;

      return matchesSearch && matchesStatus;
    });
  }, [products, search, status]);

  useEffect(() => {
    setPage(1);
  }, [search, status, products.length]);

  const totalPages = Math.max(1, Math.ceil(filteredProducts.length / PAGE_SIZE));
  const pagedProducts = filteredProducts.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const readyCount = products.filter((p) => getProductStatus(p).label === "Ready").length;
  const needsAttentionCount = products.filter(
    (p) => getProductStatus(p).label === "Needs attention"
  ).length;
  const criticalCount = products.filter((p) => getProductStatus(p).label === "Critical").length;

  const goToProduct = (product) => {
    if (!product.product_id) return;
    navigate(`/app/products/detail?id=${encodeURIComponent(product.product_id)}`);
  };

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-[#202223]">Products</h1>
          <p className="text-sm text-[#6D7175] mt-0.5">
            Review product-level readiness from your completed audits. Only audited
            products appear here — not your full Shopify catalog.
          </p>
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Products Audited"
          value={products.length}
          labelClassName="text-[#6D7175]"
          valueClassName="text-[#202223]"
        />
        <MetricCard
          label="Needs Attention"
          value={needsAttentionCount}
          labelClassName="text-[#8A6116]"
          valueClassName="text-[#8A6116]"
        />
        <MetricCard
          label="Ready"
          value={readyCount}
          labelClassName="text-[#008060]"
          valueClassName="text-[#008060]"
        />
        <MetricCard
          label="Critical"
          value={criticalCount}
          labelClassName="text-[#D72C0D]"
          valueClassName="text-[#D72C0D]"
        />
      </div>

      {/* Search + filter */}
      <div className="bg-white rounded-xl border border-[#E1E3E5] p-4 shadow-sm">
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-[#6D7175] absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search products by title or product ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-xs rounded-md border border-[#E1E3E5] focus:border-[#008060] focus:ring-1 focus:ring-[#008060] outline-none text-[#202223] placeholder:text-[#6D7175]"
            />
          </div>

          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="bg-[#F6F6F7] border border-[#E1E3E5] rounded-md py-1.5 px-2.5 font-semibold text-[#202223] text-xs outline-none focus:border-[#008060]"
          >
            <option value="All">All Status</option>
            <option value="Critical">Critical</option>
            <option value="Needs attention">Needs attention</option>
            <option value="Ready">Ready</option>
          </select>
        </div>
      </div>

      {/* Products table */}
      <div className="bg-white rounded-xl border border-[#E1E3E5] shadow-sm overflow-hidden">
        {pagedProducts.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead className="bg-[#F8F9FA] text-[10px] font-bold text-[#6D7175] uppercase tracking-wider">
                <tr>
                  <th className="py-3 px-6 border-b border-[#E1E3E5]">Product</th>
                  <th className="py-3 px-6 border-b border-[#E1E3E5]">Issues</th>
                  <th className="py-3 px-6 border-b border-[#E1E3E5]">Status</th>
                  <th className="py-3 px-6 border-b border-[#E1E3E5] text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E1E3E5] text-xs">
                {pagedProducts.map((product) => {
                  const productStatus = getProductStatus(product);
                  const issues = product.missing_enrichments || [];
                  const high = issues.filter((i) => i.priority === "high").length;
                  const medium = issues.filter((i) => i.priority === "medium").length;

                  return (
                    <tr
                      key={product.product_id}
                      onClick={() => goToProduct(product)}
                      className="hover:bg-[#F9FAFB] transition-colors cursor-pointer group"
                    >
                      <td className="py-4 px-6">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-md border border-[#E1E3E5] bg-[#F1F2F3] flex items-center justify-center shrink-0">
                            <Package size={16} className="text-[#6D7175]" />
                          </div>
                          <div>
                            <div className="font-semibold text-[#202223] group-hover:text-[#008060] transition-colors">
                              {product.title || "Untitled product"}
                            </div>
                            <div className="text-[11px] text-[#6D7175] font-mono mt-0.5 truncate max-w-[220px]">
                              {product.product_id || "ID unavailable"}
                            </div>
                          </div>
                        </div>
                      </td>

                      <td className="py-4 px-6 whitespace-nowrap">
                        <div className="flex items-center gap-2">
                          {high > 0 && (
                            <span className="rounded-full bg-red-50 px-2.5 py-1 text-[10px] font-bold text-red-700">
                              {high} High
                            </span>
                          )}
                          {medium > 0 && (
                            <span className="rounded-full bg-orange-50 px-2.5 py-1 text-[10px] font-bold text-orange-700">
                              {medium} Medium
                            </span>
                          )}
                          {!high && !medium && (
                            <span className="text-[#6D7175] font-medium">No issues</span>
                          )}
                        </div>
                      </td>

                      <td className="py-4 px-6 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold ${productStatus.className}`}
                        >
                          {productStatus.label}
                        </span>
                      </td>

                      <td
                        className="py-4 px-6 text-right whitespace-nowrap"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <button
                          onClick={() => goToProduct(product)}
                          className="px-3 py-1 rounded text-xs font-semibold text-[#008060] hover:underline cursor-pointer"
                        >
                          {productStatus.label === "Critical" ? "Review" : "View"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="px-6 py-16 text-center">
            <Package size={28} className="mx-auto mb-3 text-[#6D7175]" />
            {!report ? (
              <>
                <h2 className="text-lg font-extrabold text-[#008060]">
                  No audit report available
                </h2>
                <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-[#6D7175]">
                  Run an audit from the Dashboard first. Your analyzed products will
                  appear here after the audit completes.
                </p>
              </>
            ) : (
              <>
                <h2 className="text-lg font-extrabold text-[#008060]">No products found</h2>
                <p className="mt-2 text-sm text-[#6D7175]">
                  Try changing your search or filter.
                </p>
              </>
            )}
          </div>
        )}

        {filteredProducts.length > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-[#E1E3E5] px-6 py-4">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-lg border border-[#E1E3E5] px-4 py-2 text-sm font-semibold text-[#202223] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>

            <span className="text-sm text-[#6D7175]">
              Page {page} of {totalPages}
            </span>

            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded-lg border border-[#E1E3E5] px-4 py-2 text-sm font-semibold text-[#202223] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </div>

      <div className="text-center text-xs text-[#6D7175]">
        Showing {pagedProducts.length} of {filteredProducts.length} products
      </div>
    </div>
  );
}