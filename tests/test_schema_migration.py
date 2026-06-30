"""Phase-0 schema: raw prices persist and a pre-migration DB upgrades (OBJ-7/41)."""

import sqlite3
from pathlib import Path

from storage import db_manager
from storage.db_manager import (
    get_connection,
    init_db,
    log_edges,
    upsert_prop,
)


def test_raw_prices_and_provenance_round_trip(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    with get_connection(db) as conn:
        upsert_prop(
            conn,
            player_name="LeBron James",
            team="LAL",
            stat_type="player_points",
            line=25.5,
            source="DK",
            bookmaker="draftkings",
            captured_at="2026-06-30T00:00:00+00:00",
            true_over_prob=54.0,
            true_under_prob=46.0,
            price_over=-130,
            price_under=105,
            devig_method="shin",
            shin_z=0.02,
            hold=1.048,
            sport_key="basketball_nba",
        )
        conn.commit()
        row = conn.execute(
            "SELECT price_over, price_under, devig_method, shin_z, hold, "
            "sport_key, fetch_status FROM props"
        ).fetchone()
    assert row["price_over"] == -130
    assert row["price_under"] == 105
    assert row["devig_method"] == "shin"
    assert abs(row["shin_z"] - 0.02) < 1e-9
    assert row["sport_key"] == "basketball_nba"
    assert row["fetch_status"] == "ok"  # default


def test_config_version_stamped_on_edges(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    log_edges(
        [{
            "pp_player_name": "Stephen Curry",
            "dk_player_name": "Stephen Curry",
            "stat_type": "player_points",
            "play": "OVER",
            "pp_line": 27.5,
            "dk_line_at_flag": 28.5,
            "edge_type": "Line Discrepancy",
            "win_prob": 0.6,
            "consensus_n": 3,
            "consensus_tag": "identified",
        }],
        db_path=db,
    )
    from engine.config import CONFIG_VERSION
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT config_version, consensus_n, consensus_tag FROM edges"
        ).fetchone()
    assert row["config_version"] == CONFIG_VERSION
    assert row["consensus_n"] == 3
    assert row["consensus_tag"] == "identified"


def test_pre_migration_db_upgrades(tmp_path):
    # Simulate an OLD database that predates the raw-price columns.
    db = tmp_path / "old.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE props (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL, team TEXT, stat_type TEXT NOT NULL,
                line REAL NOT NULL, true_over_prob REAL, true_under_prob REAL,
                source TEXT NOT NULL, bookmaker TEXT NOT NULL DEFAULT 'draftkings',
                game TEXT, captured_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO props (player_name, stat_type, line, source, captured_at) "
            "VALUES ('Old Player', 'player_points', 20.5, 'DK', '2026-01-01T00:00:00+00:00')"
        )
        conn.commit()

    init_db(db)  # should ALTER in the new columns without dropping the old row
    with get_connection(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(props)")}
        assert {"price_over", "price_under", "devig_method", "sport_key",
                "fetch_status"} <= cols
        count = conn.execute("SELECT COUNT(*) FROM props").fetchone()[0]
    assert count == 1  # the historical row survived the migration
