"""DealRadar — FastAPI backend + dashboard.

Run with:  uvicorn app.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from app import categorize, db, notify, sources

app = FastAPI(title="DealRadar", version="0.1.0")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/deals")
def get_deals(
    category: str | None = None,
    q: str | None = None,
    item: str | None = None,
    store: str | None = None,
    max_price: float | None = Query(default=None, ge=0),
    min_price: float | None = Query(default=None, ge=0),
    limit: int = Query(default=100, le=500),
):
    return {"deals": db.list_deals(category=category, q=q, item=item, store=store,
                                   max_price=max_price, min_price=min_price,
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
    }


@app.post("/api/refresh")
def refresh():
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

    return {
        "fetched": len(fetched),
        "new": new_count,
        "ai_scored": scored,
        "ai_error": ai_error,
        "source_errors": errors,
    }


@app.post("/api/notify")
def post_to_discord():
    if not notify.webhook_configured():
        raise HTTPException(status_code=400, detail="DISCORD_WEBHOOK_URL is not set")
    deals = db.list_deals(limit=25)
    posted = notify.post_top_deals(deals, limit=5)
    return {"posted": posted}
