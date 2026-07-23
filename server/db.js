// SQLite storage for deals. DB file lives at data/dealradar.db (auto-created).
// Uses Node's built-in node:sqlite — no native compilation, no extra install.
import { createHash } from "node:crypto";
import { DatabaseSync } from "node:sqlite";
import { mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");

const SCHEMA = `
CREATE TABLE IF NOT EXISTS deals (
    id          TEXT PRIMARY KEY,          -- sha1 of the deal URL
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    source      TEXT NOT NULL,             -- e.g. 'zara.com', 'nike.com'
    category    TEXT NOT NULL DEFAULT 'Other',
    store       TEXT,                      -- retailer: Amazon, Zara, ASOS, ...
    price       REAL,                      -- extracted from title, NULL if none found
    image_url   TEXT,                      -- product image from the feed, if any
    posted_at   TEXT,                      -- ISO timestamp from the feed, if any
    fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
    ai_score    INTEGER,                   -- 1-10, NULL until Claude scores it
    ai_take     TEXT,                      -- one-line verdict from Claude
    colors      TEXT,                      -- comma-joined lowercase color names (scraped sources)
    sizes       TEXT,                      -- comma-joined in-stock size labels (scraped sources)
    discount_pct INTEGER                   -- % off, from scraper data or title
);
CREATE INDEX IF NOT EXISTS idx_deals_category ON deals(category);
CREATE INDEX IF NOT EXISTS idx_deals_fetched ON deals(fetched_at);
`;

let _db = null;

export function dealId(url) {
  return createHash("sha1").update(url, "utf8").digest("hex");
}

function connect() {
  if (_db) return _db;
  const dbPath = process.env.DEALRADAR_DB || path.join(ROOT, "data", "dealradar.db");
  mkdirSync(path.dirname(dbPath), { recursive: true });
  _db = new DatabaseSync(dbPath);
  _db.exec(SCHEMA);
  // migrate pre-existing DBs (CREATE IF NOT EXISTS won't add new columns)
  for (const col of ["colors TEXT", "sizes TEXT", "discount_pct INTEGER"]) {
    try { _db.exec(`ALTER TABLE deals ADD COLUMN ${col}`); } catch { /* exists */ }
  }
  return _db;
}

/** Test hook: close and forget the current connection so DEALRADAR_DB is re-read. */
export function resetForTests() {
  if (_db) _db.close();
  _db = null;
}

/** Insert deals, skipping ones we've already seen. Returns count of new rows. */
export function upsertDeals(deals) {
  const db = connect();
  const stmt = db.prepare(
    `INSERT OR IGNORE INTO deals (id, title, url, source, category, store, price, image_url, posted_at, colors, sizes, discount_pct)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
  );
  let added = 0;
  db.exec("BEGIN");
  try {
    for (const d of deals) {
      const res = stmt.run(
        dealId(d.url), d.title, d.url, d.source, d.category ?? "Other",
        d.store ?? null, d.price ?? null, d.image_url ?? null, d.posted_at ?? null,
        d.colors ?? null, d.sizes ?? null, d.discount_pct ?? null
      );
      added += Number(res.changes);
    }
    db.exec("COMMIT");
  } catch (e) {
    db.exec("ROLLBACK");
    throw e;
  }
  return added;
}

export function setAiResult(id, score, take) {
  connect().prepare("UPDATE deals SET ai_score = ?, ai_take = ? WHERE id = ?").run(score, take, id);
}

export function unscoredDeals(limit = 30) {
  return connect()
    .prepare("SELECT * FROM deals WHERE ai_score IS NULL ORDER BY fetched_at DESC LIMIT ?")
    .all(limit);
}

function buildClauses({
  category, q, items, store, stores, maxPrice, minPrice, maxAgeHours, colors, sizes, minDiscount,
}) {
  const clauses = [];
  const params = [];
  if (colors?.length) {
    clauses.push("(" + colors.map(() => "colors LIKE ?").join(" OR ") + ")");
    for (const c of colors) params.push(`%${c.toLowerCase()}%`);
  }
  if (sizes?.length) {
    clauses.push("(" + sizes.map(() => "(',' || sizes || ',') LIKE ?").join(" OR ") + ")");
    for (const s of sizes) params.push(`%,${s},%`);
  }
  if (minDiscount != null) { clauses.push("discount_pct IS NOT NULL AND discount_pct >= ?"); params.push(minDiscount); }
  if (maxAgeHours != null) {
    clauses.push("datetime(COALESCE(posted_at, fetched_at)) >= datetime('now', ?)");
    params.push(`-${maxAgeHours} hours`);
  }
  if (category && category !== "All") { clauses.push("category = ?"); params.push(category); }
  if (q) { clauses.push("title LIKE ?"); params.push(`%${q}%`); }
  if (items?.length) {
    // word-boundary match via GLOB (space padding covers string start/end) —
    // plain LIKE '%tee%' matched "Steelbook" and "Stainless Steel". OR the
    // per-word groups so multiple item types widen the result set.
    const groups = items.map(() => "((' '||lower(title)||' ') GLOB ? OR (' '||lower(title)||' ') GLOB ?)");
    clauses.push("(" + groups.join(" OR ") + ")");
    for (const item of items) {
      const w = item.toLowerCase().replace(/[^a-z0-9-]/g, "");
      params.push(`*[^a-z0-9]${w}[^a-z0-9]*`, `*[^a-z0-9]${w}s[^a-z0-9]*`);
    }
  }
  // multiselect stores (OR'd); `store` kept for single-select callers
  const storeList = (stores?.length ? stores : store ? [store] : []).filter((s) => s && s !== "All");
  if (storeList.length) {
    clauses.push("(" + storeList.map(() => "store = ?").join(" OR ") + ")");
    params.push(...storeList);
  }
  if (maxPrice != null) { clauses.push("price IS NOT NULL AND price <= ?"); params.push(maxPrice); }
  if (minPrice != null) { clauses.push("price IS NOT NULL AND price >= ?"); params.push(minPrice); }
  return { where: clauses.length ? " WHERE " + clauses.join(" AND ") : "", params };
}

export function listDeals({ order = "new", limit = 100, ...filters } = {}) {
  const { where, params } = buildClauses(filters);
  let sql = "SELECT * FROM deals" + where;
  sql += order === "best"
    ? " ORDER BY ai_score IS NULL, ai_score DESC, datetime(COALESCE(posted_at, fetched_at)) DESC"
    : " ORDER BY datetime(COALESCE(posted_at, fetched_at)) DESC";
  sql += " LIMIT ?";
  return connect().prepare(sql).all(...params, limit);
}

/** Total rows matching the same filters listDeals takes (ignores limit). */
export function countDeals(filters = {}) {
  const { where, params } = buildClauses(filters);
  return connect().prepare("SELECT COUNT(*) AS n FROM deals" + where).get(...params).n;
}

/** Scraped catalogs change between refreshes: sync price/title/etc for rows
    we already have (INSERT OR IGNORE never updates them). */
export function refreshDealData(deals) {
  const db = connect();
  const stmt = db.prepare(
    `UPDATE deals SET title = ?, price = ?, image_url = ?, colors = ?, sizes = ?, discount_pct = ?
     WHERE id = ?`
  );
  db.exec("BEGIN");
  try {
    for (const d of deals) {
      stmt.run(d.title, d.price ?? null, d.image_url ?? null, d.colors ?? null,
        d.sizes ?? null, d.discount_pct ?? null, dealId(d.url));
    }
    db.exec("COMMIT");
  } catch (e) {
    db.exec("ROLLBACK");
    throw e;
  }
}

/** Remove rows for a scraped source that vanished from its latest fetch
    (deal expired / product left the sale). Returns count removed. */
export function pruneMissing(source, keepUrls) {
  const db = connect();
  const keep = new Set(keepUrls.map(dealId));
  const rows = db.prepare("SELECT id FROM deals WHERE source = ?").all(source);
  const stale = rows.filter((r) => !keep.has(r.id));
  const stmt = db.prepare("DELETE FROM deals WHERE id = ?");
  for (const r of stale) stmt.run(r.id);
  return stale.length;
}

/** Distinct colors and sizes with counts, for the filter sidebar. */
export function filterFacets() {
  const rows = connect()
    .prepare("SELECT colors, sizes FROM deals WHERE colors IS NOT NULL OR sizes IS NOT NULL")
    .all();
  const count = (map, csv) => {
    for (const v of (csv ?? "").split(",")) if (v) map.set(v, (map.get(v) ?? 0) + 1);
  };
  const colors = new Map();
  const sizes = new Map();
  for (const r of rows) { count(colors, r.colors); count(sizes, r.sizes); }
  const top = (map, n) =>
    [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map(([name, count]) => ({ name, count }));
  return { colors: top(colors, 14), sizes: top(sizes, 14) };
}

/** ISO timestamp of the most recent fetch, or null on an empty DB. */
export function lastFetchedAt() {
  const row = connect().prepare("SELECT MAX(fetched_at) AS t FROM deals").get();
  return row?.t ?? null;
}

export function categoryCounts() {
  return connect()
    .prepare("SELECT category, COUNT(*) AS n FROM deals GROUP BY category ORDER BY n DESC")
    .all();
}

export function storeCounts(category) {
  if (category && category !== "All") {
    return connect()
      .prepare("SELECT store, COUNT(*) AS n FROM deals WHERE store IS NOT NULL AND category = ? GROUP BY store ORDER BY n DESC")
      .all(category);
  }
  return connect()
    .prepare("SELECT store, COUNT(*) AS n FROM deals WHERE store IS NOT NULL GROUP BY store ORDER BY n DESC")
    .all();
}
