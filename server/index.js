// DealRadar — single Node server: JSON API + built React app, one port.
//
//   npm run build   (once, builds frontend/dist)
//   npm start       -> http://localhost:8000
//
// Sources are re-fetched automatically every DEALRADAR_REFRESH_MINUTES (default 15).
import "dotenv/config";
import express from "express";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as categorize from "./categorize.js";
import * as db from "./db.js";
import * as notify from "./notify.js";
import * as sources from "./sources.js";
import { SCRAPERS } from "./stores/index.js";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIST = path.join(ROOT, "frontend", "dist");
const PORT = Number(process.env.PORT || 8000);
const REFRESH_MINUTES = Number(process.env.DEALRADAR_REFRESH_MINUTES || 15);

const lastRefresh = { at: null, result: null };
const refreshLog = []; // newest first, last 20 refreshes, in-memory

/** Fetch all sources, store new deals, categorize, and (if enabled) AI-score them. */
export async function runRefresh() {
  const { deals, errors, health } = await sources.fetchAll();
  for (const d of deals) {
    // direct store fetchers pre-set these; fall back to title-derived values
    d.category = d.category ?? categorize.categorize(d.title);
    d.store = d.store ?? categorize.detectStore(d.title, d.url);
    d.price = d.price ?? categorize.extractPrice(d.title);
    d.discount_pct = d.discount_pct ?? categorize.extractDiscount(d.title);
  }
  const added = db.upsertDeals(deals);

  // scraped catalogs are live state, not posts: sync changed prices and drop
  // rows whose product left the store's sale (stale-deal fix)
  let pruned = 0;
  const scraperNames = new Set(SCRAPERS.map((s) => s.name));
  for (const h of health) {
    if (!h.ok || !scraperNames.has(h.source)) continue;
    const current = deals.filter((d) => d.source === h.source);
    db.refreshDealData(current);
    pruned += db.pruneMissing(h.source, current.map((d) => d.url));
  }

  let scored = 0;
  let aiError = null;
  if (categorize.aiAvailable()) {
    try {
      const batch = db.unscoredDeals(30);
      for (const r of await categorize.scoreDealsWithAI(batch)) {
        db.setAiResult(r.id, r.score, r.take);
        scored += 1;
      }
    } catch (e) {
      aiError = String(e?.message ?? e); // AI scoring is best-effort
    }
  }

  const result = {
    at: new Date().toISOString(),
    fetched: deals.length,
    new: added,
    pruned,
    ai_scored: scored,
    ai_error: aiError,
    source_errors: errors,
    sources: health,
  };
  lastRefresh.at = result.at;
  lastRefresh.result = result;
  refreshLog.unshift(result);
  if (refreshLog.length > 20) refreshLog.pop();
  return result;
}

const app = express();

app.get("/api/deals", (req, res) => {
  const num = (v) => (v === undefined || v === "" ? null : Number(v));
  const list = (v) => (v ? String(v).split(",").filter(Boolean) : []);
  const order = req.query.order === "best" ? "best" : "new";
  const filters = {
    category: req.query.category,
    q: req.query.q,
    items: list(req.query.items),
    stores: list(req.query.stores),
    maxPrice: num(req.query.max_price),
    minPrice: num(req.query.min_price),
    maxAgeHours: num(req.query.max_age_hours),
    colors: list(req.query.colors),
    sizes: list(req.query.sizes),
    minDiscount: num(req.query.min_discount),
  };
  res.json({
    deals: db.listDeals({ ...filters, order, limit: Math.min(num(req.query.limit) ?? 100, 1000) }),
    total: db.countDeals(filters),
  });
});

app.get("/api/categories", (_req, res) => res.json({ categories: db.categoryCounts() }));
app.get("/api/stores", (req, res) => res.json({ stores: db.storeCounts(req.query.category) }));
app.get("/api/filters", (_req, res) => res.json(db.filterFacets()));

app.get("/api/status", (_req, res) => {
  res.json({
    ai_enabled: categorize.aiAvailable(),
    discord_enabled: notify.webhookConfigured(),
    sources: sources.ALL_SOURCES.map((s) => s.name),
    auto_refresh_minutes: REFRESH_MINUTES,
    last_refresh_at: lastRefresh.at,
    last_refresh: lastRefresh.result,
    refresh_log: refreshLog,
  });
});

app.post("/api/refresh", async (_req, res) => {
  try {
    res.json(await runRefresh());
  } catch (e) {
    res.status(500).json({ detail: String(e?.message ?? e) });
  }
});

app.post("/api/notify", async (_req, res) => {
  if (!notify.webhookConfigured()) {
    return res.status(400).json({ detail: "DISCORD_WEBHOOK_URL is not set" });
  }
  try {
    const deals = db.listDeals({ order: "best", limit: 25 });
    res.json({ posted: await notify.postTopDeals(deals, 5) });
  } catch (e) {
    res.status(500).json({ detail: String(e?.message ?? e) });
  }
});

// Serve the built React app (production). In dev, Vite serves it on :5173.
if (existsSync(DIST)) {
  app.use(express.static(DIST));
  app.get(/^\/(?!api\/).*/, (_req, res) => res.sendFile(path.join(DIST, "index.html")));
} else {
  app.get("/", (_req, res) =>
    res.json({ service: "DealRadar API", ui: "run `npm run build` for production or `npm run dev` for development" })
  );
}

app.listen(PORT, () => {
  console.log(`DealRadar running on http://localhost:${PORT}`);
  // skip the startup refresh when data is fresh — dev-server restarts were
  // re-fetching every source each time and getting us rate-limited
  const last = db.lastFetchedAt();
  const freshMs = last ? Date.now() - new Date(last.replace(" ", "T") + "Z") : Infinity;
  if (freshMs < 5 * 60 * 1000) {
    console.log(`skipping initial refresh — data is ${Math.round(freshMs / 1000)}s old`);
  } else {
    runRefresh()
      .then((r) => console.log(`initial refresh: ${r.fetched} fetched, ${r.new} new, ${r.source_errors.length} source errors`))
      .catch((e) => console.error("initial refresh failed:", e.message));
  }
  setInterval(() => runRefresh().catch((e) => console.error("refresh failed:", e.message)),
    REFRESH_MINUTES * 60 * 1000);
});
