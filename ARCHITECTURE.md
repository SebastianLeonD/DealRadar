# Architecture

npm workspaces monorepo, all-JavaScript (Node >= 22.5).

## Folders
- `server/` — Node API. `index.js` (entry, HTTP server), `sources.js` (deal scraping/fetching), `categorize.js` (deal categorization), `db.js` (storage), `notify.js` (notifications), `dealradar.test.js` (tests).
- `frontend/` — Vite + React SPA. `src/main.jsx` (entry) → `App.jsx` → components (`DealGrid`, `DealCard`, `DealModal`, `FilterBar`, `TopBar`, `SubNav`, `Ticker`). `api.js` talks to the server.

## Data flow
sources.js fetches deals → categorize.js tags them → db.js stores → index.js serves API → frontend/src/api.js → React components.

## Entry points
- `npm run dev` — API (`node --watch server/index.js`) + Vite dev server concurrently.
- `npm start` — production server (`node server/index.js`).
- `npm test` — server tests.
