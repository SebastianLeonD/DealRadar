import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchCategories, fetchDeals, fetchStatus, fetchStores, postNotify, postRefresh,
} from "./api.js";
import DealGrid from "./components/DealGrid.jsx";
import DealModal from "./components/DealModal.jsx";
import FilterBar from "./components/FilterBar.jsx";
import SourceLog from "./components/SourceLog.jsx";
import SubNav from "./components/SubNav.jsx";
import Ticker from "./components/Ticker.jsx";
import TopBar from "./components/TopBar.jsx";

const DEFAULT_FILTERS = {
  category: "All", item: "All", query: "", store: "All",
  maxPrice: "", age: "48", order: "new",
};

export default function App() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [saleMode, setSaleMode] = useState(false);
  const [deals, setDeals] = useState([]);
  const [categories, setCategories] = useState([]);
  const [stores, setStores] = useState([]);
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
    const effective = { ...filters, order: saleMode ? "best" : filters.order };
    try {
      const [dealsRes, catsRes, storesRes, statusRes] = await Promise.all([
        fetchDeals(effective), fetchCategories(), fetchStores(), fetchStatus(),
      ]);
      setDeals(dealsRes.deals);
      setCategories(catsRes.categories);
      setStores(storesRes.stores);
      setStatus(statusRes);
    } catch (e) {
      showToast("Couldn't reach the DealRadar API — is the backend running?");
    }
    setLoading(false);
  }, [filters, saleMode]);

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
        onCategory={(category) => { setSaleMode(false); patchFilters({ category }); }}
        onToggleSale={() => setSaleMode((s) => !s)}
      />
      <Ticker deals={deals} />
      <div className="page">
        <div className="titlerow">
          <h2>{saleMode ? "The Hot List" : `Today's Board — ${catLabel}`}</h2>
          <span className="stylecount">
            {deals.length} DEAL{deals.length === 1 ? "" : "S"} ON THE WIRE
          </span>
        </div>
        <FilterBar filters={filters} stores={stores} saleMode={saleMode} onChange={patchFilters} />
        <SourceLog status={status} />
        <DealGrid deals={deals} loading={loading} onOpen={setOpenIndex} />
      </div>
      <DealModal deal={openIndex != null ? deals[openIndex] : null} onClose={() => setOpenIndex(null)} />
      {toast ? <div className="toast show">{toast}</div> : null}
    </>
  );
}
