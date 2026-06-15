from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.matcher import find_edges
from storage.db_manager import DB_PATH, get_record_summary, ingest_staging
from services.pipeline import (
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


@app.get("/api/status/feeds")
def get_feed_status():
    dk_status, dk_detail = format_status_label("DK")
    pp_status, pp_detail = format_status_label("PP")
    return {
        "draftkings": {
            "status": dk_status,
            "label": dk_status.upper(),
            "detail": dk_detail,
        },
        "prizepicks": {
            "status": pp_status,
            "label": pp_status.upper(),
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


@app.post("/api/pipeline/fetch-form")
def pipeline_fetch_form():
    wc_ok, wc_out = run_script("scrapers/fbref_stats.py")
    club_ok, club_out = run_script("scrapers/fbref_club_stats.py")
    output = f"{wc_out}\n\n{club_out}".strip()
    return {"success": wc_ok and club_ok, "output": output or "Form stats updated."}


@app.post("/api/pipeline/fetch-underdog")
def pipeline_fetch_underdog():
    success, output = run_script("scrapers/underdog_api.py")
    return {"success": success, "output": output or "Underdog board updated."}


@app.post("/api/pipeline/settle")
def pipeline_settle():
    success, output = run_script("engine/settlement.py")
    return {"success": success, "output": output or "Settlement complete."}


class AnalyzeRequest(BaseModel):
    """An edge row as the frontend already holds it (all fields optional)."""

    player: str | None = None
    pp_player_name: str | None = None
    dk_player_name: str | None = None
    team: str | None = None
    opponent: str | None = None
    game: str | None = None
    stat_type: str | None = None
    play: str | None = None
    pp_line: float | None = None
    dk_line: float | None = None
    dk_line_at_flag: float | None = None
    edge_type: str | None = None
    verdict: str | None = None
    win_prob: float | None = None
    ev_percent: float | None = None
    book_count: int | None = None
    commence_time: str | None = None
    flags: str | None = None
    mode: str = "full"  # "full" (with sharp books) or "stats_only" (PrizePicks-only)


def _with_matchup(edge: dict) -> dict:
    """Fill in the opponent/game so the analyst always knows the matchup."""
    from engine.ai_analyst import opponent_from_game
    from storage.db_manager import get_player_game_map

    if not edge.get("game"):
        player = edge.get("dk_player_name") or edge.get("player")
        edge["game"] = get_player_game_map().get(player, "")
    if not edge.get("opponent"):
        edge["opponent"] = opponent_from_game(edge.get("game"), edge.get("team"))
    return edge


@app.post("/api/edges/prompt")
def preview_prompt(req: AnalyzeRequest):
    """Show exactly what would be sent to Claude — no model call, no billing."""
    from engine.ai_analyst import describe_request

    payload = req.model_dump()
    mode = payload.pop("mode", "full")
    edge = _with_matchup(payload)
    return {"ok": True, "opponent": edge.get("opponent"),
            "sent": describe_request(edge, mode=mode)}


@app.post("/api/edges/analyze")
def analyze_edge(req: AnalyzeRequest):
    """Second-opinion OVER/UNDER/PASS call from Claude (your subscription)."""
    from engine.ai_analyst import analyze_play, describe_request

    payload = req.model_dump()
    mode = payload.pop("mode", "full")
    edge = _with_matchup(payload)
    sent = describe_request(edge, mode=mode)

    try:
        recommendation = analyze_play(edge, mode=mode)
        return {
            "ok": True,
            "recommendation": recommendation,
            "opponent": edge.get("opponent"),
            "sent": sent,
        }
    except Exception as error:  # surface a clean message to the UI
        return {"ok": False, "error": str(error), "opponent": edge.get("opponent"), "sent": sent}


@app.get("/api/prizepicks/board")
def get_prizepicks_board():
    """Every PrizePicks prop you pasted, grouped by stat type — the full menu,
    including stats no sportsbook prices. `has_form_data` marks which stats the
    AI has real numbers for (vs. ones it can only reason about generally)."""
    import json
    from collections import Counter, defaultdict
    from datetime import datetime, timedelta, timezone

    from engine import line_shop
    from engine.projections import FORM_FIELD_BY_STAT
    from services.pipeline import MATCH_OVER_HOURS

    board_file = PROJECT_ROOT / "data" / "processed" / "pp_board.json"
    if not board_file.exists():
        return {"total": 0, "groups": [], "games": []}
    with board_file.open() as file:
        props = json.load(file)

    # Drop props whose game already finished (~2h+ since kickoff). Upcoming and
    # in-progress games stay; missing/unparseable times are kept, never hidden.
    cutoff = datetime.now(timezone.utc) - timedelta(hours=MATCH_OVER_HOURS)

    def still_on(prop: dict) -> bool:
        start = prop.get("start_time")
        if not start:
            return True
        try:
            kickoff = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except ValueError:
            return True
        return kickoff >= cutoff

    props = [prop for prop in props if still_on(prop)]

    # Underdog line-shop: attach UD's line for the same player + stat.
    ud_index = line_shop.build_index(line_shop.load_underdog())

    def has_form(mapped: str | None) -> bool:
        if not mapped:
            return False
        return mapped.replace("_1h", "") in FORM_FIELD_BY_STAT

    grouped: dict[str, dict] = defaultdict(
        lambda: {"props": [], "mapped_stat": None, "has_form_data": False}
    )
    for prop in props:
        g = grouped[prop["stat_type"]]
        g["mapped_stat"] = prop.get("mapped_stat")
        g["has_form_data"] = has_form(prop.get("mapped_stat"))
        ud = line_shop.match_prop(
            prop["name"],
            line_shop.normalize(prop["name"]),
            line_shop.pp_join_key(prop.get("mapped_stat"), prop["stat_type"]),
            prop["line"],
            ud_index,
        )
        g["props"].append(
            {
                "player": prop["name"],
                "team": prop.get("team"),
                "line": prop["line"],
                "position": prop.get("position"),
                "image_url": prop.get("image_url"),
                "opponent": prop.get("opponent"),
                "game_id": prop.get("game_id"),
                "start_time": prop.get("start_time"),
                "underdog": ud,
            }
        )

    groups = [
        {"stat_type": stat, "count": len(g["props"]), **g}
        for stat, g in grouped.items()
    ]
    # Stats we can actually analyze first, then by how many props.
    groups.sort(key=lambda g: (g["has_form_data"], g["count"]), reverse=True)

    # The matchups on the board, keeping only games that actually have props.
    games_file = PROJECT_ROOT / "data" / "processed" / "pp_games.json"
    games: list[dict] = []
    if games_file.exists():
        with games_file.open() as file:
            all_games = json.load(file)
        counts = Counter(p.get("game_id") for p in props)
        games = [
            {**game, "count": counts[game["game_id"]]}
            for game in all_games
            if counts.get(game["game_id"])
        ]
        games.sort(key=lambda g: g.get("start_time") or "")

    return {"total": len(props), "groups": groups, "games": games}


@app.get("/api/record")
def get_record():
    return get_record_summary()


class TrackBetRequest(AnalyzeRequest):
    """An edge the user is logging as a placed bet, plus an optional stake."""

    stake: float | None = None


@app.post("/api/bets")
def track_bet(req: TrackBetRequest):
    from storage.db_manager import add_bet

    payload = req.model_dump()
    player = payload.get("player") or payload.get("dk_player_name")
    if not player or payload.get("stat_type") is None or payload.get("pp_line") is None:
        return {"ok": False, "error": "Missing player, stat, or line."}

    bet = {
        "pp_player_name": player,
        "dk_player_name": payload.get("dk_player_name") or player,
        "team": payload.get("team"),
        "opponent": payload.get("opponent"),
        "stat_type": payload["stat_type"],
        "play": payload.get("play") or "OVER",
        "pp_line": payload["pp_line"],
        "dk_line": payload.get("dk_line"),
        "win_prob": payload.get("win_prob"),
        "ev_percent": payload.get("ev_percent"),
        "verdict": payload.get("verdict"),
        "edge_type": payload.get("edge_type"),
        "book_count": payload.get("book_count"),
        "commence_time": payload.get("commence_time"),
        "stake": payload.get("stake"),
    }
    bet_id = add_bet(bet)
    if bet_id is None:
        return {"ok": True, "duplicate": True}
    return {"ok": True, "id": bet_id}


@app.get("/api/bets")
def list_bets():
    from storage.db_manager import get_bet_record_summary, get_bets

    return {"bets": get_bets(), "summary": get_bet_record_summary()}


@app.post("/api/bets/settle")
def settle_my_bets():
    from engine.settlement import settle_bets

    settled, report = settle_bets()
    return {"success": True, "settled": settled, "output": "\n".join(report)}


@app.delete("/api/bets/{bet_id}")
def remove_bet(bet_id: int):
    from storage.db_manager import delete_bet

    return {"ok": delete_bet(bet_id)}


@app.get("/api/edges")
def get_edges(
    stat: str = Query("All"),
    edge_type: str = Query("All"),
):
    frame = load_edges_dataframe(stat, edge_type)
    all_stats = load_edges_dataframe("All", "All")
    stats = sorted(all_stats["stat_type"].dropna().unique()) if not all_stats.empty else []

    if frame.empty:
        return {
            "edges": [],
            "summary": {
                "unique": 0, "line_discrepancy": 0, "ev_juice": 0, "yes_count": 0,
                "stats": stats,
            },
        }

    line_count = int((frame["edge_type"] == "Line Discrepancy").sum())
    ev_count = int((frame["edge_type"] == "+EV Odds Juice").sum())
    yes_count = int((frame["verdict"] == "YES").sum())

    edges = frame.to_dict(orient="records")
    _attach_underdog(edges)

    return {
        "edges": edges,
        "summary": {
            "unique": len(frame),
            "line_discrepancy": line_count,
            "ev_juice": ev_count,
            "yes_count": yes_count,
            "stats": stats,
        },
    }


def _attach_underdog(edges: list[dict]) -> None:
    """Add Underdog's line + which app to bet the engine's side on, per edge.

    Edges are engine-keyed, so the stat_type is itself the join key (a _1h key
    only matches UD first-half props — never a full-match line)."""
    from engine import line_shop

    index = line_shop.build_index(line_shop.load_underdog())
    for edge in edges:
        player = edge.get("player") or edge.get("dk_player_name") or ""
        pp_line = edge.get("pp_line")
        if not player or pp_line is None:
            edge["underdog"] = None
            continue
        edge["underdog"] = line_shop.match_edge(
            edge.get("play", ""),
            player,
            line_shop.normalize(player),
            edge.get("stat_type", ""),
            pp_line,
            index,
        )


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
