# DealRadar 🛰️

An AI-powered discount aggregator — the same thing those paid Discord/Telegram
"deals" groups do, but self-hosted and automated.

DealRadar continuously pulls live deals from free public sources (Slickdeals
frontpage, Reddit deal communities), auto-categorizes them (Tech, Clothing,
Gaming, Home, ...), optionally has Claude score how good each deal actually is,
and shows everything in a clean web dashboard. It can also push top deals to a
Discord channel via webhook — exactly the workflow the paid groups charge for.

## What it does

1. **Aggregates — live** — the server pulls RSS/Atom feeds from Slickdeals and
   Reddit deal subs (r/deals, r/buildapcsales, r/frugalmalefashion,
   r/FrugalFemaleFashion, r/GameDeals) automatically every 15 minutes
   (`DEALRADAR_REFRESH_MINUTES` to change), and the dashboard re-polls every
   60 seconds — no button pressing. Deals default to newest-first with a
   freshness window (Last 24h / 48h / 7d) so you never look at dead deals.
2. **Parses every deal** — extracts the sale **price** from the title and
   detects the **store** (Amazon, Zara, ASOS, Hollister, PacSun, Ralph Lauren,
   H&M, American Eagle, Urban Outfitters, J.Crew, Vans, New Balance, Nike,
   Uniqlo, Best Buy, ...) from the deal's link/title, so you can shop-filter
   like *"jeans under $30 from ASOS"*.
3. **Categorizes** — a keyword engine buckets every deal into a category
   instantly. If you set `ANTHROPIC_API_KEY`, Claude additionally scores each
   deal 1–10 and writes a one-line take ("solid all-time-low on a good TV" vs
   "fake discount, ignore").
4. **React storefront** — `frontend/` is a Vite + React app (ASOS-style
   design): black header with search, dark category nav with a red Hot tag,
   portrait product grid with image cards, price + AI-score badges, and a
   click-to-open detail modal with the full-size image, AI verdict, and an
   "Open deal" link. Product images come straight from the feeds (Slickdeals
   thumbnails, Reddit preview images). Filters — category tabs, item chips
   (Jeans, Shorts, Hoodie, Sneaker, ...), store dropdown, max-price box,
   freshness window, and search — are all combinable. The Python service is
   API-only.
5. **Posts to Discord (optional)** — set `DISCORD_WEBHOOK_URL` and hit the
   "Post top deals" button (or `POST /api/notify`) to push the best current
   deals into your own server, formatted like the paid groups do it.

## Quick start

Two pieces: a **Python API** (aggregation, storage, AI scoring) and a
**React frontend** (all the UI — no Python-served pages).

```bash
# 1) API (terminal one)
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # optional: keys for AI scoring / Discord
uvicorn app.main:app --reload      # http://localhost:8000 (JSON only)

# 2) React frontend (terminal two)
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

Open http://localhost:5173 — the Vite dev server proxies `/api/*` to the
backend, so there's nothing else to configure. For production, `npm run
build` and serve `frontend/dist/` from any static host.

## Configuration (all optional)

| Env var               | What it enables                                          |
| --------------------- | -------------------------------------------------------- |
| `ANTHROPIC_API_KEY`   | Claude deal scoring (1–10 + one-line verdict per deal)    |
| `DEALRADAR_AI_MODEL`  | Override the Claude model (default `claude-opus-4-8`)     |
| `DEALRADAR_REFRESH_MINUTES` | Background feed-refresh interval (default 15)       |
| `DISCORD_WEBHOOK_URL` | "Post top deals" button → posts to your Discord channel   |

Without any keys, everything still works — you just get keyword categories
instead of AI scores.

## API

| Endpoint              | Method | Description                                      |
| --------------------- | ------ | ------------------------------------------------ |
| `/api/deals`          | GET    | List deals. Params: `category`, `item`, `store`, `max_price`, `min_price`, `max_age_hours`, `order` (`new`/`best`), `q`, `limit` |
| `/api/categories`     | GET    | Category names with deal counts                  |
| `/api/stores`         | GET    | Detected stores with deal counts                 |
| `/api/status`         | GET    | Feature flags + last background-refresh time     |
| `/api/refresh`        | POST   | Manual refresh (the server also does this on a timer) |
| `/api/notify`         | POST   | Push current top deals to the Discord webhook    |

Example — jeans under $30 from ASOS:

```
GET /api/deals?item=jeans&store=ASOS&max_price=30
```

Note on stores: Zara/ASOS/Hollister don't publish public deal feeds, so
DealRadar tags deals *mentioning* those stores from the aggregator feeds (the
paid groups work the same way — they watch aggregators). The store is detected
from the deal's link domain first, falling back to the title.

## Project layout

```
app/                     Python API service (no UI)
  main.py                FastAPI routes + background feed refresher
  sources.py             Feed fetchers (Slickdeals + Reddit, RSS/Atom)
  categorize.py          Keyword categorizer + optional Claude scoring
  db.py                  SQLite storage (data/dealradar.db, auto-created)
  notify.py              Discord webhook poster
frontend/                React app (Vite)
  src/App.jsx            State, data loading, 60s live polling
  src/api.js             API client helpers
  src/styles.css         The ASOS-style design system
  src/components/        TopBar, SubNav, Banners, FilterBar,
                         DealGrid, DealCard, DealModal
```

## Roadmap ideas

- Price-history tracking to catch fake "discounts"
- User accounts + paid tier (Stripe) if you want to run it as a business
- Telegram bot output alongside Discord
- More sources: Woot, Amazon Warehouse RSS, store-specific feeds
