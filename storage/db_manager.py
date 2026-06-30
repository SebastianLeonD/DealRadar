import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path('data/arb_engine.db')
DK_STAGING_FILE = Path('data/processed/draftkings_data.json')
PP_STAGING_FILE = Path('data/processed/live.json')

TABLES_SCHEMA = """
CREATE TABLE IF NOT EXISTS props (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_name TEXT NOT NULL,
    team TEXT,
    stat_type TEXT NOT NULL,
    line REAL NOT NULL,
    true_over_prob REAL,
    true_under_prob REAL,
    price_over INTEGER,
    price_under INTEGER,
    devig_method TEXT,
    shin_z REAL,
    hold REAL,
    league TEXT,
    league_id TEXT,
    sport_key TEXT,
    game_id TEXT,
    fetch_status TEXT NOT NULL DEFAULT 'ok',
    source TEXT NOT NULL CHECK(source IN ('DK', 'PP')),
    bookmaker TEXT NOT NULL DEFAULT 'draftkings',
    game TEXT,
    commence_time TEXT,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pp_player_name TEXT NOT NULL,
    dk_player_name TEXT NOT NULL,
    team TEXT,
    stat_type TEXT NOT NULL,
    play TEXT NOT NULL CHECK(play IN ('OVER', 'UNDER')),
    pp_line REAL NOT NULL,
    dk_line_at_flag REAL NOT NULL,
    edge_type TEXT NOT NULL,
    dk_over_prob REAL,
    dk_under_prob REAL,
    probability_text TEXT,
    win_prob REAL,
    ev_percent REAL,
    verdict TEXT,
    flags TEXT,
    book_count INTEGER,
    commence_time TEXT,
    result TEXT,
    actual_value REAL,
    settled_at TEXT,
    consensus_n INTEGER,
    consensus_tag TEXT,
    config_version TEXT,
    flagged_at TEXT NOT NULL,
    pp_captured_at TEXT,
    dk_captured_at TEXT
);
"""

INDEX_SCHEMA = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_props_upsert_v2
    ON props(player_name, stat_type, source, bookmaker, line);

CREATE INDEX IF NOT EXISTS idx_props_latest
    ON props(source, stat_type, player_name, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_edges_flagged_at
    ON edges(flagged_at DESC);

CREATE INDEX IF NOT EXISTS idx_edges_dk_player
    ON edges(dk_player_name, stat_type, flagged_at DESC);

CREATE INDEX IF NOT EXISTS idx_edges_unsettled
    ON edges(result, flagged_at DESC);
"""

PROPS_MIGRATION_COLUMNS = {
    'bookmaker': "TEXT NOT NULL DEFAULT 'draftkings'",
    'commence_time': 'TEXT',
    # Council OBJ-7: persist the raw American prices + de-vig provenance so any
    # true prob is recompute-attributable (the bake-off needs the raw odds).
    'price_over': 'INTEGER',
    'price_under': 'INTEGER',
    'devig_method': 'TEXT',
    'shin_z': 'REAL',
    'hold': 'REAL',
    # Multi-sport seam (OBJ-4/7) + typed fetch failures (OBJ http-robustness).
    'league': 'TEXT',
    'league_id': 'TEXT',
    'sport_key': 'TEXT',
    'game_id': 'TEXT',
    'fetch_status': "TEXT NOT NULL DEFAULT 'ok'",
}

EDGES_MIGRATION_COLUMNS = {
    'win_prob': 'REAL',
    'ev_percent': 'REAL',
    'verdict': 'TEXT',
    'flags': 'TEXT',
    'book_count': 'INTEGER',
    'commence_time': 'TEXT',
    'result': 'TEXT',
    'actual_value': 'REAL',
    'settled_at': 'TEXT',
    # Consensus provenance + reproducibility stamp (OBJ-1/3, OBJ-41).
    'consensus_n': 'INTEGER',
    'consensus_tag': 'TEXT',
    'config_version': 'TEXT',
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _migrate(connection: sqlite3.Connection) -> None:
    for table, columns in (('props', PROPS_MIGRATION_COLUMNS), ('edges', EDGES_MIGRATION_COLUMNS)):
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, ddl in columns.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # The upsert key now includes bookmaker; replace the old unique index.
    connection.execute("DROP INDEX IF EXISTS idx_props_upsert")

    # Rows ingested before the bookmaker column got the 'draftkings' default;
    # re-label PP rows so per-bookmaker grouping never duplicates a player.
    connection.execute(
        "UPDATE OR IGNORE props SET bookmaker = 'prizepicks' "
        "WHERE source = 'PP' AND bookmaker != 'prizepicks'"
    )
    connection.execute(
        "DELETE FROM props WHERE source = 'PP' AND bookmaker != 'prizepicks'"
    )


def init_db(db_path: Path = DB_PATH) -> None:
    with get_connection(db_path) as connection:
        connection.executescript(TABLES_SCHEMA)
        _migrate(connection)
        connection.executescript(INDEX_SCHEMA)


def upsert_prop(
    connection: sqlite3.Connection,
    *,
    player_name: str,
    team: str | None,
    stat_type: str,
    line: float,
    source: str,
    captured_at: str,
    true_over_prob: float | None = None,
    true_under_prob: float | None = None,
    game: str | None = None,
    bookmaker: str = 'draftkings',
    commence_time: str | None = None,
    price_over: int | None = None,
    price_under: int | None = None,
    devig_method: str | None = None,
    shin_z: float | None = None,
    hold: float | None = None,
    league: str | None = None,
    league_id: str | None = None,
    sport_key: str | None = None,
    game_id: str | None = None,
    fetch_status: str = 'ok',
) -> None:
    connection.execute(
        """
        INSERT INTO props (
            player_name, team, stat_type, line,
            true_over_prob, true_under_prob, price_over, price_under,
            devig_method, shin_z, hold, league, league_id, sport_key,
            game_id, fetch_status, source, bookmaker,
            game, commence_time, captured_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_name, stat_type, source, bookmaker, line) DO UPDATE SET
            team = excluded.team,
            true_over_prob = excluded.true_over_prob,
            true_under_prob = excluded.true_under_prob,
            price_over = excluded.price_over,
            price_under = excluded.price_under,
            devig_method = excluded.devig_method,
            shin_z = excluded.shin_z,
            hold = excluded.hold,
            league = excluded.league,
            league_id = excluded.league_id,
            sport_key = excluded.sport_key,
            game_id = excluded.game_id,
            fetch_status = excluded.fetch_status,
            game = excluded.game,
            commence_time = excluded.commence_time,
            captured_at = excluded.captured_at
        """,
        (
            player_name,
            team,
            stat_type,
            line,
            true_over_prob,
            true_under_prob,
            price_over,
            price_under,
            devig_method,
            shin_z,
            hold,
            league,
            league_id,
            sport_key,
            game_id,
            fetch_status,
            source,
            bookmaker,
            game,
            commence_time,
            captured_at,
        ),
    )


def ingest_draftkings(
    json_path: Path = DK_STAGING_FILE,
    db_path: Path = DB_PATH,
    captured_at: str | None = None,
) -> int:
    if not json_path.exists():
        raise FileNotFoundError(f"Missing sharp-lines staging file: {json_path}")

    with json_path.open('r') as file:
        records = json.load(file)

    timestamp = captured_at or utc_now()
    count = 0

    init_db(db_path)
    with get_connection(db_path) as connection:
        for record in records:
            upsert_prop(
                connection,
                player_name=record['Player'],
                team=None,
                stat_type=record.get('Stat', 'player_points'),
                line=float(record['Line']),
                true_over_prob=float(record['True_Over_Prob']),
                true_under_prob=float(record['True_Under_Prob']),
                price_over=record.get('Price_Over'),
                price_under=record.get('Price_Under'),
                devig_method=record.get('Devig_Method'),
                shin_z=record.get('Shin_Z'),
                hold=record.get('Hold'),
                league=record.get('League'),
                league_id=record.get('League_Id'),
                sport_key=record.get('Sport_Key'),
                game_id=record.get('Game_Id'),
                fetch_status=record.get('Fetch_Status', 'ok'),
                source='DK',
                bookmaker=record.get('Bookmaker', 'draftkings'),
                game=record.get('Game'),
                commence_time=record.get('Commence_Time'),
                captured_at=timestamp,
            )
            count += 1
        connection.commit()

    return count


def ingest_prizepicks(
    json_path: Path = PP_STAGING_FILE,
    db_path: Path = DB_PATH,
    captured_at: str | None = None,
) -> int:
    if not json_path.exists():
        raise FileNotFoundError(f"Missing PrizePicks staging file: {json_path}")

    with json_path.open('r') as file:
        records = json.load(file)

    timestamp = captured_at or utc_now()
    count = 0

    init_db(db_path)
    with get_connection(db_path) as connection:
        for record in records:
            upsert_prop(
                connection,
                player_name=record['name'],
                team=record.get('team'),
                stat_type=record['stat_type'],
                line=float(record['line']),
                source='PP',
                bookmaker='prizepicks',
                captured_at=timestamp,
            )
            count += 1
        connection.commit()

    return count


def ingest_staging(
    db_path: Path = DB_PATH,
    dk_path: Path = DK_STAGING_FILE,
    pp_path: Path = PP_STAGING_FILE,
) -> dict[str, int]:
    init_db(db_path)
    results = {}

    if dk_path.exists():
        results['dk'] = ingest_draftkings(dk_path, db_path)
    if pp_path.exists():
        results['pp'] = ingest_prizepicks(pp_path, db_path)

    return results


def get_latest_props(
    source: str,
    stat_type: str = 'player_points',
    db_path: Path = DB_PATH,
) -> list[dict]:
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT p.*
            FROM props p
            INNER JOIN (
                SELECT player_name, bookmaker, MAX(captured_at) AS max_captured_at
                FROM props
                WHERE source = ? AND stat_type = ?
                GROUP BY player_name, bookmaker
            ) latest
                ON p.player_name = latest.player_name
               AND p.bookmaker = latest.bookmaker
               AND p.captured_at = latest.max_captured_at
            WHERE p.source = ? AND p.stat_type = ?
            ORDER BY p.player_name, p.bookmaker, p.line
            """,
            (source, stat_type, source, stat_type),
        ).fetchall()

    return [dict(row) for row in rows]


def get_sharp_ladders(
    stat_type: str = 'player_points',
    db_path: Path = DB_PATH,
) -> dict[str, dict[str, dict]]:
    """Latest sharp lines grouped as player -> bookmaker -> ladder info.

    Each bookmaker entry holds every alternate line from its latest scrape:
    {'points': [(line, p_over), ...], 'captured_at': ..., 'commence_time': ...}
    """
    rows = get_latest_props('DK', stat_type, db_path)
    ladders: dict[str, dict[str, dict]] = {}

    for row in rows:
        if row['true_over_prob'] is None:
            continue
        book_entry = ladders.setdefault(row['player_name'], {}).setdefault(
            row['bookmaker'],
            {'points': [], 'captured_at': row['captured_at'], 'commence_time': row['commence_time']},
        )
        book_entry['points'].append((row['line'], row['true_over_prob'] / 100.0))
        book_entry['captured_at'] = max(book_entry['captured_at'], row['captured_at'])

    return ladders


def log_edges(
    edges: list[dict],
    db_path: Path = DB_PATH,
    flagged_at: str | None = None,
) -> int:
    if not edges:
        return 0

    init_db(db_path)
    timestamp = flagged_at or utc_now()
    inserted = 0

    try:  # reproducibility stamp (OBJ-41); never let it block ingestion
        from engine.config import CONFIG_VERSION
    except Exception:
        CONFIG_VERSION = None

    with get_connection(db_path) as connection:
        for edge in edges:
            # Re-running the matcher must not duplicate an open play:
            # same player/stat/play/line with no result yet = already logged.
            existing = connection.execute(
                """
                SELECT 1 FROM edges
                WHERE pp_player_name = ? AND stat_type = ? AND play = ?
                  AND pp_line = ? AND result IS NULL
                LIMIT 1
                """,
                (edge['pp_player_name'], edge['stat_type'], edge['play'], edge['pp_line']),
            ).fetchone()
            if existing:
                continue
            inserted += 1
            connection.execute(
                """
                INSERT INTO edges (
                    pp_player_name, dk_player_name, team, stat_type, play,
                    pp_line, dk_line_at_flag, edge_type, dk_over_prob,
                    dk_under_prob, probability_text, win_prob, ev_percent,
                    verdict, flags, book_count, commence_time,
                    consensus_n, consensus_tag, config_version, flagged_at,
                    pp_captured_at, dk_captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge['pp_player_name'],
                    edge['dk_player_name'],
                    edge.get('team'),
                    edge['stat_type'],
                    edge['play'],
                    edge['pp_line'],
                    edge['dk_line_at_flag'],
                    edge['edge_type'],
                    edge.get('dk_over_prob'),
                    edge.get('dk_under_prob'),
                    edge.get('probability_text'),
                    edge.get('win_prob'),
                    edge.get('ev_percent'),
                    edge.get('verdict'),
                    edge.get('flags'),
                    edge.get('book_count'),
                    edge.get('commence_time'),
                    edge.get('consensus_n'),
                    edge.get('consensus_tag'),
                    CONFIG_VERSION,
                    timestamp,
                    edge.get('pp_captured_at'),
                    edge.get('dk_captured_at'),
                ),
            )
        connection.commit()

    return inserted


def get_edges(
    stat_type: str | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Logged edges, newest first. stat_type=None returns every stat."""
    init_db(db_path)

    query = "SELECT * FROM edges"
    params: tuple = ()
    if stat_type is not None:
        query += " WHERE stat_type = ?"
        params = (stat_type,)
    query += " ORDER BY flagged_at DESC, id DESC"

    with get_connection(db_path) as connection:
        rows = connection.execute(query, params).fetchall()

    return [dict(row) for row in rows]


def get_unsettled_edges(db_path: Path = DB_PATH) -> list[dict]:
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM edges
            WHERE result IS NULL
            ORDER BY flagged_at ASC, id ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]


def settle_edge(
    edge_id: int,
    result: str,
    actual_value: float,
    db_path: Path = DB_PATH,
) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE edges
            SET result = ?, actual_value = ?, settled_at = ?
            WHERE id = ?
            """,
            (result, actual_value, utc_now(), edge_id),
        )
        connection.commit()


def get_record_summary(db_path: Path = DB_PATH) -> dict:
    """Win/loss record of settled edges, overall and by verdict.

    Counts unique plays, not log rows — historical matcher runs logged the
    same play repeatedly, which silently inflated the record.
    """
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT verdict, result, win_prob
            FROM edges
            WHERE result IS NOT NULL
            GROUP BY pp_player_name, stat_type, play, pp_line, result, actual_value
            """
        ).fetchall()

    summary = {
        'settled': len(rows),
        'wins': 0,
        'losses': 0,
        'pushes': 0,
        'hit_rate': None,
        'avg_predicted_prob': None,
        'by_verdict': {},
    }

    predicted = []
    for row in rows:
        result = row['result']
        verdict = row['verdict'] or 'UNRATED'
        bucket = summary['by_verdict'].setdefault(verdict, {'wins': 0, 'losses': 0, 'pushes': 0})
        if result == 'WIN':
            summary['wins'] += 1
            bucket['wins'] += 1
        elif result == 'LOSS':
            summary['losses'] += 1
            bucket['losses'] += 1
        else:
            summary['pushes'] += 1
            bucket['pushes'] += 1
        if row['win_prob'] is not None:
            predicted.append(row['win_prob'])

    decided = summary['wins'] + summary['losses']
    if decided:
        summary['hit_rate'] = round(summary['wins'] / decided * 100, 1)
    if predicted:
        summary['avg_predicted_prob'] = round(sum(predicted) / len(predicted) * 100, 1)

    return summary


def get_latest_dk_line(
    player_name: str,
    stat_type: str = 'player_points',
    db_path: Path = DB_PATH,
    reference_line: float | None = None,
) -> dict | None:
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT p.line, p.captured_at, p.true_over_prob, p.true_under_prob
            FROM props p
            INNER JOIN (
                SELECT MAX(captured_at) AS max_captured_at
                FROM props
                WHERE source = 'DK'
                  AND bookmaker = 'draftkings'
                  AND stat_type = ?
                  AND player_name = ?
            ) latest
                ON p.captured_at = latest.max_captured_at
            WHERE p.source = 'DK'
              AND p.bookmaker = 'draftkings'
              AND p.stat_type = ?
              AND p.player_name = ?
            ORDER BY p.line
            """,
            (stat_type, player_name, stat_type, player_name),
        ).fetchall()

    if not rows:
        return None

    lines = [dict(row) for row in rows]
    if reference_line is None or len(lines) == 1:
        return lines[0]

    return min(lines, key=lambda row: abs(row['line'] - reference_line))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description='Manage arb_engine SQLite storage')
    parser.add_argument('command', choices=['init', 'ingest'], help='Database action')
    parser.add_argument('--dk-only', action='store_true', help='Ingest DraftKings staging only')
    parser.add_argument('--pp-only', action='store_true', help='Ingest PrizePicks staging only')
    args = parser.parse_args()

    if args.command == 'init':
        init_db()
        print(f"Initialized database at {DB_PATH}")
        return

    init_db()
    if args.dk_only:
        count = ingest_draftkings()
        print(f"Ingested {count} sharp props into {DB_PATH}")
        return

    if args.pp_only:
        count = ingest_prizepicks()
        print(f"Ingested {count} PrizePicks props into {DB_PATH}")
        return

    results = ingest_staging()
    if not results:
        raise SystemExit('No staging JSON files found to ingest.')

    for source, count in results.items():
        print(f"Ingested {count} {source.upper()} props into {DB_PATH}")


if __name__ == '__main__':
    main()
