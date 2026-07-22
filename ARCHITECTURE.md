# Architecture

npm workspaces monorepo, all-JavaScript (Node >= 22.5).

## Folders
- `server/` — Node API. `index.js` (entry, HTTP server, refresh loop + in-memory refresh log; skips startup refresh when data <5 min old), `sources.js` (Slickdeals RSS feeds — frontpage + per-store searches; `ALL_SOURCES` = feeds + scrapers; 30-min cooldown for 429'd sources; NO Reddit, user removed it), `stores/` (one file per direct fetcher: `zara.js`, `hm.js`, `nike.js`, `ikea.js`, `steam.js`, `gog.js`, `epic.js`, `bestbuy.js` (only active with BESTBUY_API_KEY), + `util.js` helpers, `index.js` exports `SCRAPERS`), `categorize.js` (category/store/price from title+url, optional AI scoring), `db.js` (SQLite storage), `notify.js` (Discord), `dealradar.test.js` (tests).
- `frontend/` — Vite + React SPA. `src/main.jsx` (entry) → `App.jsx` → components (`DealGrid`, `DealCard`, `DealModal`, `Sidebar` (left filter rail: item/store/discount/price/size/color/freshness), `TopBar`, `SubNav`, `Ticker`, `SourceLog`). `api.js` talks to the server.

## Data flow
sources.fetchAll() (RSS feeds + scrapers, per-source health) → categorize.js tags each deal → db.js stores (dedup by URL hash) → index.js serves API (`/api/deals`, `/api/status` incl. `refresh_log`) → frontend/src/api.js → React components. Scrapers embed price in the title ("X — $12 (was $40, 70% off)"); the normal extractPrice/detectStore pipeline picks it up.

## Retailer sources
- Zara + H&M + Nike: direct unofficial JSON endpoints (see each stores/ file header for endpoint notes; Nike needs the public `nike-api-caller-id` header). Men's sections only (user preference). Zara/H&M emit `colors`/`sizes`/`discount_pct`; `/api/filters` aggregates them for the sidebar.
- IKEA: "Last chance" pages are server-rendered; fetcher parses embedded schema.org JSON-LD (ItemList lives under CollectionPage.mainEntity inside `@graph`).
- Steam (specials) + GOG (discounted catalog) + Epic (weekly free games): open JSON endpoints, pre-set `category: "Gaming"` and `store` — fetcher-set fields win over title-derived ones in runRefresh.
- Best Buy: official API, activates when BESTBUY_API_KEY is set in .env (free key from developer.bestbuy.com).
- Hollister/PacSun/ASOS/Amazon/Uniqlo: Slickdeals per-store search RSS (retail sites 403 server-side traffic; Uniqlo's API hides sale prices).

## Per-category filters
Sidebar personalizes by section: Clothing (or All) shows item/size/color; other sections just store/discount/price/freshness. `/api/stores?category=X` scopes the store dropdown; switching sections resets store/item/size/color.
- Per-source health: every refresh records ok/count/error/ms per source; UI "SOURCE WIRE" panel + `/api/status.refresh_log` (last 20, in-memory).

## Entry points
- `npm run dev` — API (`node --watch server/index.js`) + Vite dev server concurrently.
- `npm start` — production server (`node server/index.js`).
- `npm test` — server tests.
