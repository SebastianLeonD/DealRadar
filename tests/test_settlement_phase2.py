"""Phase-2 settlement partition + schema backfill + end-to-end DB calibration."""

import math
import random
import sqlite3

from engine.settlement import classify_settlement
from engine.calibration import gather_scored_legs, run_calibration
from storage.db_manager import get_connection, init_db, log_edges, settle_edge


# ---- settlement partition (spec §3) ----------------------------------------
def test_status_outcome_invariant():
    for play, line, actual in [("OVER", 20.5, 25), ("UNDER", 20.5, 18),
                               ("OVER", 20.5, 15), ("UNDER", 20.5, 30)]:
        part = classify_settlement(play, line, actual)
        assert part["status"] == "SCORED"
        assert part["outcome_over"] is not None
        # fixed-OVER, side-agnostic
        assert part["outcome_over"] == (1 if actual > line else 0)


def test_push_any_parity():
    for line in (20.0, 20.5):
        part = classify_settlement("OVER", line, line)
        assert part["status"] == "PUSH" and part["outcome_over"] is None


def test_minutes_floor_strict():
    # minutes == floor is NOT voided (strict <)
    assert classify_settlement("OVER", 20.5, 25, minutes=0.0, min_minutes=0.0)["status"] == "SCORED"
    assert classify_settlement("OVER", 20.5, 25, minutes=0.0, min_minutes=0.5)["void_reason"] == "below_minutes_threshold"
    # minutes None falls through to scoring
    assert classify_settlement("OVER", 20.5, 25, minutes=None, min_minutes=0.5)["status"] == "SCORED"


def test_partial_game_voided_but_flagged():
    # 8 minutes, partial floor 12, UNDER, stat below line would be a WIN — but
    # participation gate precedes O/U, so it is VOID(partial), not WIN.
    part = classify_settlement("UNDER", 20.5, 5, minutes=8.0, min_minutes=0.0, partial_floor=12.0)
    assert part["status"] == "VOID" and part["void_reason"] == "partial_game"
    assert part["partial_game"] == 1


def test_no_data_is_null_status():
    part = classify_settlement("OVER", 20.5, None)
    assert part["status"] is None and part["outcome_over"] is None


def test_finiteness_asserts():
    for bad in (float("nan"), float("inf")):
        try:
            classify_settlement("OVER", 20.5, bad)
        except AssertionError:
            continue
        raise AssertionError("expected AssertionError on non-finite actual")


# ---- schema backfill (spec §4.2) -------------------------------------------
def test_legacy_result_backfilled(tmp_path):
    db = tmp_path / "legacy.db"
    init_db(db)
    log_edges([
        {"pp_player_name": "A", "dk_player_name": "A", "stat_type": "player_points",
         "play": "OVER", "pp_line": 20.5, "dk_line_at_flag": 21.5, "edge_type": "x"},
    ], db_path=db)
    with get_connection(db) as conn:
        eid = conn.execute("SELECT id FROM edges").fetchone()["id"]
        # simulate an OLD settle that only wrote result (no partition)
        conn.execute("UPDATE edges SET result='WIN' WHERE id=?", (eid,))
        conn.commit()
    init_db(db)  # re-migrate -> backfill
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT settlement_status, outcome_over FROM edges").fetchone()
    assert row["settlement_status"] == "SCORED"
    assert row["outcome_over"] == 1  # WIN on OVER -> over won


def test_new_phase2_columns_present(tmp_path):
    db = tmp_path / "s.db"
    init_db(db)
    with get_connection(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(edges)")}
    assert {"settlement_status", "outcome_over", "consensus_p", "baseline_p",
            "game_id", "sport", "line_band", "snapshot_bucket"} <= cols


# ---- end-to-end: settled edges -> run_calibration --------------------------
def _seed_calibratable_db(db, n_games=240, seed=42):
    """Seed many settled, identified games where consensus genuinely beats the
    sharp-book baseline, so the gate should be able to fire."""
    init_db(db)
    rng = random.Random(seed)
    edges = []
    for g in range(n_games):
        date = f"2026-06-{(g % 28) + 1:02d}"
        for j in range(2):
            true_p = rng.uniform(0.45, 0.75)
            y_over = 1 if rng.random() < true_p else 0
            # consensus close to truth; baseline noisier (worse Brier)
            cons = min(0.99, max(0.01, true_p + rng.gauss(0, 0.03)))
            base = min(0.99, max(0.01, true_p + rng.gauss(0, 0.12)))
            edges.append({
                "pp_player_name": f"P{g}_{j}", "dk_player_name": f"P{g}_{j}",
                "stat_type": "player_points", "play": "OVER", "pp_line": 20.5,
                "dk_line_at_flag": 20.5, "edge_type": "line_discrepancy",
                "consensus_tag": "identified", "consensus_n": 3,
                "consensus_p": cons, "baseline_p": base, "win_prob_raw": cons,
                "game_id": f"G{g}", "game_date": date, "sport": "nba",
                "line_band": "mid", "snapshot_bucket": f"{date}T00:00:00+00:00",
                "_y": y_over,
            })
    n = log_edges(edges, db_path=db)
    # settle each as SCORED with the seeded outcome
    with get_connection(db) as conn:
        rows = conn.execute("SELECT id, pp_player_name FROM edges").fetchall()
    by_name = {e["pp_player_name"]: e["_y"] for e in edges}
    for row in rows:
        y = by_name[row["pp_player_name"]]
        settle_edge(row["id"], "WIN" if y else "LOSS", 25.0 if y else 15.0,
                    db_path=db, settlement_status="SCORED", outcome_over=y)
    return n


def test_end_to_end_calibration_runs(tmp_path):
    db = tmp_path / "cal.db"
    _seed_calibratable_db(db, n_games=240)
    with get_connection(db) as conn:
        legs, diag = gather_scored_legs(conn)
        result = run_calibration(conn)
    assert diag["kept"] == 480           # 240 games x 2 legs, all SCORED+identified
    assert len(legs) == 480
    assert result["strata"], "expected at least one stratum"
    top = result["strata"][0]
    assert top.n_independent_games == 240
    # the consensus genuinely beats baseline -> the Brier point estimate is negative
    assert top.point_mean_d is not None and top.point_mean_d < 0


def test_unit_guard_rejects_percent(tmp_path):
    db = tmp_path / "pct.db"
    init_db(db)
    log_edges([{
        "pp_player_name": "Q", "dk_player_name": "Q", "stat_type": "player_points",
        "play": "OVER", "pp_line": 20.5, "dk_line_at_flag": 20.5, "edge_type": "x",
        "consensus_tag": "identified", "consensus_p": 55.0, "baseline_p": 50.0,
        "game_id": "G1", "game_date": "2026-06-01", "sport": "nba",
        "snapshot_bucket": "b",
    }], db_path=db)
    with get_connection(db) as conn:
        cid = conn.execute("SELECT id FROM edges").fetchone()["id"]
        settle_edge(cid, "WIN", 25.0, db_path=db,
                    settlement_status="SCORED", outcome_over=1)
        try:
            gather_scored_legs(conn)
        except ValueError:
            return
    raise AssertionError("expected ValueError on percent-scale consensus_p")


def test_read_query_dedups(tmp_path):
    db = tmp_path / "dedup.db"
    init_db(db)
    base = {
        "pp_player_name": "Dup", "dk_player_name": "Dup", "stat_type": "player_points",
        "play": "OVER", "pp_line": 20.5, "dk_line_at_flag": 20.5, "edge_type": "x",
        "consensus_tag": "identified", "consensus_p": 0.6, "baseline_p": 0.5,
        "game_id": "G1", "game_date": "2026-06-01", "sport": "nba",
        "snapshot_bucket": "2026-06-01T00:00:00+00:00",
    }
    # three identical log rows (same dedup grain) settled to SCORED
    with get_connection(db) as conn:
        for _ in range(3):
            conn.execute(
                "INSERT INTO edges (pp_player_name, dk_player_name, stat_type, play, "
                "pp_line, dk_line_at_flag, edge_type, consensus_tag, consensus_p, "
                "baseline_p, game_id, game_date, sport, snapshot_bucket, "
                "settlement_status, outcome_over, config_version, flagged_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("Dup", "Dup", "player_points", "OVER", 20.5, 20.5, "x", "identified",
                 0.6, 0.5, "G1", "2026-06-01", "nba", "2026-06-01T00:00:00+00:00",
                 "SCORED", 1, "v", "2026-06-01T00:00:00+00:00"))
        conn.commit()
        legs, _ = gather_scored_legs(conn)
    assert len(legs) == 1  # collapsed to one ScoredLeg
