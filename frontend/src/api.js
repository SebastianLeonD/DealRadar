// Thin client for the DealRadar FastAPI backend (proxied under /api).

async function getJSON(path) {
  const resp = await fetch(path);
  if (!resp.ok) throw new Error(`${path} -> HTTP ${resp.status}`);
  return resp.json();
}

export function fetchDeals(filters) {
  const params = new URLSearchParams();
  if (filters.category !== "All") params.set("category", filters.category);
  if (filters.item !== "All") params.set("item", filters.item);
  if (filters.query) params.set("q", filters.query);
  if (filters.store !== "All") params.set("store", filters.store);
  if (filters.maxPrice) params.set("max_price", filters.maxPrice);
  if (filters.age) params.set("max_age_hours", filters.age);
  params.set("order", filters.order);
  return getJSON("/api/deals?" + params);
}

export const fetchCategories = () => getJSON("/api/categories");
export const fetchStores = () => getJSON("/api/stores");
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
