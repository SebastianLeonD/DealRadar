from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.matcher import find_edges
from storage.db_manager import DB_PATH, ingest_staging
from web_ui.components import (
    ACTION_CATALOG,
    build_clv_dataframe,
    clv_daily_summary,
    edges_to_csv,
    format_status_label,
    load_edges_dataframe,
    pp_raw_file_exists,
    run_full_pipeline,
    run_script,
)

app = FastAPI(title="Arbitrage_CC API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _parse_feed_status(label: str) -> str:
    if "Fresh" in label:
        return "fresh"
    if "Aging" in label:
        return "aging"
    return "stale"


@app.get("/api/status/feeds")
def get_feed_status():
    dk_label, dk_detail = format_status_label("DK")
    pp_label, pp_detail = format_status_label("PP")
    return {
        "draftkings": {
            "status": _parse_feed_status(dk_label),
            "label": dk_label.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "").upper(),
            "detail": dk_detail,
        },
        "prizepicks": {
            "status": _parse_feed_status(pp_label),
            "label": pp_label.replace("🟢 ", "").replace("🟡 ", "").replace("🔴 ", "").upper(),
            "detail": pp_detail,
        },
        "database": {
            "online": DB_PATH.exists(),
            "label": "ONLINE" if DB_PATH.exists() else "MISSING",
        },
        "pp_raw_exists": pp_raw_file_exists(),
    }


@app.get("/api/actions")
def get_actions():
    return ACTION_CATALOG


@app.post("/api/pipeline/fetch-sharp")
def pipeline_fetch_sharp():
    success, output = run_script("scrapers/draftkings_api.py")
    if success:
        ingest_staging()
    return {"success": success, "output": output or "DraftKings scrape complete."}


@app.post("/api/pipeline/parse-pp")
def pipeline_parse_pp():
    if not pp_raw_file_exists():
        return {
            "success": False,
            "output": "Missing data/raw/prizepicks_raw.json — save your PP dump in the editor first.",
        }
    success, output = run_script("scrapers/prizepicks_api.py")
    if success:
        ingest_staging()
    return {"success": success, "output": output or "PrizePicks parse complete."}


@app.post("/api/pipeline/run-matcher")
def pipeline_run_matcher():
    ingest_staging()
    flagged = find_edges(sync_staging=False)
    return {
        "success": True,
        "output": f"Found {len(flagged)} advantageous play(s).",
        "edges_found": len(flagged),
    }


@app.post("/api/pipeline/full")
def pipeline_full():
    success, output = run_full_pipeline()
    return {"success": success, "output": output}


@app.get("/api/edges")
def get_edges(
    stat: str = Query("All"),
    edge_type: str = Query("All"),
):
    frame = load_edges_dataframe(stat, edge_type)
    if frame.empty:
        return {"edges": [], "summary": {"unique": 0, "line_discrepancy": 0, "ev_juice": 0}}

    line_count = int((frame["edge_type"] == "Line Discrepancy").sum())
    ev_count = int((frame["edge_type"] == "+EV Odds Juice").sum())

    return {
        "edges": frame.to_dict(orient="records"),
        "summary": {
            "unique": len(frame),
            "line_discrepancy": line_count,
            "ev_juice": ev_count,
        },
    }


@app.get("/api/edges/export")
def export_edges(
    stat: str = Query("All"),
    edge_type: str = Query("All"),
):
    frame = load_edges_dataframe(stat, edge_type)
    return PlainTextResponse(
        edges_to_csv(frame),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=edges.csv"},
    )


@app.get("/api/clv")
def get_clv(refresh: bool = Query(False)):
    frame = build_clv_dataframe(sync_staging=refresh)
    if frame.empty:
        return {
            "rows": [],
            "summary": {"unique": 0, "positive_rate": 0, "avg_clv": 0},
            "daily": [],
        }

    positive = int((frame["clv"] > 0).sum())
    avg_clv = round(float(frame["clv"].mean()), 2)
    daily = clv_daily_summary(frame)

    return {
        "rows": frame.to_dict(orient="records"),
        "summary": {
            "unique": len(frame),
            "positive_rate": round(positive / len(frame) * 100),
            "positive_count": positive,
            "avg_clv": avg_clv,
        },
        "daily": daily.to_dict(orient="records"),
    }


@app.post("/api/clv/refresh")
def refresh_clv():
    frame = build_clv_dataframe(sync_staging=True)
    if frame.empty:
        return {
            "rows": [],
            "summary": {"unique": 0, "positive_rate": 0, "avg_clv": 0},
            "daily": [],
        }

    positive = int((frame["clv"] > 0).sum())
    avg_clv = round(float(frame["clv"].mean()), 2)
    daily = clv_daily_summary(frame)

    return {
        "rows": frame.to_dict(orient="records"),
        "summary": {
            "unique": len(frame),
            "positive_rate": round(positive / len(frame) * 100),
            "positive_count": positive,
            "avg_clv": avg_clv,
        },
        "daily": daily.to_dict(orient="records"),
    }
