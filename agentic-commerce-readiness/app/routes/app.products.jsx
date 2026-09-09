import { useEffect, useMemo, useState } from "react";
import { Search, ChevronRight, Package } from "lucide-react";
import { useNavigate } from "react-router";

const STORAGE_KEY = "acr_latest_report";

function getProductScore(product) {
  if (typeof product.readiness_score === "number") {
    return Math.max(0, Math.min(100, Math.round(product.readiness_score)));
  }

  if (typeof product.score === "number") {
    return Math.max(0, Math.min(100, Math.round(product.score)));
  }

  const issues = product.missing_enrichments || [];

  if (!issues.length) return 100;

  const high = issues.filter((item) => item.priority === "high").length;
  const medium = issues.filter((item) => item.priority === "medium").length;
  const low = issues.filter((item) => item.priority === "low").length;

  const penalty = high * 20 + medium * 10 + low * 5;

  return Math.max(0, Math.min(100, 100 - penalty));
}

function getStatus(score) {
  if (score >= 80) {
    return {
      label: "Ready",
      className: "bg-green-50 text-[var(--app-green)]",
    };
  }

  if (score >= 50) {
    return {
      label: "Needs Work",
      className: "bg-orange-50 text-orange-700",
    };
  }

  return {
    label: "Not Ready",
    className: "bg-red-50 text-red-700",
  };
}

function ScoreBadge({ score }) {
  const status = getStatus(score);

  return (
    <div className="flex items-center gap-2">
      <span className="text-sm font-extrabold text-[var(--app-text)]">
        {score}
      </span>

      <span
        className={`rounded-full px-2.5 py-1 text-[10px] font-bold ${status.className}`}
      >
        {status.label}
      </span>
    </div>
  );
}

function ProductRow({ product, onClick }) {
  const score = getProductScore(product);
  const issues = product.missing_enrichments || [];

  const high = issues.filter((item) => item.priority === "high").length;
  const medium = issues.filter((item) => item.priority === "medium").length;

  return (
    <button
      type="button"
      onClick={onClick}
      className="group grid w-full grid-cols-1 gap-4 border-b border-[var(--app-border)] px-5 py-5 text-left transition-colors hover:bg-[var(--app-bg)] md:grid-cols-[minmax(0,1fr)_120px_150px_40px] md:items-center"
    >
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-[var(--app-border)] bg-[var(--app-bg)]">
          {product.image_url || product.image ? (
            <img
              src={product.image_url || product.image}
              alt=""
              className="h-full w-full object-cover"
            />
          ) : (
            <Package size={19} className="text-[var(--app-muted)]" />
          )}
        </div>

        <div className="min-w-0">
          <div className="truncate text-sm font-bold text-[var(--app-green)]">
            {product.title || "Untitled product"}
          </div>

          <div className="mt-1 truncate text-xs text-[var(--app-muted)]">
            {product.product_id
              ? `Product ID: ${product.product_id}`
              : "Product ID unavailable"}
          </div>
        </div>
      </div>

      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)] md:hidden">
          Readiness
        </div>

        <div className="mt-1 md:mt-0">
          <ScoreBadge score={score} />
        </div>
      </div>

      <div>
        <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)] md:hidden">
          Issues
        </div>

        <div className="mt-1 flex items-center gap-2 md:mt-0">
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
            <span className="text-xs font-semibold text-[var(--app-green)]">
              No issues
            </span>
          )}
        </div>
      </div>

      <div className="hidden justify-end md:flex">
        <ChevronRight
          size={18}
          className="text-[var(--app-muted)] transition-transform group-hover:translate-x-1"
        />
      </div>
    </button>
  );
}

export default function Products() {
  const navigate = useNavigate();

  const [report, setReport] = useState(null);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);

      if (stored) {
        setReport(JSON.parse(stored));
      }
    } catch (error) {
      console.warn("Could not load stored audit report.", error);
    }
  }, []);

  const products = report?.products || [];

  const filteredProducts = useMemo(() => {
    const query = search.trim().toLowerCase();

    return products.filter((product) => {
      const title = String(product.title || "").toLowerCase();
      const id = String(product.product_id || "").toLowerCase();

      const score = getProductScore(product);

      const matchesSearch =
        !query || title.includes(query) || id.includes(query);

      const matchesStatus =
        status === "all" ||
        (status === "ready" && score >= 80) ||
        (status === "needs-work" && score >= 50 && score < 80) ||
        (status === "not-ready" && score < 50);

      return matchesSearch && matchesStatus;
    });
  }, [products, search, status]);

  const readyCount = products.filter(
    (product) => getProductScore(product) >= 80
  ).length;

  const needsWorkCount = products.filter((product) => {
    const score = getProductScore(product);
    return score >= 50 && score < 80;
  }).length;

  const notReadyCount = products.filter(
    (product) => getProductScore(product) < 50
  ).length;

  return (
    <div className="min-h-screen bg-[var(--app-bg)] px-5 py-8 text-[var(--app-text)] md:px-8">
      <div className="mx-auto max-w-6xl">
        {/* Header */}
        <div className="mb-7">
          <div className="mb-2 text-[10px] font-extrabold uppercase tracking-[0.1em] text-[var(--app-orange)]">
            Catalog
          </div>

          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <h1 className="text-3xl font-extrabold tracking-tight text-[var(--app-green)]">
                Products
              </h1>

              <p className="mt-1.5 max-w-2xl text-sm leading-relaxed text-[var(--app-muted)]">
                Review product-level readiness and identify the catalog
                attributes that need attention for agentic commerce.
              </p>
            </div>

            <div className="rounded-xl border border-[var(--app-border)] bg-white px-4 py-3">
              <div className="text-[10px] font-bold uppercase tracking-wider text-[var(--app-muted)]">
                Products Analyzed
              </div>

              <div className="mt-0.5 text-2xl font-extrabold text-[var(--app-green)]">
                {products.length}
              </div>
            </div>
          </div>
        </div>

        {/* Status summary */}
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-2xl border border-[var(--app-border)] bg-white p-4">
            <div className="text-xs font-bold text-[var(--app-muted)]">
              Ready
            </div>

            <div className="mt-1 text-2xl font-extrabold text-[var(--app-green)]">
              {readyCount}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--app-border)] bg-white p-4">
            <div className="text-xs font-bold text-[var(--app-muted)]">
              Needs Work
            </div>

            <div className="mt-1 text-2xl font-extrabold text-orange-700">
              {needsWorkCount}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--app-border)] bg-white p-4">
            <div className="text-xs font-bold text-[var(--app-muted)]">
              Not Ready
            </div>

            <div className="mt-1 text-2xl font-extrabold text-red-700">
              {notReadyCount}
            </div>
          </div>
        </div>

        {/* Search + filter */}
        <div className="mb-5 flex flex-col gap-3 md:flex-row">
          <div className="relative flex-1">
            <Search
              size={17}
              className="absolute left-3.5 top-1/2 -translate-y-1/2 text-[var(--app-muted)]"
            />

            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search products..."
              className="h-11 w-full rounded-xl border border-[var(--app-border)] bg-white pl-10 pr-4 text-sm text-[var(--app-text)] outline-none focus:border-[var(--app-green)]"
            />
          </div>

          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="h-11 rounded-xl border border-[var(--app-border)] bg-white px-4 text-sm font-semibold text-[var(--app-text)] outline-none"
          >
            <option value="all">All products</option>
            <option value="ready">Ready</option>
            <option value="needs-work">Needs Work</option>
            <option value="not-ready">Not Ready</option>
          </select>
        </div>

        {/* Product table */}
        <div className="overflow-hidden rounded-2xl border border-[var(--app-border)] bg-white">
          <div className="hidden grid-cols-[minmax(0,1fr)_120px_150px_40px] gap-4 border-b border-[var(--app-border)] bg-[var(--app-bg)] px-5 py-3 text-[10px] font-extrabold uppercase tracking-wider text-[var(--app-muted)] md:grid">
            <div>Product</div>
            <div>Readiness</div>
            <div>Issues</div>
            <div />
          </div>

          {filteredProducts.length > 0 ? (
            filteredProducts.map((product, index) => (
              <ProductRow
                key={product.product_id || product.id || index}
                product={product}
                onClick={() => {
                  const id = product.product_id || product.id;

                  if (id) {
                    navigate(`/app/products/${encodeURIComponent(id)}`);
                  }
                }}
              />
            ))
          ) : (
            <div className="px-6 py-16 text-center">
              <Package
                size={28}
                className="mx-auto mb-3 text-[var(--app-muted)]"
              />

              {!report ? (
                <>
                  <h2 className="text-lg font-extrabold text-[var(--app-green)]">
                    No audit report available
                  </h2>

                  <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-[var(--app-muted)]">
                    Run an audit from the Dashboard first. Your analyzed
                    products will appear here after the audit completes.
                  </p>
                </>
              ) : (
                <>
                  <h2 className="text-lg font-extrabold text-[var(--app-green)]">
                    No products found
                  </h2>

                  <p className="mt-2 text-sm text-[var(--app-muted)]">
                    Try changing your search or filter.
                  </p>
                </>
              )}
            </div>
          )}
        </div>

        <div className="mt-5 text-center text-xs text-[var(--app-muted)]">
          Showing {filteredProducts.length} of {products.length} products
        </div>
      </div>
    </div>
  );
}