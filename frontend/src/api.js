// Thin client for the DealRadar FastAPI backend (proxied under /api).

async function getJSON(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`${path} -> HTTP ${resp.status}`);
  return resp.json();
}

export function fetchDeals(filters) {
  const params = new URLSearchParams();
  if (filters.category !== "All") params.set("category", filters.category);
  if (filters.items?.length) params.set("items", filters.items.join(","));
  if (filters.query) params.set("q", filters.query);
  if (filters.stores?.length) params.set("stores", filters.stores.join(","));
  if (filters.maxPrice) params.set("max_price", filters.maxPrice);
  if (filters.minPrice) params.set("min_price", filters.minPrice);
  if (filters.colors?.length) params.set("colors", filters.colors.join(","));
  if (filters.sizes?.length) params.set("sizes", filters.sizes.join(","));
  if (filters.minDiscount) params.set("min_discount", filters.minDiscount);
  if (filters.age) params.set("max_age_hours", filters.age);
  params.set("order", filters.order);
  if (filters.limit) params.set("limit", filters.limit);
  return getJSON("/api/deals?" + params);
}

// Which of these saved URLs are still on sale (returns live rows w/ fresh price).
export async function fetchLive(urls) {
  if (!urls.length) return [];
  const resp = await fetch("/api/deals/live", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ urls }),
  });
  if (!resp.ok) throw new Error(`live -> HTTP ${resp.status}`);
  return (await resp.json()).live;
}

export const fetchCategories = () => getJSON("/api/categories");
export const fetchStores = (category) =>
  getJSON("/api/stores" + (category && category !== "All" ? `?category=${encodeURIComponent(category)}` : ""));
export const fetchFilters = () => getJSON("/api/filters");
export const fetchStatus = () => getJSON("/api/status");

export async function postRefresh() {
  const resp = await fetch("/api/refresh", { method: "POST" });
  if (!resp.ok) throw new Error(`refresh -> HTTP ${resp.status}`);
  return resp.json();
}

export async function postNotify() {
  const resp = await fetch("/api/notify", { method: "POST" });
  const body = await resp.json();
  return { ok: resp.ok, body };
}

export function timeAgo(iso) {
  if (!iso) return "";
  const t = new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z");
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 60) return `${mins}m ago`;
  if (mins < 1440) return `${Math.round(mins / 60)}h ago`;
  return `${Math.round(mins / 1440)}d ago`;
}

export const scoreClass = (s) => (s >= 8 ? "hi" : s >= 5 ? "mid" : "lo");
