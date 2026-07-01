"""Shadow-model Brier scorer — synthetic-DB tests (stdlib only)."""

from storage.db_manager import get_connection, init_db, log_edges, settle_edge
from engine.shadow_score import _fetch_rows, score

BASE = {
    "dk_player_name": "Q", "play": "OVER", "pp_line": 20.5,
    "dk_line_at_flag": 20.5, "edge_type": "x", "consensus_tag": "identified",
    "game_id": "G1", "game_date": "2026-06-01", "sport": "nba",
    "snapshot_bucket": "b",
}


def _seed(db, rows):
    """rows: list of dicts with model_p, consensus_p, baseline_p, outcome_over,
    model_credibility, stat_type overrides."""
    init_db(db)
    edges = []
    for i, r in enumerate(rows):
        edge = dict(BASE)
        edge["pp_player_name"] = f"P{i}"
        edge["stat_type"] = r.get("stat_type", "player_points")
        edge["model_p"] = r["model_p"]
        edge["consensus_p"] = r.get("consensus_p")
        edge["baseline_p"] = r.get("baseline_p")
        edge["model_credibility"] = r.get("model_credibility")
        edges.append(edge)
    log_edges(edges, db_path=db)

    with get_connection(db) as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM edges ORDER BY id")]
    for eid, r in zip(ids, rows):
        settle_edge(
            eid, "WIN" if r["outcome_over"] else "LOSS", 0.0, db_path=db,
            settlement_status="SCORED", outcome_over=r["outcome_over"],
        )


def test_perfect_model_near_zero_brier(tmp_path):
    db = tmp_path / "perfect.db"
    rows = [{"model_p": 1.0, "outcome_over": 1}, {"model_p": 0.0, "outcome_over": 0}] * 5
    _seed(db, rows)
    result = score(_fetch_rows(db))
    assert result["n_model"] == 10
    assert result["model_brier_all"] == 0.0


def test_coinflip_model_quarter_brier(tmp_path):
    db = tmp_path / "coinflip.db"
    rows = [{"model_p": 0.5, "outcome_over": 1}, {"model_p": 0.5, "outcome_over": 0}] * 5
    _seed(db, rows)
    result = score(_fetch_rows(db))
    assert abs(result["model_brier_all"] - 0.25) < 1e-9


def test_paired_diff_sign_model_better(tmp_path):
    db = tmp_path / "paired.db"
    # model is spot-on (p=1 for outcome=1), consensus is way off (p=0.2).
    rows = [
        {"model_p": 1.0, "consensus_p": 0.2, "baseline_p": 0.2, "outcome_over": 1}
        for _ in range(6)
    ]
    _seed(db, rows)
    result = score(_fetch_rows(db))
    assert result["n_paired"] == 6
    assert result["diff_vs_consensus"] < 0
    assert result["diff_vs_baseline"] < 0


def test_paired_diff_sign_market_better(tmp_path):
    db = tmp_path / "paired_bad.db"
    # model is way off (p=0.2 for outcome=1), consensus is spot-on (p=1.0).
    rows = [
        {"model_p": 0.2, "consensus_p": 1.0, "baseline_p": 1.0, "outcome_over": 1}
        for _ in range(6)
    ]
    _seed(db, rows)
    result = score(_fetch_rows(db))
    assert result["diff_vs_consensus"] > 0
    assert result["diff_vs_baseline"] > 0


def test_stat_type_below_min_n_excluded(tmp_path):
    db = tmp_path / "stats.db"
    rows = (
        [{"model_p": 0.6, "outcome_over": 1, "stat_type": "player_points"} for _ in range(6)]
        + [{"model_p": 0.6, "outcome_over": 1, "stat_type": "player_assists"} for _ in range(3)]
    )
    _seed(db, rows)
    result = score(_fetch_rows(db))
    assert "player_points" in result["by_stat"]
    assert "player_assists" not in result["by_stat"]
    assert result["by_stat"]["player_points"]["n"] == 6


def test_credibility_bucket_below_min_n_excluded(tmp_path):
    db = tmp_path / "cred.db"
    rows = (
        [{"model_p": 0.6, "outcome_over": 1, "model_credibility": 0.1} for _ in range(6)]
        + [{"model_p": 0.6, "outcome_over": 1, "model_credibility": 0.9} for _ in range(2)]
    )
    _seed(db, rows)
    result = score(_fetch_rows(db))
    assert "<0.3" in result["by_credibility"]
    assert ">0.5" not in result["by_credibility"]
