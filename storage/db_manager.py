import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path('data/arb_engine.db')
DK_STAGING_FILE = Path('data/processed/draftkings_data.json')
PP_STAGING_FILE = Path('data/processed/live.json')
# Underdog's de-vigged board, same shape as DK — ingested as another book.
UD_STAGING_FILE = Path('data/processed/underdog_sharp.json')
# Pinnacle's de-vigged anytime-goalscorer board, same shape — a sharp book.
PINNACLE_STAGING_FILE = Path('data/processed/pinnacle_sharp.json')

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

-- Shadow-model sidecar (v2+): one prediction row per (edge, model), logged
-- beside — never inside — the edges table. v1's model_* edge columns are
-- untouched; every additional shadow model is one more model_name here.
-- Firewall: asserted_gated — rows are logged only, never gate a verdict.
CREATE TABLE IF NOT EXISTS model_predictions (
    edge_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    model_p REAL,
    model_p_side REAL,
    model_lambda REAL,
    model_credibility REAL,
    model_n_matches INTEGER,
    model_source TEXT,
    predicted_at TEXT NOT NULL,
    UNIQUE(edge_id, model_name)
);

CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    pp_player_name TEXT NOT NULL,
    dk_player_name TEXT NOT NULL,
    team TEXT,
    opponent TEXT,
    stat_type TEXT NOT NULL,
    play TEXT NOT NULL CHECK(play IN ('OVER', 'UNDER')),
    pp_line REAL NOT NULL,
    dk_line REAL,
    win_prob REAL,
    ev_percent REAL,
    verdict TEXT,
    edge_type TEXT,
    book_count INTEGER,
    commence_time TEXT,
    stake REAL,
    result TEXT,
    actual_value REAL,
    settled_at TEXT
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

CREATE INDEX IF NOT EXISTS idx_bets_created
    ON bets(created_at DESC);
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
    'best_book': 'TEXT',                    # cross-book line-shopping anchor (Pillar 3)
    'config_version': 'TEXT',
    # Venue shopping (Feature A): which app has the softer line for our side.
    'best_venue': 'TEXT',                   # 'underdog' | 'prizepicks'
    'venue_note': 'TEXT',
    # AI matchup gate (Feature B): second-opinion check on YES verdicts only.
    'ai_pick': 'TEXT',                       # 'OVER' | 'UNDER' | 'PASS'
    'ai_confidence': 'INTEGER',
    # Phase-2 settlement partition (spec §3.1).
    'settlement_status': 'TEXT',            # NULL|'SCORED'|'PUSH'|'VOID' (NO_DATA=NULL)
    'outcome_over': 'INTEGER',              # 1 over won / 0 over lost / NULL push|void
    'partial_game': 'INTEGER NOT NULL DEFAULT 0',
    'void_reason': 'TEXT',
    'first_unsettled_at': 'TEXT',
    'force_voided_at': 'TEXT',
    # Phase-2 canonical-event triple (the three probs the test reads, spec §3.3).
    'consensus_p': 'REAL',                  # un-folded P(over), push-conditional on int lines
    'consensus_push_mass': 'REAL',
    'baseline_p': 'REAL',                   # single-sharpest-book raw P(over), push-conditional
    'baseline_book': 'TEXT',
    'baseline_hold': 'REAL',
    'win_prob_raw': 'REAL',                 # asserted Normal P(side); secondary arm only
    # Clustering + stratum keys (spec §4).
    'game_id': 'TEXT',
    'game_date': 'TEXT',
    'sport': 'TEXT',
    'line_band': 'TEXT',
    'snapshot_bucket': 'TEXT',
    # Shadow prediction (council Phase-2): the ASSERTED FBref Poisson model's
    # P(over) logged beside the market number. FLAGS NOTHING — it only feeds the
    # calibration gate, which decides if/when it earns the right to flag a bet.
    'model_p': 'REAL',                      # model P(over the line), un-folded
    'model_p_side': 'REAL',                 # folded to the bet side (compare vs win_prob)
    'model_lambda': 'REAL',                 # Poisson rate the prediction rests on
    'model_credibility': 'REAL',            # 0..1 player-vs-baseline shrink weight
    'model_n_matches': 'INTEGER',           # FBref appearances behind the prior
    'model_source': 'TEXT',                 # 'fbref_poisson_prior' | NULL
    # Retroactive DNP audit (scripts/audit_dnp.py): the pre-audit result is
    # preserved here before a row gets overwritten to VOID, and NULL/already-set
    # is what makes a re-run idempotent.
    'pre_audit_result': 'TEXT',
}

BETS_MIGRATION_COLUMNS = {
    'pre_audit_result': 'TEXT',
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def _migrate(connection: sqlite3.Connection) -> None:
    for table, columns in (
        ('props', PROPS_MIGRATION_COLUMNS),
        ('edges', EDGES_MIGRATION_COLUMNS),
        ('bets', BETS_MIGRATION_COLUMNS),
    ):
        existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, ddl in columns.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    # The upsert key now includes bookmaker; replace the old unique index.
    connection.execute("DROP INDEX IF EXISTS idx_props_upsert")

    # Phase-2 idempotent backfill (spec §4.2): translate legacy WIN/LOSS/PUSH/VOID
    # 'result' rows into the new settlement partition so the calibration read is
    # non-empty post-migration. Guarded by settlement_status IS NULL so a second
    # init_db run is a no-op. consensus_p/baseline_p are NOT backfillable (the
    # push mass / sharp-book quote were never persisted) -> left NULL, correctly
    # excluded by the read's NOT-NULL predicate rather than mis-paired.
    edge_cols = {row[1] for row in connection.execute("PRAGMA table_info(edges)")}
    if 'settlement_status' in edge_cols and 'outcome_over' in edge_cols:
        connection.execute(
            "UPDATE edges SET settlement_status='SCORED', outcome_over="
            "CASE WHEN (result='WIN' AND play='OVER') OR (result='LOSS' AND play='UNDER') "
            "THEN 1 ELSE 0 END "
            "WHERE result IN ('WIN','LOSS') AND settlement_status IS NULL"
        )
        connection.execute(
            "UPDATE edges SET settlement_status='PUSH' "
            "WHERE result='PUSH' AND settlement_status IS NULL"
        )
        connection.execute(
            "UPDATE edges SET settlement_status='VOID' "
            "WHERE result='VOID' AND settlement_status IS NULL"
        )

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
        payload = json.load(file)

    # Newer scrapers write {'fetch_complete': bool, 'records': [...]} so an
    # incomplete fetch (budget truncation / per-game failure) can be threaded
    # through to the consensus tag; a bare list (legacy files, fixtures) is
    # always treated as a complete fetch.
    if isinstance(payload, dict):
        records = payload.get('records', [])
        fetch_complete = payload.get('fetch_complete', True)
        # Fetch time recorded by the scraper (pinnacle). Stamping captured_at
        # with it keeps a re-ingested stale file honestly stale, so the
        # matcher's cross-book staleness guard can drop it.
        fetched_at = payload.get('fetched_at')
    else:
        records = payload
        fetched_at = None
        fetch_complete = True

    timestamp = captured_at or fetched_at or utc_now()
    count = 0

    init_db(db_path)
    with get_connection(db_path) as connection:
        for record in records:
            fetch_status = record.get('Fetch_Status', 'ok')
            if not fetch_complete:
                fetch_status = 'budget_truncated'
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
                fetch_status=fetch_status,
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
    ud_path: Path = UD_STAGING_FILE,
    pinnacle_path: Path = PINNACLE_STAGING_FILE,
) -> dict[str, int]:
    init_db(db_path)
    results = {}

    if dk_path.exists():
        results['dk'] = ingest_draftkings(dk_path, db_path)
    if ud_path.exists():
        # Same loader/shape as DK; records carry Bookmaker='underdog'.
        results['underdog'] = ingest_draftkings(ud_path, db_path)
    if pinnacle_path.exists():
        # Same loader/shape as DK; records carry Bookmaker='pinnacle'.
        results['pinnacle'] = ingest_draftkings(pinnacle_path, db_path)
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
    from engine.name_matcher import match_player_name, normalize_name

    rows = get_latest_props('DK', stat_type, db_path)
    ladders: dict[str, dict[str, dict]] = {}
    # Books outside the Odds-API feed (Pinnacle) spell names differently
    # ('Anis Hadj-Moussa', 'Riyhad Mahrez'), so keying ladders on the raw
    # string would fork them out of consensus. Resolve each new spelling to
    # an existing ladder key via the same normalizer/fuzzy matcher used for
    # PP names; first spelling seen becomes canonical.
    canonical: dict[str, str] = {}

    for row in rows:
        if row['true_over_prob'] is None:
            continue
        norm = normalize_name(row['player_name'])
        if norm not in canonical:
            matched, _ = match_player_name(row['player_name'], list(ladders.keys()))
            canonical[norm] = matched or row['player_name']
        book_entry = ladders.setdefault(canonical[norm], {}).setdefault(
            row['bookmaker'],
            {
                'points': [], 'captured_at': row['captured_at'],
                'commence_time': row['commence_time'], 'fetch_complete': True,
            },
        )
        book_entry['points'].append((row['line'], row['true_over_prob'] / 100.0))
        book_entry['captured_at'] = max(book_entry['captured_at'], row['captured_at'])
        if row['fetch_status'] not in (None, 'ok'):
            book_entry['fetch_complete'] = False

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
                    consensus_n, consensus_tag, best_book, config_version,
                    consensus_p, consensus_push_mass, baseline_p, baseline_book,
                    baseline_hold, win_prob_raw, game_id, game_date, sport,
                    line_band, snapshot_bucket, flagged_at,
                    pp_captured_at, dk_captured_at,
                    model_p, model_p_side, model_lambda, model_credibility,
                    model_n_matches, model_source,
                    best_venue, venue_note, ai_pick, ai_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?)
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
                    edge.get('best_book'),
                    CONFIG_VERSION,
                    edge.get('consensus_p'),
                    edge.get('consensus_push_mass'),
                    edge.get('baseline_p'),
                    edge.get('baseline_book'),
                    edge.get('baseline_hold'),
                    edge.get('win_prob_raw'),
                    edge.get('game_id'),
                    edge.get('game_date'),
                    edge.get('sport'),
                    edge.get('line_band'),
                    edge.get('snapshot_bucket'),
                    timestamp,
                    edge.get('pp_captured_at'),
                    edge.get('dk_captured_at'),
                    edge.get('model_p'),
                    edge.get('model_p_side'),
                    edge.get('model_lambda'),
                    edge.get('model_credibility'),
                    edge.get('model_n_matches'),
                    edge.get('model_source'),
                    edge.get('best_venue'),
                    edge.get('venue_note'),
                    edge.get('ai_pick'),
                    edge.get('ai_confidence'),
                ),
            )
        connection.commit()

    return inserted


def record_model_predictions(
    bets: list[dict],
    db_path: Path = DB_PATH,
    model_name: str = 'glm_v2',
    field_key: str = 'glm_v2',
) -> int:
    """Attach shadow-v2 predictions to their edges in the sidecar table.

    Each bet carrying a `field_key` dict (the six model fields) is re-joined to
    its open edge row by the same dedup key log_edges uses (player/stat/play/
    line, result IS NULL) plus commence_time — log_edges doesn't return rowids,
    and the re-select is the smaller diff. The commence_time match (null-safe
    IS) pins the prediction to the same fixture: a recurring line for a
    player's NEXT match must never attach to a still-open edge from an earlier
    match, whose features could already contain that match's own stats
    (hindsight leak into the shadow Brier). INSERT OR IGNORE on
    UNIQUE(edge_id, model_name) keeps the FIRST prediction for an edge, so
    re-running the matcher against an already-open edge never overwrites the
    original number.
    """
    preds = [bet for bet in bets if isinstance(bet.get(field_key), dict)]
    if not preds:
        return 0

    init_db(db_path)
    timestamp = utc_now()
    inserted = 0
    with get_connection(db_path) as connection:
        for bet in preds:
            row = connection.execute(
                """
                SELECT id FROM edges
                WHERE pp_player_name = ? AND stat_type = ? AND play = ?
                  AND pp_line = ? AND commence_time IS ? AND result IS NULL
                ORDER BY id DESC LIMIT 1
                """,
                (bet['pp_player_name'], bet['stat_type'], bet['play'],
                 bet['pp_line'], bet.get('commence_time')),
            ).fetchone()
            if not row:
                continue
            fields = bet[field_key]
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO model_predictions (
                    edge_id, model_name, model_p, model_p_side, model_lambda,
                    model_credibility, model_n_matches, model_source, predicted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row['id'], model_name,
                    fields.get('model_p'), fields.get('model_p_side'),
                    fields.get('model_lambda'), fields.get('model_credibility'),
                    fields.get('model_n_matches'), fields.get('model_source'),
                    timestamp,
                ),
            )
            inserted += cursor.rowcount
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
    actual_value: float | None,
    db_path: Path = DB_PATH,
    *,
    settlement_status: str | None = None,
    outcome_over: int | None = None,
    void_reason: str | None = None,
    partial_game: int = 0,
) -> None:
    """Settle one edge. Writes the legacy result AND the Phase-2 settlement
    partition (settlement_status / outcome_over / void_reason / partial_game)
    so the calibration read has a well-defined SCORED pool (spec §3)."""
    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE edges
            SET result = ?, actual_value = ?, settled_at = ?,
                settlement_status = ?, outcome_over = ?,
                void_reason = ?, partial_game = ?
            WHERE id = ?
            """,
            (result, actual_value, utc_now(), settlement_status, outcome_over,
             void_reason, partial_game, edge_id),
        )
        connection.commit()


def force_void_edge(edge_id: int, void_reason: str, db_path: Path = DB_PATH) -> None:
    """Force-void an edge that's been unsettled too long (STALE_SETTLE_MAX_HOURS).

    Mirrors settle_edge's partition write but stamps force_voided_at so a
    force-void is distinguishable from a normally-graded VOID."""
    with get_connection(db_path) as connection:
        now = utc_now()
        connection.execute(
            """
            UPDATE edges
            SET result = 'VOID', settled_at = ?,
                settlement_status = 'VOID', outcome_over = NULL,
                void_reason = ?, force_voided_at = ?
            WHERE id = ?
            """,
            (now, void_reason, now, edge_id),
        )
        connection.commit()


def get_record_summary(db_path: Path = DB_PATH, since: str | None = None) -> dict:
    """Win/loss record of settled edges, overall and by verdict.

    Counts unique plays, not log rows — historical matcher runs logged the
    same play repeatedly, which silently inflated the record.

    since: optional ISO flagged_at floor (e.g. a pipeline-fix timestamp) so
    the repaired verdicts' trustworthiness can be measured on their own.
    """
    init_db(db_path)

    query = """
        SELECT verdict, result, win_prob
        FROM edges
        WHERE result IS NOT NULL
    """
    params: tuple = ()
    if since:
        query += " AND flagged_at >= ?"
        params = (since,)
    query += """
        GROUP BY pp_player_name, stat_type, play, pp_line, result, actual_value
    """

    with get_connection(db_path) as connection:
        rows = connection.execute(query, params).fetchall()

    summary = {
        'settled': len(rows),
        'wins': 0,
        'losses': 0,
        'pushes': 0,
        'voids': 0,
        'hit_rate': None,
        'avg_predicted_prob': None,
        'by_verdict': {},
    }

    predicted = []
    for row in rows:
        result = row['result']
        verdict = row['verdict'] or 'UNRATED'
        bucket = summary['by_verdict'].setdefault(
            verdict, {'wins': 0, 'losses': 0, 'pushes': 0, 'voids': 0})
        if result == 'WIN':
            summary['wins'] += 1
            bucket['wins'] += 1
        elif result == 'LOSS':
            summary['losses'] += 1
            bucket['losses'] += 1
        elif result == 'VOID':
            # A VOID is a refund, not a push — never fold it into the push count
            # or the hit-rate denominator (council OBJ-33, spec §3.6).
            summary['voids'] += 1
            bucket['voids'] += 1
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


def add_bet(bet: dict, db_path: Path = DB_PATH) -> int | None:
    """Log a bet the user actually placed. Returns the new id, or None if an
    identical open bet already exists (so double-clicks don't duplicate)."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        existing = connection.execute(
            """
            SELECT id FROM bets
            WHERE pp_player_name = ? AND stat_type = ? AND play = ?
              AND pp_line = ? AND result IS NULL
            LIMIT 1
            """,
            (bet['pp_player_name'], bet['stat_type'], bet['play'], bet['pp_line']),
        ).fetchone()
        if existing:
            return None
        cursor = connection.execute(
            """
            INSERT INTO bets (
                created_at, pp_player_name, dk_player_name, team, opponent,
                stat_type, play, pp_line, dk_line, win_prob, ev_percent,
                verdict, edge_type, book_count, commence_time, stake
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bet.get('created_at') or utc_now(),
                bet['pp_player_name'],
                bet['dk_player_name'],
                bet.get('team'),
                bet.get('opponent'),
                bet['stat_type'],
                bet['play'],
                bet['pp_line'],
                bet.get('dk_line'),
                bet.get('win_prob'),
                bet.get('ev_percent'),
                bet.get('verdict'),
                bet.get('edge_type'),
                bet.get('book_count'),
                bet.get('commence_time'),
                bet.get('stake'),
            ),
        )
        connection.commit()
        return cursor.lastrowid


def get_bets(db_path: Path = DB_PATH) -> list[dict]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM bets ORDER BY created_at DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_unsettled_bets(db_path: Path = DB_PATH) -> list[dict]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT * FROM bets WHERE result IS NULL ORDER BY created_at ASC, id ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def settle_bet(bet_id: int, result: str, actual_value: float, db_path: Path = DB_PATH) -> None:
    with get_connection(db_path) as connection:
        connection.execute(
            "UPDATE bets SET result = ?, actual_value = ?, settled_at = ? WHERE id = ?",
            (result, actual_value, utc_now(), bet_id),
        )
        connection.commit()


def delete_bet(bet_id: int, db_path: Path = DB_PATH) -> bool:
    init_db(db_path)
    with get_connection(db_path) as connection:
        cursor = connection.execute("DELETE FROM bets WHERE id = ?", (bet_id,))
        connection.commit()
        return cursor.rowcount > 0


def get_bet_record_summary(db_path: Path = DB_PATH) -> dict:
    """Record of the bets the user actually placed — overall and by verdict."""
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute("SELECT verdict, result, win_prob, stake FROM bets").fetchall()

    summary = {
        'total': len(rows),
        'settled': 0,
        'wins': 0,
        'losses': 0,
        'pushes': 0,
        'voids': 0,
        'hit_rate': None,
        'total_staked': 0.0,
        'by_verdict': {},
    }
    for row in rows:
        summary['total_staked'] += row['stake'] or 0.0
        result = row['result']
        if result is None:
            continue
        summary['settled'] += 1
        verdict = row['verdict'] or 'UNRATED'
        bucket = summary['by_verdict'].setdefault(
            verdict, {'wins': 0, 'losses': 0, 'pushes': 0, 'voids': 0}
        )
        if result == 'WIN':
            summary['wins'] += 1
            bucket['wins'] += 1
        elif result == 'LOSS':
            summary['losses'] += 1
            bucket['losses'] += 1
        elif result == 'VOID':
            # A VOID is a refund, not a push — never fold it into the push
            # count or the hit-rate denominator (mirrors get_record_summary).
            summary['voids'] += 1
            bucket['voids'] += 1
        else:
            summary['pushes'] += 1
            bucket['pushes'] += 1

    decided = summary['wins'] + summary['losses']
    if decided:
        summary['hit_rate'] = round(summary['wins'] / decided * 100, 1)
    summary['total_staked'] = round(summary['total_staked'], 2)
    return summary


def get_player_game_map(db_path: Path = DB_PATH) -> dict[str, str]:
    """player_name -> bookmaker 'Game' string (e.g. 'Japan @ Netherlands').

    Pulled from the sharp (DK) props, newest scrape wins. Used to tell the AI
    analyst who each player is up against so it can reason about the matchup.
    """
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT player_name, game
            FROM props
            WHERE source = 'DK' AND game IS NOT NULL AND game != ''
            ORDER BY captured_at ASC
            """
        ).fetchall()

    # Later (newer) rows overwrite earlier ones for the same player.
    return {row['player_name']: row['game'] for row in rows}


def get_game_commence_map(db_path: Path = DB_PATH) -> list[dict]:
    """Distinct (game, commence_time) pairs from the sharp (DK) props.

    Modeled edges (saves, fouls, etc.) have no book line, so they can't inherit
    a kickoff from a matched book prop. Instead we resolve it from the player's
    team: find the DK game whose 'Away @ Home' string names that team.
    """
    init_db(db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT game, commence_time, MAX(captured_at) AS captured_at
            FROM props
            WHERE source = 'DK' AND game IS NOT NULL AND game != ''
              AND commence_time IS NOT NULL
            GROUP BY game
            ORDER BY captured_at ASC
            """
        ).fetchall()

    return [{'game': row['game'], 'commence_time': row['commence_time']} for row in rows]


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
