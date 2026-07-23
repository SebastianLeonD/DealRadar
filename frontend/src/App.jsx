import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchCategories, fetchDeals, fetchFilters, fetchLive, fetchStatus, fetchStores, postNotify, postRefresh,
} from "./api.js";
import { useSaved } from "./saved.js";
import DealGrid from "./components/DealGrid.jsx";
import DealModal from "./components/DealModal.jsx";
import Sidebar from "./components/Sidebar.jsx";
import SourceLog from "./components/SourceLog.jsx";
import SubNav from "./components/SubNav.jsx";
import Ticker from "./components/Ticker.jsx";
import TopBar from "./components/TopBar.jsx";

const DEFAULT_FILTERS = {
  category: "All", items: [], query: "", stores: [],
  minPrice: "", maxPrice: "", age: "48", order: "new",
  colors: [], sizes: [], minDiscount: "",
};

export default function App() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [saleMode, setSaleMode] = useState(false);
  const { saved, toggle: toggleSave } = useSaved();
  const savedSet = new Set(saved.map((d) => d.url));
  const [savedView, setSavedView] = useState(false);
  const [liveUrls, setLiveUrls] = useState(null); // null until we've checked
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

  // in the saved view, ask the server which saved deals are still on sale
  useEffect(() => {
    if (!savedView) return;
    let cancelled = false;
    setLiveUrls(null);
    fetchLive(saved.map((d) => d.url))
      .then((rows) => !cancelled && setLiveUrls(new Set(rows.map((r) => r.url))))
      .catch(() => !cancelled && setLiveUrls(new Set(saved.map((d) => d.url)))); // on error, assume all live
    return () => { cancelled = true; };
  }, [savedView, saved]);

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
  const shown = savedView ? saved : deals;
  const staleSet = savedView && liveUrls ? new Set(saved.filter((d) => !liveUrls.has(d.url)).map((d) => d.url)) : null;
  const openDeal = openIndex != null ? shown[openIndex] : null;

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
        savedView={savedView}
        savedCount={saved.length}
        onCategory={(category) => {
          setSaleMode(false);
          setSavedView(false);
          setOpenIndex(null);
          // section change resets section-specific filters
          patchFilters({ category, stores: [], items: [], sizes: [], colors: [] });
        }}
        onToggleSale={() => { setSavedView(false); setOpenIndex(null); setSaleMode((s) => !s); }}
        onSaved={() => { setSaleMode(false); setOpenIndex(null); setSavedView((v) => !v); }}
      />
      <Ticker deals={deals} />
      <div className="page">
        <div className="titlerow">
          <h2>{savedView ? "Saved Deals" : saleMode ? "The Hot List" : `Today's Board — ${catLabel}`}</h2>
          <span className="stylecount">
            {savedView
              ? `${saved.length} SAVED`
              : `${total > deals.length ? `${deals.length} OF ${total}` : deals.length} DEAL${total === 1 ? "" : "S"} ON THE WIRE`}
          </span>
        </div>
        <SourceLog status={status} />
        <div className="pagegrid">
          {savedView ? null : (
            <Sidebar filters={filters} category={filters.category} stores={stores} facets={facets} saleMode={saleMode} onChange={patchFilters} />
          )}
          <main className={savedView ? "full" : ""}>
            <DealGrid
              deals={shown}
              loading={savedView ? false : loading}
              onOpen={setOpenIndex}
              savedSet={savedSet}
              onToggleSave={toggleSave}
              staleSet={staleSet}
              emptyMsg={savedView ? "NO SAVED DEALS YET — TAP ☆ ON ANY DEAL TO SAVE IT." : undefined}
            />
            {!savedView && total > deals.length && (
              <button className="showmore" onClick={() => setLimit((l) => l + 100)}>
                ▾ SHOW MORE ({total - deals.length} REMAINING)
              </button>
            )}
          </main>
        </div>
      </div>
      <DealModal
        deal={openDeal}
        onClose={() => setOpenIndex(null)}
        isSaved={openDeal ? savedSet.has(openDeal.url) : false}
        onToggleSave={toggleSave}
        stale={openDeal ? staleSet?.has(openDeal.url) : false}
      />
      {toast ? <div className="toast show">{toast}</div> : null}
    </>
  );
}
