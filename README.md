# DealRadar 🛰️

An AI-powered discount aggregator — the same thing those paid Discord/Telegram
"deals" groups do, but self-hosted and automated. **100% JavaScript**: a Node.js
server (API + feed aggregation + SQLite + optional Claude scoring) and a React
frontend, started with a single command.

## What it does

1. **Aggregates — live** — pulls RSS/Atom feeds from Slickdeals and Reddit deal
   subs (r/deals, r/buildapcsales, r/frugalmalefashion, r/FrugalFemaleFashion,
   r/GameDeals) automatically every 15 minutes. No API keys needed for any
   source. The board defaults to newest-first with a freshness window so you
   never look at dead deals.
2. **Parses every deal** — extracts the sale **price** from the title and
   detects the **store** (Amazon, Zara, ASOS, Hollister, PacSun, Ralph Lauren,
   H&M, American Eagle, Urban Outfitters, J.Crew, Vans, New Balance, Nike,
   Uniqlo, Best Buy, ...) from the deal's link domain, so you can shop-filter
   like *"jeans under $30 from ASOS"*.
3. **AI scoring (optional)** — set `ANTHROPIC_API_KEY` and Claude rates every
   new deal 1–10 with a one-line verdict ("all-time low, grab it" vs "fake
   discount, skip").
4. **"Market Bulletin" React storefront** — editorial white/ink/red design:
   serif masthead, live deal ticker, image product grid with score stamps and
   staggered reveal, click-to-open detail sheet with the outbound link.
5. **Posts to Discord (optional)** — set `DISCORD_WEBHOOK_URL` and the
   "→ Discord" button pushes the top 5 deals to your server, formatted like
   the paid groups do it.

## Quick start (one command to run)

Requires **Node.js 22.5+** (nodejs.org — current LTS works). No Python.

```bash
npm install        # installs server + frontend (workspaces)
npm run build      # builds the React app once
npm start          # -> http://localhost:8000  (UI + API, one server)
```

That's it. The server fetches deals on boot and every 15 minutes after.

For development with hot reload (still one command — runs API + Vite together):

```bash
npm run dev        # UI on http://localhost:5173, API on :8000
```

## Configuration (all optional)

Copy `.env.example` to `.env` in the repo root:

| Env var                     | What it enables                                        |
| --------------------------- | ------------------------------------------------------ |
| `ANTHROPIC_API_KEY`         | Claude deal scoring (1–10 + one-line verdict per deal)  |
| `DEALRADAR_AI_MODEL`        | Override the Claude model (default `claude-opus-4-8`)   |
| `DEALRADAR_REFRESH_MINUTES` | Background feed-refresh interval (default 15)           |
| `DISCORD_WEBHOOK_URL`       | "→ Discord" button posts top deals to your channel      |
| `PORT`                      | Server port (default 8000)                              |

## API

| Endpoint          | Method | Description                                      |
| ----------------- | ------ | ------------------------------------------------ |
| `/api/deals`      | GET    | List deals. Params: `category`, `item`, `store`, `max_price`, `min_price`, `max_age_hours`, `order` (`new`/`best`), `q`, `limit` |
| `/api/categories` | GET    | Category names with deal counts                  |
| `/api/stores`     | GET    | Detected stores with deal counts                 |
| `/api/status`     | GET    | Feature flags + last background-refresh time     |
| `/api/refresh`    | POST   | Manual refresh (the server also does this on a timer) |
| `/api/notify`     | POST   | Push current top deals to the Discord webhook    |

Example — jeans under $30 from ASOS: `GET /api/deals?item=jeans&store=ASOS&max_price=30`

Note on stores: Zara/ASOS/Hollister don't publish public deal feeds, so
DealRadar tags deals *mentioning* those stores from the aggregator feeds (the
paid groups work the same way — they watch aggregators).

## Project layout

```
server/                  Node.js backend (Express)
  index.js               API routes, static serving, background refresher
  sources.js             Feed fetchers (rss-parser; Slickdeals + Reddit)
  categorize.js          Keyword categorizer, price/store extraction,
                         optional Claude scoring (@anthropic-ai/sdk)
  db.js                  SQLite via built-in node:sqlite (data/dealradar.db)
  notify.js              Discord webhook poster
  dealradar.test.js      Vitest suite (npm test)
frontend/                React app (Vite)
  src/App.jsx            State, data loading, 60s live polling
  src/api.js             API client helpers
  src/styles.css         The "Market Bulletin" design system
  src/components/        TopBar, SubNav, Ticker, FilterBar,
                         DealGrid, DealCard, DealModal
```

## Roadmap ideas

- Price-history tracking to catch fake "discounts"
- User accounts + paid tier (Stripe) if you want to run it as a business
- Telegram bot output alongside Discord
- More sources: Woot, Amazon Warehouse RSS, store-specific feeds
