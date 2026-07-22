# Architecture

npm workspaces monorepo, all-JavaScript (Node >= 22.5).

## Folders
- `server/` — Node API. `index.js` (entry, HTTP server, refresh loop + in-memory refresh log; skips startup refresh when data <5 min old), `sources.js` (RSS feeds incl. per-store Slickdeals searches; `ALL_SOURCES` = feeds + scrapers; 30-min cooldown for 429'd sources), `stores/` (one file per direct fetcher: `zara.js`, `hm.js`, `steam.js`, `gog.js`, `epic.js`, + `util.js` helpers, `index.js` exports `SCRAPERS`), `categorize.js` (category/store/price from title+url, optional AI scoring), `db.js` (SQLite storage), `notify.js` (Discord), `dealradar.test.js` (tests).
- `frontend/` — Vite + React SPA. `src/main.jsx` (entry) → `App.jsx` → components (`DealGrid`, `DealCard`, `DealModal`, `Sidebar` (left filter rail: item/store/discount/price/size/color/freshness), `TopBar`, `SubNav`, `Ticker`, `SourceLog`). `api.js` talks to the server.

## Data flow
sources.fetchAll() (RSS feeds + scrapers, per-source health) → categorize.js tags each deal → db.js stores (dedup by URL hash) → index.js serves API (`/api/deals`, `/api/status` incl. `refresh_log`) → frontend/src/api.js → React components. Scrapers embed price in the title ("X — $12 (was $40, 70% off)"); the normal extractPrice/detectStore pipeline picks it up.

## Retailer sources
- Zara + H&M: direct unofficial JSON endpoints (see each stores/ file header for endpoint notes). Men's sections only (user preference). Emit `colors`/`sizes`/`discount_pct`; `/api/filters` aggregates them for the sidebar.
- Steam (specials) + GOG (discounted catalog) + Epic (weekly free games): open JSON endpoints, pre-set `category: "Gaming"` and `store` — fetcher-set fields win over title-derived ones in runRefresh.
- Hollister/PacSun/ASOS/Amazon/Uniqlo: Slickdeals per-store search RSS (retail sites 403 server-side traffic; Uniqlo's API hides sale prices).
- Per-source health: every refresh records ok/count/error/ms per source; UI "SOURCE WIRE" panel + `/api/status.refresh_log` (last 20, in-memory).

## Entry points
- `npm run dev` — API (`node --watch server/index.js`) + Vite dev server concurrently.
- `npm start` — production server (`node server/index.js`).
- `npm test` — server tests.
