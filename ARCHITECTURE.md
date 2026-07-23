# Architecture

npm workspaces monorepo, all-JavaScript (Node >= 22.5).

## Folders
- `server/` — Node API. `index.js` (entry, HTTP server, refresh loop + in-memory refresh log; skips startup refresh when data <5 min old), `sources.js` (`ALL_SOURCES` = the direct scrapers; 30-min cooldown for 429'd sources — no RSS/feeds), `stores/` (one file per direct fetcher: `zara.js`, `hm.js`, `nike.js`, `ikea.js`, `bestbuy.js` (only active with BESTBUY_API_KEY), + `util.js` helpers, `index.js` exports `SCRAPERS`), `categorize.js` (category/store/price from title+url, optional AI scoring), `db.js` (SQLite storage), `notify.js` (Discord), `dealradar.test.js` (tests).
- `frontend/` — Vite + React SPA. `src/main.jsx` (entry) → `App.jsx` → components (`DealGrid`, `DealCard`, `DealModal`, `Sidebar` (left filter rail: item/store/discount/price/size/color/freshness), `TopBar`, `SubNav`, `Ticker`, `SourceLog`). `api.js` talks to the server. `saved.js` (`useSaved` hook) is a browser-local watchlist stored in `localStorage` (`dealradar:saved`, full deal snapshots).

## Data flow
sources.fetchAll() (direct scrapers, per-source health) → categorize.js tags each deal → db.js stores (dedup by URL hash) → index.js serves API (`/api/deals`, `/api/status` incl. `refresh_log`) → frontend/src/api.js → React components. Scrapers embed price in the title ("X — $12 (was $40, 70% off)"); the normal extractPrice/detectStore pipeline picks it up.

## Retailer sources
Sources are direct fetchers only — no RSS/feeds.
- Zara + H&M + Nike: direct unofficial JSON endpoints (see each stores/ file header for endpoint notes; Nike needs the public `nike-api-caller-id` header). Men's sections only (user preference). Zara/H&M emit `colors`/`sizes`/`discount_pct`; `/api/filters` aggregates them for the sidebar.
- IKEA: "Last chance" pages are server-rendered; fetcher parses embedded schema.org JSON-LD (ItemList lives under CollectionPage.mainEntity inside `@graph`).
- Gap + Old Navy (`stores/gap.js`): shared `api.gap.com` commerce gateway (no auth), men's-sale cid per brand. Prices/percentages are strings (coerced); `/webcontent` image paths served from each brand's site host.
- Shopify stores (`stores/shopify.js`, one generic `mapShopify`/`makeShopifyFetcher`): Gymshark, Parachute — each `/collections/{handle}/products.json`; a markdown = variant with `compare_at_price > price > 0`. Gymshark is men's-only via a `tags` filter (`Mens` and not `Womens`); Parachute is Home, others Clothing.
- Target (`stores/target.js`): RedSky public API (`redsky.target.com/.../plp_search_v2`), category "Home", home-clearance keyword. Akamai TLS-fingerprints Node's fetch (403) and captchas repeated/flagged traffic, so it shells out to the system `curl`, makes a single request per refresh, and throws on captcha (health flags it). **Off by default** — Akamai captchas it in practice; set `ENABLE_TARGET=1` in `.env` to try from a clean, low-volume IP. `key`/`pricing_store_id` are Target's public web values and may rotate.
- Best Buy: official API, activates when BESTBUY_API_KEY is set in .env (free key from developer.bestbuy.com).

## Per-category filters
Sidebar personalizes by section: Clothing (or All) shows item/size/color; other sections just store/discount/price/freshness. `/api/stores?category=X` scopes the store dropdown; switching sections resets store/item/size/color. Item/size/color/store are multiselect (chips toggle in/out; sent to `/api/deals` as comma-joined `items`/`sizes`/`colors`/`stores`, OR'd within each group). The sidebar itself scrolls (`max-height: calc(100vh - 120px); overflow-y: auto`) so the wheel scrolls the rail, not the page, when hovering it.
- Per-source health: every refresh records ok/count/error/ms per source; UI "SOURCE WIRE" panel + `/api/status.refresh_log` (last 20, in-memory).

## Saved items (watchlist)
Client-side only — no accounts. `saved.js` keeps a snapshot of each saved deal in `localStorage`, so saved deals still render after they leave the live board. The "★ Saved" tab (SubNav) shows them; on open it POSTs the saved URLs to `/api/deals/live` (→ `db.dealsByUrls`), which returns the subset still on sale. Anything missing is marked stale (greyed + red diagonal + "NO LONGER ON SALE" banner) but stays clickable — the modal's OPEN DEAL link still works. The ☆/★ toggle on any card or in the modal saves/unsaves (unsaving in the Saved view removes it).

## Entry points
- `npm run dev` — API (`node --watch server/index.js`) + Vite dev server concurrently.
- `npm start` — production server (`node server/index.js`).
- `npm test` — server tests.
