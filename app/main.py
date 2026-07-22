"""DealRadar — FastAPI backend + dashboard.

Run with:  uvicorn app.main:app --reload

The server refreshes all feeds in the background every
DEALRADAR_REFRESH_MINUTES (default 15) so the board stays live without
anyone pressing the button.
"""

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import categorize, db, notify, sources

REFRESH_MINUTES = float(os.environ.get("DEALRADAR_REFRESH_MINUTES", "15"))

_last_refresh: dict = {"at": None, "result": None}


def run_refresh() -> dict:
    """Fetch all feeds, store new deals, categorize, and (if enabled) AI-score them."""
    fetched, errors = sources.fetch_all()
    for deal in fetched:
        deal["category"] = categorize.categorize(deal["title"])
        deal["store"] = categorize.detect_store(deal["title"], deal["url"])
        deal["price"] = categorize.extract_price(deal["title"])
    new_count = db.upsert_deals(fetched)

    scored = 0
    ai_error = None
    if categorize.ai_available():
        try:
            batch = db.unscored_deals(limit=30)
            for result in categorize.score_deals_with_ai(batch):
                db.set_ai_result(result["id"], result["score"], result["take"])
                scored += 1
        except Exception as exc:  # noqa: BLE001 — AI scoring is best-effort
            ai_error = str(exc)

    result = {
        "fetched": len(fetched),
        "new": new_count,
        "ai_scored": scored,
        "ai_error": ai_error,
        "source_errors": errors,
    }
    _last_refresh["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _last_refresh["result"] = result
    return result


async def _auto_refresh_loop() -> None:
    while True:
        try:
            await asyncio.to_thread(run_refresh)
        except Exception:  # noqa: BLE001 — never let one bad cycle kill the loop
            pass
        await asyncio.sleep(REFRESH_MINUTES * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_auto_refresh_loop())
    yield
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


app = FastAPI(title="DealRadar API", version="0.3.0", lifespan=lifespan)

# The UI is a separate React app (frontend/) — this service is API-only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def index():
    return {"service": "DealRadar API", "ui": "run the React app in frontend/ (npm run dev)"}


@app.get("/api/deals")
def get_deals(
    category: str | None = None,
    q: str | None = None,
    item: str | None = None,
    store: str | None = None,
    max_price: float | None = Query(default=None, ge=0),
    min_price: float | None = Query(default=None, ge=0),
    max_age_hours: float | None = Query(default=None, gt=0),
    order: str = Query(default="new", pattern="^(new|best)$"),
    limit: int = Query(default=100, le=500),
):
    return {"deals": db.list_deals(category=category, q=q, item=item, store=store,
                                   max_price=max_price, min_price=min_price,
                                   max_age_hours=max_age_hours, order=order,
                                   limit=limit)}


@app.get("/api/categories")
def get_categories():
    return {"categories": db.category_counts()}


@app.get("/api/stores")
def get_stores():
    return {"stores": db.store_counts()}


@app.get("/api/status")
def get_status():
    return {
        "ai_enabled": categorize.ai_available(),
        "discord_enabled": notify.webhook_configured(),
        "sources": [f["name"] for f in sources.FEEDS],
        "auto_refresh_minutes": REFRESH_MINUTES,
        "last_refresh_at": _last_refresh["at"],
        "last_refresh": _last_refresh["result"],
    }


@app.post("/api/refresh")
async def refresh():
    """Manual refresh — same job the background loop runs on its own."""
    return await asyncio.to_thread(run_refresh)


@app.post("/api/notify")
def post_to_discord():
    if not notify.webhook_configured():
        raise HTTPException(status_code=400, detail="DISCORD_WEBHOOK_URL is not set")
    deals = db.list_deals(limit=25)
    posted = notify.post_top_deals(deals, limit=5)
    return {"posted": posted}
