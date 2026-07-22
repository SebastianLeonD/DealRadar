# DealRadar 🛰️

An AI-powered discount aggregator — the same thing those paid Discord/Telegram
"deals" groups do, but self-hosted and automated.

DealRadar continuously pulls live deals from free public sources (Slickdeals
frontpage, Reddit deal communities), auto-categorizes them (Tech, Clothing,
Gaming, Home, ...), optionally has Claude score how good each deal actually is,
and shows everything in a clean web dashboard. It can also push top deals to a
Discord channel via webhook — exactly the workflow the paid groups charge for.

## What it does

1. **Aggregates** — fetches RSS/Atom feeds from Slickdeals and Reddit deal subs
   (r/deals, r/buildapcsales, r/frugalmalefashion, r/GameDeals). No API keys
   needed for any source.
2. **Categorizes** — a keyword engine buckets every deal into a category
   instantly. If you set `ANTHROPIC_API_KEY`, Claude additionally scores each
   deal 1–10 and writes a one-line take ("solid all-time-low on a good TV" vs
   "fake discount, ignore").
3. **Serves a dashboard** — browse, filter by category, and search all deals at
   `http://localhost:8000`.
4. **Posts to Discord (optional)** — set `DISCORD_WEBHOOK_URL` and hit the
   "Post top deals" button (or `POST /api/notify`) to push the best current
   deals into your own server, formatted like the paid groups do it.

## Quick start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # optional: add keys for AI scoring / Discord

uvicorn app.main:app --reload
```

Open http://localhost:8000 and click **Refresh deals** to pull the latest.

## Configuration (all optional)

| Env var               | What it enables                                          |
| --------------------- | -------------------------------------------------------- |
| `ANTHROPIC_API_KEY`   | Claude deal scoring (1–10 + one-line verdict per deal)    |
| `DEALRADAR_AI_MODEL`  | Override the Claude model (default `claude-opus-4-8`)     |
| `DISCORD_WEBHOOK_URL` | "Post top deals" button → posts to your Discord channel   |

Without any keys, everything still works — you just get keyword categories
instead of AI scores.

## API

| Endpoint              | Method | Description                                      |
| --------------------- | ------ | ------------------------------------------------ |
| `/api/deals`          | GET    | List deals. Params: `category`, `q`, `limit`     |
| `/api/categories`     | GET    | Category names with deal counts                  |
| `/api/refresh`        | POST   | Fetch all sources, store + categorize new deals  |
| `/api/notify`         | POST   | Push current top deals to the Discord webhook    |

## Project layout

```
app/
  main.py        FastAPI app + API routes, serves the dashboard
  sources.py     Feed fetchers (Slickdeals + Reddit, RSS/Atom)
  categorize.py  Keyword categorizer + optional Claude scoring
  db.py          SQLite storage (data/dealradar.db, auto-created)
  notify.py      Discord webhook poster
static/
  index.html     The dashboard (self-contained, no build step)
```

## Roadmap ideas

- Scheduled auto-refresh (cron / background task) so the feed is always fresh
- Price-history tracking to catch fake "discounts"
- User accounts + paid tier (Stripe) if you want to run it as a business
- Telegram bot output alongside Discord
- More sources: Woot, Amazon Warehouse RSS, store-specific feeds
