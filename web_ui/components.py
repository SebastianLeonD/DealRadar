from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from html import escape
from io import StringIO
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.clv_report import build_clv_rows
from engine.matcher import find_edges
from storage.db_manager import DB_PATH, get_connection, init_db, ingest_staging

FRESHNESS_MINUTES = 5

EDGE_DEDUPE_KEYS = ['player', 'play', 'pp_line', 'dk_line', 'edge_type', 'stat_type']
CLV_DEDUPE_KEYS = ['pp_player_name', 'play', 'pp_line', 'dk_line_at_flag', 'edge_type']


ACTION_CATALOG = {
    'fetch_sharp': {
        'title': 'Fetch Sharp Lines',
        'command': 'python3 scrapers/draftkings_api.py',
        'description': (
            'Calls The-Odds-API for today\'s NBA games, pulls DraftKings '
            '`player_points` props, de-vigs American odds into true Over/Under '
            'probabilities, and writes the flattened snapshot to JSON staging.'
        ),
        'api_calls': '0 credits for event list + ~1 credit per game on the slate',
        'writes_to': 'data/processed/draftkings_data.json',
    },
    'parse_pp': {
        'title': 'Parse PrizePicks',
        'command': 'python3 scrapers/prizepicks_api.py',
        'description': (
            'Reads PrizePicks raw JSON from data/raw/prizepicks_raw.json '
            '(edit that file in your IDE), filters to single-stat Points only, '
            'and outputs a flat board for matching.'
        ),
        'api_calls': 'None (local file parse only)',
        'writes_to': 'data/processed/live.json',
    },
    'run_matcher': {
        'title': 'Run Edge Detection',
        'command': 'python3 engine/matcher.py',
        'description': (
            'Syncs staging JSON into SQLite, fuzzy-matches PP player names to DK, '
            'compares latest player_points lines, flags line discrepancies and +EV juice, '
            'and logs new edges to the database.'
        ),
        'api_calls': 'None (reads local SQLite + JSON staging)',
        'writes_to': 'data/arb_engine.db → edges table',
    },
    'run_full': {
        'title': 'Run Full Pipeline',
        'command': (
            'python3 scrapers/draftkings_api.py && '
            'python3 scrapers/prizepicks_api.py && '
            'python3 engine/matcher.py'
        ),
        'description': (
            'Runs the complete workflow in order: fetch DK sharp lines, parse PP '
            'from data/raw/prizepicks_raw.json, sync both into SQLite, then detect and log edges.'
        ),
        'api_calls': 'Same as Fetch Sharp Lines (~1 credit per game). PP parse and matcher use no API.',
        'writes_to': 'draftkings_data.json, live.json, arb_engine.db',
    },
    'refresh_clv': {
        'title': 'Refresh CLV',
        'command': 'python3 engine/clv_report.py',
        'description': (
            'Re-syncs staging JSON if needed, then compares each logged edge against '
            'the latest DraftKings line to calculate line movement and Closing Line Value.'
        ),
        'api_calls': 'None (SQLite query only unless you re-scrape DK separately first)',
        'writes_to': 'Read-only report (no file writes)',
    },
}


def dedupe_edges(frame: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    if frame.empty:
        return frame

    sort_cols = ['flagged_at']
    if 'id' in frame.columns:
        sort_cols.append('id')

    deduped = frame.sort_values(sort_cols, ascending=[False] * len(sort_cols))
    return deduped.drop_duplicates(subset=keys, keep='first').reset_index(drop=True)


def run_script(relative_path: str) -> tuple[bool, str]:
    script_path = PROJECT_ROOT / relative_path
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    output = (result.stdout or '') + (result.stderr or '')
    return result.returncode == 0, output.strip()


def pp_raw_file_exists() -> bool:
    return (PROJECT_ROOT / 'data' / 'raw' / 'prizepicks_raw.json').exists()


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

    if not row or not row['last_capture']:
        return None

    return datetime.fromisoformat(row['last_capture'])


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
        return '🔴 Stale', 'No data ingested yet'

    label = '🟢 Fresh' if is_fresh(last_capture) else '🟡 Aging'
    timestamp = last_capture.strftime('%Y-%m-%d %H:%M UTC')
    return label, f'Last {source} sync: {timestamp}'


def load_edges_dataframe(
    stat_type: str = 'All',
    edge_type: str = 'All',
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
            dk_under_prob
        FROM edges
        WHERE 1 = 1
    """
    params: list[str] = []

    if stat_type != 'All':
        query += ' AND stat_type = ?'
        params.append(stat_type)

    if edge_type != 'All':
        query += ' AND edge_type = ?'
        params.append(edge_type)

    query += ' ORDER BY flagged_at DESC, id DESC'

    with get_connection() as connection:
        frame = pd.read_sql_query(query, connection, params=params)

    return dedupe_edges(frame, EDGE_DEDUPE_KEYS)


def format_bet_clipboard(row: pd.Series) -> str:
    return (
        f"{row['player']} {row['play']} {row['pp_line']} {row['stat_type']} "
        f"| DK {row['dk_line']} | {row['edge_type']}"
    )


def prizepicks_search_url(player_name: str) -> str:
    encoded = player_name.replace(' ', '+')
    return f'https://www.google.com/search?q=PrizePicks+{encoded}+props'


def build_clv_dataframe(sync_staging: bool = False) -> pd.DataFrame:
    rows = build_clv_rows(sync_staging=sync_staging)
    if not rows:
        return pd.DataFrame()

    frame = pd.DataFrame(rows)
    frame['clv_status'] = frame['clv'].apply(
        lambda value: 'Positive' if value > 0 else ('Neutral' if value == 0 else 'Negative')
    )
    frame['player'] = frame['pp_player_name']
    frame['original_line'] = frame['pp_line']
    frame['dk_line_now'] = frame['closing_dk_line']
    frame['movement'] = frame['dk_move']
    return dedupe_edges(frame, CLV_DEDUPE_KEYS)


def clv_daily_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=['date', 'avg_clv', 'edge_count'])

    summary = frame.copy()
    summary['date'] = pd.to_datetime(summary['flagged_at'], utc=True).dt.date
    grouped = (
        summary.groupby('date', as_index=False)
        .agg(avg_clv=('clv', 'mean'), edge_count=('clv', 'count'))
        .sort_values('date')
    )
    grouped['avg_clv'] = grouped['avg_clv'].round(2)
    return grouped.tail(7)


def edges_to_csv(frame: pd.DataFrame) -> str:
    buffer = StringIO()
    frame.to_csv(buffer, index=False)
    return buffer.getvalue()


def edge_row_class(edge_type: str) -> str:
    if edge_type == 'Line Discrepancy':
        return 'line-discrepancy'
    return 'ev-juice'


def edge_pill_class(edge_type: str) -> str:
    if edge_type == 'Line Discrepancy':
        return 'pill-cyan'
    return 'pill-purple'


def play_pill_class(play: str) -> str:
    return 'pill-play-over' if play == 'OVER' else 'pill-play-under'


def render_edges_table_html(frame: pd.DataFrame) -> str:
    if frame.empty:
        return '<div class="empty-state">No active opportunities yet. Run edge detection first.</div>'

    rows: list[str] = [
        """
        <div class="edge-head">
            <div>Player</div>
            <div>Edge</div>
            <div>Play</div>
            <div>PP</div>
            <div>DK</div>
            <div>Detail</div>
            <div>Flagged</div>
        </div>
        <div class="edge-table">
        """
    ]

    for _, row in frame.iterrows():
        flagged = pd.to_datetime(row['flagged_at'], utc=True).strftime('%m/%d %H:%M')
        row_class = edge_row_class(row['edge_type'])
        edge_pill = edge_pill_class(row['edge_type'])
        play_pill = play_pill_class(row['play'])
        rows.append(
            f"""
            <div class="edge-row {row_class}">
                <div>
                    <div class="cell-title">{escape(str(row['player']))}</div>
                    <div class="cell-sub">{escape(str(row.get('team') or ''))}</div>
                </div>
                <div><span class="edge-pill {edge_pill}">{escape(str(row['edge_type']))}</span></div>
                <div><span class="edge-pill {play_pill}">{escape(str(row['play']))}</span></div>
                <div><span class="edge-pill pill-orange">{row['pp_line']}</span></div>
                <div><span class="edge-pill pill-cyan">{row['dk_line']}</span></div>
                <div class="cell-sub">{escape(str(row.get('probability_text') or ''))}</div>
                <div class="cell-sub">{flagged}</div>
            </div>
            """
        )

    rows.append('</div>')
    return ''.join(rows)


def render_clv_table_html(frame: pd.DataFrame) -> str:
    if frame.empty:
        return '<div class="empty-state">No CLV data yet. Log edges, re-scrape DK, then refresh.</div>'

    rows: list[str] = [
        """
        <div class="edge-head">
            <div>Player</div>
            <div>Edge</div>
            <div>Play</div>
            <div>Orig</div>
            <div>DK Now</div>
            <div>Move</div>
            <div>CLV</div>
        </div>
        <div class="edge-table">
        """
    ]

    for _, row in frame.iterrows():
        row_class = edge_row_class(row['edge_type'])
        edge_pill = edge_pill_class(row['edge_type'])
        play_pill = play_pill_class(row['play'])
        clv_class = 'pill-play-over' if row['clv'] > 0 else 'pill-play-under'
        rows.append(
            f"""
            <div class="edge-row {row_class}">
                <div><div class="cell-title">{escape(str(row['player']))}</div></div>
                <div><span class="edge-pill {edge_pill}">{escape(str(row['edge_type']))}</span></div>
                <div><span class="edge-pill {play_pill}">{escape(str(row['play']))}</span></div>
                <div><span class="edge-pill pill-orange">{row['original_line']}</span></div>
                <div><span class="edge-pill pill-cyan">{row['dk_line_now']}</span></div>
                <div><span class="edge-pill pill-purple">{row['movement']}</span></div>
                <div><span class="edge-pill {clv_class}">{row['clv']}</span></div>
            </div>
            """
        )

    rows.append('</div>')
    return ''.join(rows)


def render_status_html(dk_status: str, pp_status: str, db_online: bool, dk_detail: str, pp_detail: str) -> str:
    db_label = 'Online' if db_online else 'Missing'
    return f"""
    <div class="status-grid">
        <div class="status-tile">
            <div class="status-label">DraftKings Feed</div>
            <div class="status-value">{escape(dk_status)}</div>
        </div>
        <div class="status-tile">
            <div class="status-label">PrizePicks Feed</div>
            <div class="status-value">{escape(pp_status)}</div>
        </div>
        <div class="status-tile">
            <div class="status-label">Database</div>
            <div class="status-value">{db_label}</div>
        </div>
    </div>
    <div class="cell-sub">{escape(dk_detail)} · {escape(pp_detail)}</div>
    """


def render_metric_strip(items: list[tuple[str, str]]) -> str:
    boxes = []
    for label, value in items:
        boxes.append(
            f"""
            <div class="metric-box">
                <div class="label">{escape(label)}</div>
                <div class="value">{escape(value)}</div>
            </div>
            """
        )
    return f'<div class="metric-strip">{"".join(boxes)}</div>'


def run_full_pipeline() -> tuple[bool, str]:
    messages: list[str] = []

    if not pp_raw_file_exists():
        return False, 'Missing data/raw/prizepicks_raw.json — save your PP dump in the editor first.'

    success, output = run_script('scrapers/draftkings_api.py')
    messages.append(output or 'DraftKings scrape finished.')
    if not success:
        return False, '\n'.join(messages)

    success, output = run_script('scrapers/prizepicks_api.py')
    messages.append(output or 'PrizePicks parse finished.')
    if not success:
        return False, '\n'.join(messages)

    ingest_results = ingest_staging()
    messages.append(f'Synced staging JSON to SQLite: {ingest_results}')

    flagged = find_edges(sync_staging=False)
    messages.append(f'Edge detection complete. Found {len(flagged)} play(s).')
    return True, '\n'.join(messages)
