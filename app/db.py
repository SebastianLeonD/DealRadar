"""SQLite storage for deals. DB file lives at data/dealradar.db (auto-created)."""

import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "dealradar.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id          TEXT PRIMARY KEY,          -- sha1 of the deal URL
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    source      TEXT NOT NULL,             -- e.g. 'slickdeals', 'r/deals'
    category    TEXT NOT NULL DEFAULT 'Other',
    store       TEXT,                      -- retailer: Amazon, Zara, ASOS, ...
    price       REAL,                      -- extracted from title, NULL if none found
    posted_at   TEXT,                      -- ISO timestamp from the feed, if any
    fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
    ai_score    INTEGER,                   -- 1-10, NULL until Claude scores it
    ai_take     TEXT                       -- one-line verdict from Claude
);
CREATE INDEX IF NOT EXISTS idx_deals_category ON deals(category);
CREATE INDEX IF NOT EXISTS idx_deals_fetched ON deals(fetched_at);
"""

# Columns added after the first release — applied to pre-existing DBs on connect.
_MIGRATION_COLUMNS = {"store": "TEXT", "price": "REAL"}


def deal_id(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(deals)")}
    for col, coltype in _MIGRATION_COLUMNS.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE deals ADD COLUMN {col} {coltype}")
    return conn


def upsert_deals(deals: list[dict]) -> int:
    """Insert deals, skipping ones we've already seen. Returns count of new rows."""
    new = 0
    with connect() as conn:
        for d in deals:
            cur = conn.execute(
                """INSERT OR IGNORE INTO deals
                   (id, title, url, source, category, store, price, posted_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (deal_id(d["url"]), d["title"], d["url"], d["source"],
                 d.get("category", "Other"), d.get("store"), d.get("price"),
                 d.get("posted_at")),
            )
            new += cur.rowcount
    return new


def set_ai_result(url_id: str, score: int, take: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE deals SET ai_score = ?, ai_take = ? WHERE id = ?",
                     (score, take, url_id))


def unscored_deals(limit: int = 30) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM deals WHERE ai_score IS NULL ORDER BY fetched_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def list_deals(
    category: str | None = None,
    q: str | None = None,
    item: str | None = None,
    store: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    limit: int = 100,
) -> list[dict]:
    sql = "SELECT * FROM deals"
    clauses, params = [], []
    if category and category != "All":
        clauses.append("category = ?")
        params.append(category)
    if q:
        clauses.append("title LIKE ?")
        params.append(f"%{q}%")
    if item and item != "All":
        clauses.append("title LIKE ?")
        params.append(f"%{item}%")
    if store and store != "All":
        clauses.append("store = ?")
        params.append(store)
    if max_price is not None:
        clauses.append("price IS NOT NULL AND price <= ?")
        params.append(max_price)
    if min_price is not None:
        clauses.append("price IS NOT NULL AND price >= ?")
        params.append(min_price)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY ai_score IS NULL, ai_score DESC, fetched_at DESC LIMIT ?"
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def store_counts() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT store, COUNT(*) AS n FROM deals
               WHERE store IS NOT NULL GROUP BY store ORDER BY n DESC"""
        ).fetchall()
    return [dict(r) for r in rows]


def category_counts() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT category, COUNT(*) AS n FROM deals GROUP BY category ORDER BY n DESC"
        ).fetchall()
    return [dict(r) for r in rows]
