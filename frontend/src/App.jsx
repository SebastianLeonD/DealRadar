import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchCategories, fetchDeals, fetchFilters, fetchStatus, fetchStores, postNotify, postRefresh,
} from "./api.js";
import DealGrid from "./components/DealGrid.jsx";
import DealModal from "./components/DealModal.jsx";
import Sidebar from "./components/Sidebar.jsx";
import SourceLog from "./components/SourceLog.jsx";
import SubNav from "./components/SubNav.jsx";
import Ticker from "./components/Ticker.jsx";
import TopBar from "./components/TopBar.jsx";

const DEFAULT_FILTERS = {
  category: "All", items: [], query: "", store: "All",
  minPrice: "", maxPrice: "", age: "48", order: "new",
  colors: [], sizes: [], minDiscount: "",
};

export default function App() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [saleMode, setSaleMode] = useState(false);
  const [limit, setLimit] = useState(100);
  const [total, setTotal] = useState(0);
  const [deals, setDeals] = useState([]);
  const [categories, setCategories] = useState([]);
  const [stores, setStores] = useState([]);
  const [facets, setFacets] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [openIndex, setOpenIndex] = useState(null);
  const [toast, setToast] = useState("");
  const toastTimer = useRef(null);

  const showToast = (msg) => {
    setToast(msg);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 4000);
  };

  const loadAll = useCallback(async () => {
    const effective = { ...filters, limit, order: saleMode ? "best" : filters.order };
    try {
      const [dealsRes, catsRes, storesRes, statusRes, facetsRes] = await Promise.all([
        fetchDeals(effective), fetchCategories(), fetchStores(filters.category), fetchStatus(), fetchFilters(),
      ]);
      setDeals(dealsRes.deals);
      setTotal(dealsRes.total ?? dealsRes.deals.length);
      setCategories(catsRes.categories);
      setStores(storesRes.stores);
      setStatus(statusRes);
      setFacets(facetsRes);
    } catch (e) {
      showToast("Couldn't reach the DealRadar API — is the backend running?");
    }
    setLoading(false);
  }, [filters, saleMode, limit]);

  // reload on any filter change (debounced for typing), plus a 60s live poll
  useEffect(() => {
    const t = setTimeout(loadAll, 250);
    return () => clearTimeout(t);
  }, [loadAll]);
  useEffect(() => {
    const interval = setInterval(loadAll, 60000);
    return () => clearInterval(interval);
  }, [loadAll]);

  const patchFilters = (patch) => {
    if ("saleMode" in patch) {
      setSaleMode(patch.saleMode);
      const { saleMode: _, ...rest } = patch;
      patch = rest;
    }
    setLimit(100); // filter change resets paging
    if (Object.keys(patch).length) setFilters((f) => ({ ...f, ...patch }));
  };

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      const r = await postRefresh();
      let msg = `Fetched ${r.fetched} deals (${r.new} new)`;
      if (r.ai_scored) msg += `, AI-scored ${r.ai_scored}`;
      if (r.source_errors?.length) msg += ` — ${r.source_errors.length} source(s) failed`;
      showToast(msg);
      await loadAll();
    } catch (e) {
      showToast("Refresh failed: " + e.message);
    }
    setRefreshing(false);
  };

  const onNotify = async () => {
    try {
      const { ok, body } = await postNotify();
      showToast(ok ? `Posted ${body.posted} deals to Discord` : body.detail || "Failed");
    } catch (e) {
      showToast("Discord post failed: " + e.message);
    }
  };

  const catLabel = filters.category === "All" ? "All Deals" : filters.category;

  return (
    <>
      <TopBar
        query={filters.query}
        onQuery={(query) => patchFilters({ query })}
        onRefresh={onRefresh}
        onNotify={onNotify}
        refreshing={refreshing}
        status={status}
      />
      <SubNav
        categories={categories}
        activeCategory={filters.category}
        saleMode={saleMode}
        onCategory={(category) => {
          setSaleMode(false);
          // section change resets section-specific filters
          patchFilters({ category, store: "All", items: [], sizes: [], colors: [] });
        }}
        onToggleSale={() => setSaleMode((s) => !s)}
      />
      <Ticker deals={deals} />
      <div className="page">
        <div className="titlerow">
          <h2>{saleMode ? "The Hot List" : `Today's Board — ${catLabel}`}</h2>
          <span className="stylecount">
            {total > deals.length ? `${deals.length} OF ${total}` : deals.length} DEAL{total === 1 ? "" : "S"} ON THE WIRE
          </span>
        </div>
        <SourceLog status={status} />
        <div className="pagegrid">
          <Sidebar filters={filters} category={filters.category} stores={stores} facets={facets} saleMode={saleMode} onChange={patchFilters} />
          <main>
            <DealGrid deals={deals} loading={loading} onOpen={setOpenIndex} />
            {total > deals.length && (
              <button className="showmore" onClick={() => setLimit((l) => l + 100)}>
                ▾ SHOW MORE ({total - deals.length} REMAINING)
              </button>
            )}
          </main>
        </div>
      </div>
      <DealModal deal={openIndex != null ? deals[openIndex] : null} onClose={() => setOpenIndex(null)} />
      {toast ? <div className="toast show">{toast}</div> : null}
    </>
  );
}
