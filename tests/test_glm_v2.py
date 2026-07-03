"""Shadow model v2 (GLM-lite Poisson regression) — fitter, features, NULL
semantics, leak guards, sidecar logging, scorer selector."""

import json
import math
from datetime import date

from engine.glm_model import (
    FROZEN_BETA,
    build_training_rows,
    fit_poisson_irls,
    glm_fields,
    glm_lambda,
    opponent_factor,
    prior90,
    team_rate_table,
)
from engine.shadow_score import _fetch_sidecar_rows, score
from scrapers.fbref_api import normalize_player_match_rows
from storage.db_manager import (
    get_connection,
    init_db,
    log_edges,
    record_model_predictions,
    settle_edge,
)

TODAY = date.today().isoformat()


# ---- IRLS fitter ------------------------------------------------------------
def test_irls_recovers_known_beta_on_synthetic_poisson():
    import numpy as np

    rng = np.random.default_rng(7)
    n = 8000
    true_beta = (-0.3, 0.8, 1.2)
    log_prior = rng.normal(0.0, 0.6, n)
    log_opp = rng.normal(0.0, 0.4, n)
    offset = np.log(rng.uniform(30, 90, n) / 90.0)
    lam = np.exp(offset + true_beta[0] + true_beta[1] * log_prior
                 + true_beta[2] * log_opp)
    y = rng.poisson(lam)
    X = np.column_stack([np.ones(n), log_prior, log_opp])

    beta, converged = fit_poisson_irls(X, y, offset)
    assert converged
    for est, true in zip(beta, true_beta):
        assert abs(est - true) < 0.1


def test_irls_singular_design_freezes_beta():
    # log_prior identical to log_opp column -> collinear; ridge keeps it
    # solvable, but a zero-variance + zero-count corner must not blow up.
    X = [[1.0, 0.0, 0.0]] * 5
    y = [0.0] * 5
    offset = [0.0] * 5
    beta, _ = fit_poisson_irls(X, y, offset)
    assert all(math.isfinite(b) for b in beta)


# ---- feature construction ---------------------------------------------------
def test_prior90_blend_degrades_gracefully():
    # Debutant: nothing but the baseline pseudo-game.
    rate, informative = prior90(0.0, 0.0, None, None, baseline=1.2)
    assert rate == 1.2 and informative == 0.0
    # Full club season dominates a thin WC sample; club minutes are capped.
    rate_club, informative_club = prior90(0.0, 0.0, 3.0, 3420.0, baseline=1.2)
    assert informative_club == 900.0  # cap, not 3420
    assert 2.5 < rate_club < 3.0      # pulled slightly to baseline
    # WC evidence moves the blend.
    rate_wc, _ = prior90(10.0, 180.0, None, None, baseline=1.2)
    assert rate_wc > 3.0


def _rec(player, team, opp, day, minutes, **stats):
    return {"player": player, "team": team, "opponent": opp, "date": day,
            "minutes": minutes, "stats": stats}


def test_opponent_factor_shrinks_one_game_noise_toward_one():
    records = [
        _rec("A", "X", "LeakyTeam", "2026-06-11", 90.0, player_shots=8.0),
        _rec("B", "Y", "MeanTeam", "2026-06-11", 90.0, player_shots=2.0),
        _rec("C", "LeakyTeam", "X", "2026-06-11", 90.0, player_shots=0.0),
        _rec("D", "MeanTeam", "Y", "2026-06-11", 90.0, player_shots=0.0),
    ]
    table = team_rate_table(records, "player_shots")
    leaky = opponent_factor(table, "LeakyTeam")
    mean_team = opponent_factor(table, "MeanTeam")
    assert leaky > 1.0 > mean_team
    # One game of evidence: shrunk well inside the raw (8/5=1.6, 2/5=0.4).
    assert leaky < 1.6 and mean_team > 0.4
    assert opponent_factor(table, None) == 1.0
    assert opponent_factor(table, "NeverSeen") == 1.0


def test_saves_family_flips_to_opponent_sot_production():
    # GoodAttack PRODUCES SoT; a keeper facing them should get factor > 1,
    # credited to the team itself (production), not what they concede.
    records = [
        _rec("F1", "GoodAttack", "Z", "2026-06-11", 90.0,
             player_shots_on_target=6.0),
        _rec("F2", "BluntAttack", "W", "2026-06-11", 90.0,
             player_shots_on_target=1.0),
    ]
    table = team_rate_table(records, "player_goalie_saves")
    assert opponent_factor(table, "GoodAttack") > 1.0
    assert opponent_factor(table, "BluntAttack") < 1.0


def test_training_rows_are_strictly_as_of():
    # Player's monster matchday-2 must not leak into his matchday-2 prior
    # (only matchday-1 counts), and matchday-1 rows see no WC history at all.
    records = [
        _rec("P", "X", "Y", "2026-06-11", 90.0, player_shots=1.0),
        _rec("Q", "Y", "X", "2026-06-11", 90.0, player_shots=1.0),
        _rec("P", "X", "Z", "2026-06-16", 90.0, player_shots=9.0),
        _rec("Q2", "Z", "X", "2026-06-16", 90.0, player_shots=0.0),
    ]
    club = {"P": {"per90": {"shots": 2.0}, "minutes": 900.0}}
    rows = build_training_rows(records, "player_shots", club, baseline=1.2)
    p_rows = {r["date"]: r for r in rows if r["player"] == "P"}
    assert p_rows["2026-06-11"]["wc_minutes_before"] == 0.0
    assert p_rows["2026-06-16"]["wc_stat_before"] == 1.0   # not 1+9
    assert p_rows["2026-06-16"]["wc_minutes_before"] == 90.0
    # matchday-1 opponent table is empty -> factor exactly 1.0
    assert p_rows["2026-06-11"]["opp"] == 1.0


def test_training_rows_exclude_pure_baseline_priors():
    # No club join, first WC match -> informative minutes 0 < 90 -> excluded.
    records = [_rec("Nobody", "X", "Y", "2026-06-11", 90.0, player_shots=1.0)]
    rows = build_training_rows(records, "player_shots", {}, baseline=1.2)
    assert rows == []


def test_glm_lambda_matches_closed_form():
    beta = [-0.2, 0.9, 1.1]
    lam = glm_lambda(beta, 90.0, 2.0, 1.1)
    expected = math.exp(-0.2 + 0.9 * math.log(2.0) + 1.1 * math.log(1.1))
    assert abs(lam - expected) < 1e-9


# ---- inference NULL semantics ----------------------------------------------
def _write_coefs(path, fit_through=TODAY, beta=(0.0, 1.0, 1.0)):
    path.write_text(json.dumps({
        "model_source": "fbref_glm_v2",
        "fit_through": fit_through,
        "families": {"player_shots": {"beta": list(beta), "baseline": 1.2}},
    }))
    return path


def _logs(n=3, shots=2.0, minutes=90.0):
    return [_rec("P", "X", f"Opp{i}", f"2026-06-{11 + i}", minutes,
                 player_shots=shots) for i in range(n)]


def test_glm_fields_happy_path_and_side_folding(tmp_path):
    coefs = _write_coefs(tmp_path / "coefs.json")
    logs = _logs()
    logs_by_player = {"P": logs}
    over = glm_fields("P", "player_shots", 1.5, "OVER", logs=logs,
                      logs_by_player=logs_by_player,
                      coefs_path=coefs, club_path=tmp_path / "none.json")
    under = glm_fields("P", "player_shots", 1.5, "UNDER", logs=logs,
                       logs_by_player=logs_by_player,
                       coefs_path=coefs, club_path=tmp_path / "none.json")
    assert over is not None and under is not None
    assert over["model_source"] == "fbref_glm_v2"
    assert over["model_n_matches"] == 3
    assert 0.0 < over["model_p"] < 1.0
    assert over["model_p_side"] == over["model_p"]
    assert abs(under["model_p_side"] - (1.0 - under["model_p"])) < 1e-9
    assert over["model_lambda"] > 0
    assert 0.0 < over["model_credibility"] < 1.0


def test_glm_fields_null_when_coefs_missing_or_stale(tmp_path):
    logs = _logs()
    kwargs = dict(logs=logs, logs_by_player={"P": logs},
                  club_path=tmp_path / "none.json")
    assert glm_fields("P", "player_shots", 1.5, "OVER",
                      coefs_path=tmp_path / "missing.json", **kwargs) is None
    stale = _write_coefs(tmp_path / "stale.json", fit_through="2026-01-01")
    assert glm_fields("P", "player_shots", 1.5, "OVER",
                      coefs_path=stale, **kwargs) is None


def test_glm_fields_null_when_no_logs_or_unknown_family(tmp_path):
    coefs = _write_coefs(tmp_path / "coefs.json")
    assert glm_fields("P", "player_shots", 1.5, "OVER", logs=[],
                      logs_by_player={}, coefs_path=coefs,
                      club_path=tmp_path / "none.json") is None
    logs = _logs()
    assert glm_fields("P", "player_fouls", 1.5, "OVER", logs=logs,
                      logs_by_player={"P": logs}, coefs_path=coefs,
                      club_path=tmp_path / "none.json") is None


def test_glm_fields_never_raises_on_garbage(tmp_path):
    coefs = _write_coefs(tmp_path / "coefs.json")
    broken = [{"minutes": "not-a-number", "stats": None}]
    assert glm_fields("P", "player_shots", 1.5, "OVER", logs=broken,
                      logs_by_player={"P": broken}, coefs_path=coefs,
                      club_path=tmp_path / "none.json") is None


def test_frozen_beta_degrades_to_prior_times_opponent(tmp_path):
    coefs = _write_coefs(tmp_path / "coefs.json", beta=FROZEN_BETA)
    logs = _logs(n=3, shots=2.0, minutes=90.0)
    out = glm_fields("P", "player_shots", 1.5, "OVER", logs=logs,
                     logs_by_player={"P": logs}, coefs_path=coefs,
                     club_path=tmp_path / "none.json")
    # prior90 = (6 + 1.2) / (270/90 + 1) = 1.8; opp unresolvable -> 1.0
    assert abs(out["model_lambda"] - 1.8) < 1e-6


# ---- connector re-normalization (prefix strip + game parsing) ---------------
def test_normalize_strips_soccerdata_table_prefixes_and_parses_game():
    raw = [{"player": "Heung-min Son", "team": "Korea Republic",
            "game": "2026-06-11 Korea Republic-Czechia", "min": "90",
            "performance_sh": "4", "performance_sot": "2",
            "performance_gls": "1", "performance_ast": "0",
            "performance_crs": "3", "performance_tklw": "1"}]
    recs = normalize_player_match_rows(raw)
    r = recs[0]
    assert r["date"] == "2026-06-11"
    assert r["opponent"] == "Czechia"
    assert r["stats"]["player_shots"] == 4.0
    assert r["stats"]["player_crosses"] == 3.0
    assert r["stats"]["player_tackles"] == 1.0


def test_normalize_game_parsing_handles_team_second():
    raw = [{"player": "GK", "team": "Czechia",
            "game": "2026-06-11 Korea Republic-Czechia", "min": "90",
            "shot stopping_saves": "5"}]
    r = normalize_player_match_rows(raw)[0]
    assert r["opponent"] == "Korea Republic"
    assert r["stats"]["player_goalie_saves"] == 5.0


def test_normalize_passes_through_already_normalized_cache():
    cached = [{"player": "P", "team": "X", "opponent": "Y",
               "date": "2026-06-11", "minutes": 90.0,
               "stats": {"player_shots": 3.0}}]
    r = normalize_player_match_rows(cached)[0]
    assert r["stats"]["player_shots"] == 3.0
    assert r["date"] == "2026-06-11" and r["opponent"] == "Y"


# ---- sidecar logging ---------------------------------------------------------
EDGE_BASE = {
    "dk_player_name": "Q", "play": "OVER", "pp_line": 1.5,
    "dk_line_at_flag": 1.5, "edge_type": "x", "consensus_tag": "identified",
    "game_id": "G1", "game_date": "2026-07-01", "sport": "world_cup",
    "snapshot_bucket": "b", "stat_type": "player_shots",
    "pp_player_name": "P1",
}

GLM_FIELDS = {
    "model_p": 0.61, "model_p_side": 0.61, "model_lambda": 2.1,
    "model_credibility": 0.7, "model_n_matches": 3,
    "model_source": "fbref_glm_v2",
}


def test_record_model_predictions_joins_open_edge(tmp_path):
    db = tmp_path / "sidecar.db"
    log_edges([dict(EDGE_BASE)], db_path=db)
    bet = dict(EDGE_BASE, glm_v2=dict(GLM_FIELDS))
    assert record_model_predictions([bet], db_path=db) == 1
    with get_connection(db) as conn:
        row = dict(conn.execute("SELECT * FROM model_predictions").fetchone())
    assert row["model_name"] == "glm_v2"
    assert row["model_p"] == 0.61
    assert row["model_source"] == "fbref_glm_v2"
    assert row["predicted_at"]


def test_record_model_predictions_keeps_first_prediction(tmp_path):
    db = tmp_path / "dedup.db"
    log_edges([dict(EDGE_BASE)], db_path=db)
    first = dict(EDGE_BASE, glm_v2=dict(GLM_FIELDS))
    assert record_model_predictions([first], db_path=db) == 1
    rerun = dict(EDGE_BASE, glm_v2=dict(GLM_FIELDS, model_p=0.99))
    assert record_model_predictions([rerun], db_path=db) == 0  # OR IGNORE
    with get_connection(db) as conn:
        rows = conn.execute("SELECT model_p FROM model_predictions").fetchall()
    assert len(rows) == 1 and rows[0]["model_p"] == 0.61


def test_record_model_predictions_never_joins_across_fixtures(tmp_path):
    # Leak guard: edge for match M is still open (result IS NULL) when the same
    # player/stat/play/line reappears for the NEXT match M'. The M' prediction
    # (whose features may include M's own stats) must not attach to M's edge.
    db = tmp_path / "fixture.db"
    log_edges([dict(EDGE_BASE, commence_time="2026-07-01T18:00:00Z")], db_path=db)
    later_bet = dict(EDGE_BASE, commence_time="2026-07-05T18:00:00Z",
                     glm_v2=dict(GLM_FIELDS))
    assert record_model_predictions([later_bet], db_path=db) == 0
    with get_connection(db) as conn:
        assert conn.execute("SELECT COUNT(*) c FROM model_predictions").fetchone()["c"] == 0
    # Same fixture still joins.
    same_bet = dict(EDGE_BASE, commence_time="2026-07-01T18:00:00Z",
                    glm_v2=dict(GLM_FIELDS))
    assert record_model_predictions([same_bet], db_path=db) == 1


def test_record_model_predictions_skips_unmatched_and_predictionless(tmp_path):
    db = tmp_path / "skip.db"
    init_db(db)
    orphan = dict(EDGE_BASE, glm_v2=dict(GLM_FIELDS))  # edge never logged
    no_pred = dict(EDGE_BASE, glm_v2=None)
    assert record_model_predictions([orphan, no_pred], db_path=db) == 0


# ---- shadow_score sidecar selector -------------------------------------------
def test_shadow_score_sidecar_pairs_v2_against_v1_and_market(tmp_path):
    db = tmp_path / "score.db"
    # v1 (edges.model_p) is a coin flip; v2 sidecar is spot-on; market between.
    edge = dict(EDGE_BASE, model_p=0.5, consensus_p=0.7, baseline_p=0.6)
    log_edges([edge], db_path=db)
    bet = dict(EDGE_BASE, glm_v2=dict(GLM_FIELDS, model_p=1.0))
    record_model_predictions([bet], db_path=db)
    with get_connection(db) as conn:
        eid = conn.execute("SELECT id FROM edges").fetchone()["id"]
    settle_edge(eid, "WIN", 3.0, db_path=db,
                settlement_status="SCORED", outcome_over=1)

    rows = _fetch_sidecar_rows("glm_v2", db_path=db)
    assert len(rows) == 1
    result = score(rows)
    assert result["n_model"] == 1
    assert result["model_brier_all"] == 0.0            # v2 perfect
    assert result["n_vs_v1"] == 1
    assert result["diff_vs_v1"] < 0                    # v2 out-Briers v1
    assert result["diff_vs_consensus"] < 0             # and the market
    # Unknown sidecar model -> no rows, scorer stays calm.
    assert _fetch_sidecar_rows("nope", db_path=db) == []
