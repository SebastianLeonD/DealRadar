# Architecture

npm workspaces monorepo, all-JavaScript (Node >= 22.5).

## Folders
- `server/` — Node API. `index.js` (entry, HTTP server, refresh loop + in-memory refresh log), `sources.js` (RSS feeds incl. per-store Slickdeals searches; `ALL_SOURCES` = feeds + scrapers), `scrapers.js` (direct retailer JSON scrapers: Zara, H&M), `categorize.js` (category/store/price from title+url, optional AI scoring), `db.js` (SQLite storage), `notify.js` (Discord), `dealradar.test.js` (tests).
- `frontend/` — Vite + React SPA. `src/main.jsx` (entry) → `App.jsx` → components (`DealGrid`, `DealCard`, `DealModal`, `Sidebar` (left filter rail: item/store/discount/price/size/color/freshness), `TopBar`, `SubNav`, `Ticker`, `SourceLog`). `api.js` talks to the server.

## Data flow
sources.fetchAll() (RSS feeds + scrapers, per-source health) → categorize.js tags each deal → db.js stores (dedup by URL hash) → index.js serves API (`/api/deals`, `/api/status` incl. `refresh_log`) → frontend/src/api.js → React components. Scrapers embed price in the title ("X — $12 (was $40, 70% off)"); the normal extractPrice/detectStore pipeline picks it up.

## Retailer sources
- Zara + H&M: direct unofficial JSON endpoints (see scrapers.js header for endpoint notes). Men's sections only (user preference). Scrapers also emit `colors`/`sizes`/`discount_pct`; `/api/filters` aggregates them for the sidebar.
- Hollister/PacSun/ASOS/Amazon: Slickdeals per-store search RSS (their sites 403 server-side traffic).
- Per-source health: every refresh records ok/count/error/ms per source; UI "SOURCE WIRE" panel + `/api/status.refresh_log` (last 20, in-memory).

## Entry points
- `npm run dev` — API (`node --watch server/index.js`) + Vite dev server concurrently.
- `npm start` — production server (`node server/index.js`).
- `npm test` — server tests.
