// DealRadar — single Node server: JSON API + built React app, one port.
//
//   npm run build   (once, builds frontend/dist)
//   npm start       -> http://localhost:8000
//
// Feeds are re-fetched automatically every DEALRADAR_REFRESH_MINUTES (default 15).
import "dotenv/config";
import express from "express";
import { existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import * as categorize from "./categorize.js";
import * as db from "./db.js";
import * as notify from "./notify.js";
import * as sources from "./sources.js";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIST = path.join(ROOT, "frontend", "dist");
const PORT = Number(process.env.PORT || 8000);
const REFRESH_MINUTES = Number(process.env.DEALRADAR_REFRESH_MINUTES || 15);

const lastRefresh = { at: null, result: null };
const refreshLog = []; // newest first, last 20 refreshes, in-memory

/** Fetch all feeds, store new deals, categorize, and (if enabled) AI-score them. */
export async function runRefresh() {
  const { deals, errors, health } = await sources.fetchAll();
  for (const d of deals) {
    d.category = categorize.categorize(d.title);
    d.store = categorize.detectStore(d.title, d.url);
    d.price = categorize.extractPrice(d.title);
  }
  const added = db.upsertDeals(deals);

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
  const order = req.query.order === "best" ? "best" : "new";
  res.json({
    deals: db.listDeals({
      category: req.query.category,
      q: req.query.q,
      item: req.query.item,
      store: req.query.store,
      maxPrice: num(req.query.max_price),
      minPrice: num(req.query.min_price),
      maxAgeHours: num(req.query.max_age_hours),
      order,
      limit: Math.min(num(req.query.limit) ?? 100, 500),
    }),
  });
});

app.get("/api/categories", (_req, res) => res.json({ categories: db.categoryCounts() }));
app.get("/api/stores", (_req, res) => res.json({ stores: db.storeCounts() }));

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
  runRefresh()
    .then((r) => console.log(`initial refresh: ${r.fetched} fetched, ${r.new} new, ${r.source_errors.length} source errors`))
    .catch((e) => console.error("initial refresh failed:", e.message));
  setInterval(() => runRefresh().catch((e) => console.error("refresh failed:", e.message)),
    REFRESH_MINUTES * 60 * 1000);
});
