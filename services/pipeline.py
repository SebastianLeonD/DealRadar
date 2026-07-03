from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")  # show all times in NY Eastern

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.ai_analyst import opponent_from_game
from engine.clv_report import build_clv_rows
from engine.matcher import find_edges
from engine.sports import active_sport_key
from storage.db_manager import get_connection, get_player_game_map, init_db, ingest_staging

FRESHNESS_MINUTES = 5

# A soccer match runs ~2h with halftime and stoppage; once this much time has
# passed since kickoff the game is treated as over and drops off the board.
MATCH_OVER_HOURS = 2.5

EDGE_DEDUPE_KEYS = ["player", "play", "pp_line", "dk_line", "edge_type", "stat_type"]
CLV_DEDUPE_KEYS = ["pp_player_name", "play", "pp_line", "dk_line_at_flag", "edge_type", "stat_type"]

ACTION_CATALOG = {
    "fetch_sharp": {
        "title": "Fetch Sharp Lines",
        "command": "python3 scrapers/draftkings_api.py",
        "description": (
            "Calls The-Odds-API for the active sport (ACTIVE_SPORT in .env: nba or "
            "world_cup), pulls every configured player-prop market from DK/FD/MGM/Caesars, "
            "de-vigs the prices, and writes the flattened snapshot to JSON staging. "
            "Only games starting within the kickoff window are fetched."
        ),
        "api_calls": "0 credits for event list + ~1 credit per market per game",
        "writes_to": "data/processed/draftkings_data.json",
    },
    "parse_pp": {
        "title": "Parse PrizePicks",
        "command": "python3 scrapers/prizepicks_api.py",
        "description": (
            "Reads PrizePicks raw JSON from data/raw/prizepicks_raw.json "
            "(edit that file in your IDE), filters to single-stat Points only, "
            "and outputs a flat board for matching."
        ),
        "api_calls": "None (local file parse only)",
        "writes_to": "data/processed/live.json",
    },
    "fetch_form": {
        "title": "Update World Cup Form",
        "command": "python3 scrapers/fbref_stats.py",
        "description": (
            "Scrapes World Cup player AND team stats from FBref (via soccerdata, "
            "which clears Cloudflare). Player stats price book-less PrizePicks "
            "stats (saves, fouls, tackles, crosses, offsides — capped at MAYBE). "
            "Team profiles (attack/defense/style) feed the AI analyst as live "
            "matchup context. Cached locally; only new matches trigger a fetch."
        ),
        "api_calls": "None billed — FBref is free (web scrape)",
        "writes_to": "data/processed/fbref_wc_stats.json, fbref_wc_teams.json",
    },
    "fetch_underdog": {
        "title": "Update Underdog Lines",
        "command": "python3 scrapers/underdog_api.py",
        "description": (
            "Fetches Underdog Fantasy's open pick'em board directly (no key, no "
            "paste — unlike PrizePicks), filters to FIFA player props, and maps "
            "each to the engine's stat keys. The PrizePicks Board tab then shows "
            "Underdog's line beside each PP prop so you can shop the softer side."
        ),
        "api_calls": "None billed — Underdog's lines endpoint is public JSON",
        "writes_to": "data/processed/underdog_data.json",
    },
    "fetch_pinnacle": {
        "title": "Update Pinnacle Lines",
        "command": "python3 scrapers/pinnacle_api.py",
        "description": (
            "Pulls Pinnacle — the sharpest book in the world — goalscorer odds "
            "free (no key), giving goal props a second sharp book at the same "
            "line so they can reach YES."
        ),
        "api_calls": "None billed — Pinnacle's odds endpoint is public JSON",
        "writes_to": "data/processed/pinnacle_sharp.json",
    },
    "run_matcher": {
        "title": "Run Edge Detection",
        "command": "python3 engine/matcher.py",
        "description": (
            "Syncs staging JSON into SQLite, fuzzy-matches PP player names to DK, "
            "compares latest player_points lines, flags line discrepancies and +EV juice, "
            "and logs new edges to the database."
        ),
        "api_calls": "None (reads local SQLite + JSON staging)",
        "writes_to": "data/arb_engine.db → edges table",
    },
    "run_full": {
        "title": "Run Full Pipeline",
        "command": (
            "python3 scrapers/draftkings_api.py && "
            "python3 scrapers/prizepicks_api.py && "
            "python3 engine/matcher.py"
        ),
        "description": (
            "Runs the complete workflow in order: fetch DK sharp lines, parse PP "
            "from data/raw/prizepicks_raw.json, sync both into SQLite, then detect and log edges."
        ),
        "api_calls": "Same as Fetch Sharp Lines (~1 credit per game). PP parse and matcher use no API.",
        "writes_to": "draftkings_data.json, live.json, arb_engine.db",
    },
    "refresh_clv": {
        "title": "Refresh CLV",
        "command": "python3 engine/clv_report.py",
        "description": (
            "Re-syncs staging JSON if needed, then compares each logged edge against "
            "the latest DraftKings line to calculate line movement and Closing Line Value."
        ),
        "api_calls": "None (SQLite query only unless you re-scrape DK separately first)",
        "writes_to": "Read-only report (no file writes)",
    },
    "settle_results": {
        "title": "Settle Results",
        "command": "python3 engine/settlement.py",
        "description": (
            "Pulls finished-game box scores from ESPN (free, no key), grades every "
            "logged edge as WIN/LOSS/PUSH, and prints your lifetime record plus the "
            "model calibration gap (predicted win% vs actual hit rate)."
        ),
        "api_calls": "None billed — ESPN's public API is free",
        "writes_to": "data/arb_engine.db → edges table (result, actual_value)",
    },
}


def dedupe_edges(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame

    sort_cols = ["flagged_at"]
    if "id" in frame.columns:
        sort_cols.append("id")

    deduped = frame.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return deduped.drop_duplicates(subset=keys, keep="first").reset_index(drop=True)


def run_script(relative_path: str) -> tuple[bool, str]:
    script_path = PROJECT_ROOT / relative_path
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired:
        return False, f"{relative_path} timed out after 900s"
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output.strip()


def pp_raw_file_exists() -> bool:
    return (PROJECT_ROOT / "data" / "raw" / "prizepicks_raw.json").exists()


def get_last_capture(source: str) -> datetime | None:
    init_db()
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT MAX(captured_at) AS last_capture
            FROM props
            WHERE source = ?
            """,
            (source,),
        ).fetchone()

    if not row or not row["last_capture"]:
        return None

    return datetime.fromisoformat(row["last_capture"])


def is_fresh(captured_at: datetime | None, minutes: int = FRESHNESS_MINUTES) -> bool:
    if captured_at is None:
        return False
    now = datetime.now(timezone.utc)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    return (now - captured_at).total_seconds() <= minutes * 60


def format_status_label(source: str) -> tuple[str, str]:
    last_capture = get_last_capture(source)
    if last_capture is None:
        return "stale", "No data ingested yet"

    status = "fresh" if is_fresh(last_capture) else "aging"
    when = last_capture
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    timestamp = when.astimezone(EASTERN).strftime("%Y-%m-%d %H:%M ET")
    return status, f"Last {source} sync: {timestamp}"


def load_edges_dataframe(
    stat_type: str = "All",
    edge_type: str = "All",
    active_only: bool = True,
) -> pd.DataFrame:
    init_db()
    query = """
        SELECT
            id,
            flagged_at,
            pp_player_name AS player,
            dk_player_name,
            team,
            stat_type,
            play,
            pp_line,
            dk_line_at_flag AS dk_line,
            edge_type,
            probability_text,
            dk_over_prob,
            dk_under_prob,
            win_prob,
            ev_percent,
            verdict,
            flags,
            book_count,
            commence_time,
            result,
            actual_value,
            model_p,
            model_p_side,
            model_credibility,
            consensus_n,
            consensus_tag,
            best_venue,
            venue_note,
            ai_pick,
            ai_confidence
        FROM edges
        WHERE 1 = 1
    """
    params: list[str] = []

    if stat_type != "All":
        query += " AND stat_type = ?"
        params.append(stat_type)

    if edge_type != "All":
        query += " AND edge_type = ?"
        params.append(edge_type)

    query += " ORDER BY flagged_at DESC, id DESC"

    with get_connection() as connection:
        frame = pd.read_sql_query(query, connection, params=params)

    frame = dedupe_edges(frame, EDGE_DEDUPE_KEYS)
    if frame.empty:
        return frame

    if active_only:
        # "Upcoming picks" = unsettled plays whose game hasn't finished yet.
        # Settled results, games that ended hours ago, and rows with no start
        # time all drop off. Future days stay so every stat type can surface.
        local_tz = datetime.now().astimezone().tzinfo
        kickoff = pd.to_datetime(
            frame["commence_time"], utc=True, errors="coerce"
        ).dt.tz_convert(local_tz)
        now = pd.Timestamp.now(tz=local_tz)
        ended_before = now - pd.Timedelta(hours=MATCH_OVER_HOURS)
        frame = frame[
            frame["result"].isna()
            & kickoff.notna()
            & (kickoff >= ended_before)
        ]
        if frame.empty:
            return frame.reset_index(drop=True)

    frame = frame.sort_values(
        ["win_prob", "flagged_at"], ascending=[False, False], na_position="last"
    ).reset_index(drop=True)
    # Attach the matchup so the UI can show it and the AI can reason on it.
    game_map = get_player_game_map()
    frame["game"] = frame["dk_player_name"].map(game_map).fillna("")
    frame["opponent"] = frame.apply(
        lambda row: opponent_from_game(row["game"], row["team"]), axis=1
    )
    # NaN is invalid JSON; old rows predate the verdict columns.
    frame = frame.astype(object).where(pd.notna(frame), None)
    return frame


def build_clv_dataframe(sync_staging: bool = False) -> pd.DataFrame:
    rows = build_clv_rows(sync_staging=sync_staging)
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame["clv_status"] = frame["clv"].apply(
        lambda value: "Positive" if value > 0 else ("Neutral" if value == 0 else "Negative")
    )
    frame["player"] = frame["pp_player_name"]
    frame["original_line"] = frame["pp_line"]
    frame["dk_line_now"] = frame["closing_dk_line"]
    frame["movement"] = frame["dk_move"]
    return dedupe_edges(frame, CLV_DEDUPE_KEYS)


def clv_daily_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["date", "avg_clv", "edge_count"])

    summary = frame.copy()
    summary["date"] = pd.to_datetime(summary["flagged_at"], utc=True).dt.date
    grouped = (
        summary.groupby("date", as_index=False)
        .agg(avg_clv=("clv", "mean"), edge_count=("clv", "count"))
        .sort_values("date")
    )
    grouped["avg_clv"] = grouped["avg_clv"].round(2)
    return grouped.tail(7)


def edges_to_csv(frame: pd.DataFrame) -> str:
    buffer = StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()


def run_full_pipeline() -> tuple[bool, str]:
    messages: list[str] = []

    if not pp_raw_file_exists():
        return False, "Missing data/raw/prizepicks_raw.json — save your PP dump in the editor first."

    success, output = run_script("scrapers/draftkings_api.py")
    messages.append(output or "DraftKings scrape finished.")
    if not success:
        return False, "\n".join(messages)

    success, output = run_script("scrapers/prizepicks_api.py")
    messages.append(output or "PrizePicks parse finished.")
    if not success:
        return False, "\n".join(messages)

    # Pinnacle is a World Cup-only connector and non-fatal: on failure the
    # previous staging file keeps its own fetched_at stamp, so a stale board
    # can never re-enter consensus looking fresh.
    if active_sport_key() == "world_cup":
        _, output = run_script("scrapers/pinnacle_api.py")
        messages.append(output or "Pinnacle fetch finished.")

    ingest_results = ingest_staging()
    messages.append(f"Synced staging JSON to SQLite: {ingest_results}")

    flagged = find_edges(sync_staging=False)
    messages.append(f"Edge detection complete. Found {len(flagged)} play(s).")
    return True, "\n".join(messages)
