"""Stale unsettled edges (past STALE_SETTLE_MAX_HOURS) must get force-voided
by settle_edges(), while recent unsettled edges are left untouched."""

import functools
from datetime import datetime, timedelta, timezone

import engine.settlement as settlement
from engine.config import STALE_SETTLE_MAX_HOURS
from storage.db_manager import force_void_edge, get_connection, get_unsettled_edges, init_db, log_edges


def _iso(dt):
    return dt.isoformat()


def test_stale_unsettled_edge_force_voided(tmp_path, monkeypatch):
    db = tmp_path / "stale.db"
    init_db(db)
    monkeypatch.setattr(settlement, "get_unsettled_edges",
                         functools.partial(get_unsettled_edges, db_path=db))
    monkeypatch.setattr(settlement, "force_void_edge",
                         functools.partial(force_void_edge, db_path=db))

    now = datetime.now(timezone.utc)
    stale_commence = _iso(now - timedelta(hours=STALE_SETTLE_MAX_HOURS + 10))
    recent_commence = _iso(now - timedelta(hours=1))

    # Unknown stat_type so resolve_actual short-circuits to 'unknown' status
    # (no sport config match) and never hits the network during settlement.
    log_edges([
        {"pp_player_name": "Stale Player", "dk_player_name": "Stale Player",
         "stat_type": "player_points_no_box_score", "play": "OVER", "pp_line": 20.5,
         "dk_line_at_flag": 20.5, "edge_type": "x", "commence_time": stale_commence},
        {"pp_player_name": "Recent Player", "dk_player_name": "Recent Player",
         "stat_type": "player_points_no_box_score", "play": "OVER", "pp_line": 20.5,
         "dk_line_at_flag": 20.5, "edge_type": "x", "commence_time": recent_commence},
    ], db_path=db)

    settlement.settle_edges()

    with get_connection(db) as conn:
        rows = {
            row["pp_player_name"]: dict(row)
            for row in conn.execute("SELECT * FROM edges")
        }

    stale_row = rows["Stale Player"]
    assert stale_row["settlement_status"] == "VOID"
    assert stale_row["void_reason"] == "stale_unsettled"
    assert stale_row["result"] == "VOID"
    assert stale_row["force_voided_at"] is not None

    recent_row = rows["Recent Player"]
    assert recent_row["result"] is None
    assert recent_row["force_voided_at"] is None


def test_stale_edge_with_unmatched_box_score_gets_no_name_match_reason(tmp_path, monkeypatch):
    """A box score WAS fetched (non-empty) but the player's name never
    matched anyone in it — that's a name-matcher gap (fixable with an
    alias), not a genuine 'no data ever showed up' case, so it must not be
    silently swallowed under 'stale_unsettled'."""
    db = tmp_path / "namematch.db"
    init_db(db)
    monkeypatch.setattr(settlement, "get_unsettled_edges",
                         functools.partial(get_unsettled_edges, db_path=db))
    monkeypatch.setattr(settlement, "force_void_edge",
                         functools.partial(force_void_edge, db_path=db))
    # Non-empty box score, but no entry for this edge's player at all.
    monkeypatch.setattr(
        settlement, "fetch_stats_for_date",
        lambda *a, **kw: {"Totally Different Player": {"totalShots": 2.0, "appearances": 1.0}},
    )

    stale_commence = _iso(datetime.now(timezone.utc) - timedelta(hours=STALE_SETTLE_MAX_HOURS + 10))
    log_edges([
        {"pp_player_name": "Ghost Player", "dk_player_name": "Ghost Player",
         "stat_type": "player_shots", "play": "OVER", "pp_line": 1.5,
         "dk_line_at_flag": 1.5, "edge_type": "x", "commence_time": stale_commence},
    ], db_path=db)

    settlement.settle_edges()

    with get_connection(db) as conn:
        row = dict(conn.execute(
            "SELECT * FROM edges WHERE pp_player_name='Ghost Player'"
        ).fetchone())

    assert row["result"] == "VOID"
    assert row["void_reason"] == "no_name_match"
