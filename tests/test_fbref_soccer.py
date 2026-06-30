"""FBref connector + rate prior + asserted soccer model."""

import math

from engine.probability import poisson_p_over_push_adjusted
from engine.rate_prior import (
    FALLBACK_BASELINES,
    minutes_weighted_rate,
    rate_prior,
    shrunk_rate,
)
from engine.soccer_model import expected_lambda, model_p_over, model_prediction
from scrapers.fbref_api import (
    fetch_player_match_stats,
    last_n_player_logs,
    normalize_player_match_rows,
)


# ---- connector normalization -----------------------------------------------
def test_normalize_maps_fbref_columns_to_canonical():
    raw = [{"player": "Bukayo Saka", "team": "England", "opponent": "Wales",
            "date": "2026-06-20", "Min": "90", "Sh": "5", "SoT": "2",
            "Gls": "1", "Ast": "0"}]
    recs = normalize_player_match_rows(raw)
    assert len(recs) == 1
    r = recs[0]
    assert r["player"] == "Bukayo Saka" and r["minutes"] == 90.0
    assert r["stats"]["player_shots"] == 5.0
    assert r["stats"]["player_shots_on_target"] == 2.0
    assert r["stats"]["player_goals"] == 1.0


def test_normalize_drops_dnp_and_nan():
    raw = [
        {"player": "Sub Guy", "Min": "", "Sh": "0"},       # unused sub
        {"player": "", "Min": "90", "Sh": "3"},            # no name
        {"player": "Real", "Min": "45", "Sh": float("nan")},  # NaN stat dropped
    ]
    recs = normalize_player_match_rows(raw)
    assert len(recs) == 1
    assert recs[0]["player"] == "Real"
    assert "player_shots" not in recs[0]["stats"]  # NaN was skipped


def test_last_n_orders_by_date_desc_and_limits():
    raw = [
        {"player": "P", "date": "2026-06-10", "Min": "90", "Sh": "1"},
        {"player": "P", "date": "2026-06-20", "Min": "90", "Sh": "4"},
        {"player": "P", "date": "2026-06-15", "Min": "90", "Sh": "2"},
        {"player": "Q", "date": "2026-06-15", "Min": "90", "Sh": "9"},
    ]
    recs = normalize_player_match_rows(raw)
    logs = last_n_player_logs(recs, players=["P"], n=2)
    assert list(logs) == ["P"]
    assert [r["date"] for r in logs["P"]] == ["2026-06-20", "2026-06-15"]  # newest first


def test_fetch_uses_injected_fetcher():
    def fake_fetch(season, league, stat_type):
        assert league == "INT-World Cup"
        return [{"player": "X", "Min": "90", "Sh": "3", "SoT": "1"}]
    recs = fetch_player_match_stats("2026", fetch_fn=fake_fetch)
    assert recs[0]["stats"]["player_shots"] == 3.0


# ---- rate prior ------------------------------------------------------------
def test_minutes_weighted_rate_basic():
    logs = [
        {"minutes": 90, "stats": {"player_shots": 4}},
        {"minutes": 45, "stats": {"player_shots": 2}},   # same per-90 rate
    ]
    rate, mins = minutes_weighted_rate(logs, "player_shots")
    assert mins == 135.0
    assert abs(rate - 4.0) < 1e-9   # 6 shots / 135 min * 90 = 4.0


def test_minutes_weighted_cameo_counts_less():
    # one 90' game at 6 shots, one 10' cameo at 1 shot -> weighted toward the 90'
    logs = [
        {"minutes": 90, "stats": {"player_shots": 6}},
        {"minutes": 10, "stats": {"player_shots": 1}},
    ]
    rate, mins = minutes_weighted_rate(logs, "player_shots")
    # 7 shots / 100 min * 90 = 6.3, much closer to 6 than to the cameo's 9/90
    assert 6.0 < rate < 6.6


def test_shrunk_rate_thin_sample_pulled_to_baseline():
    thin = shrunk_rate(5.0, 30.0, baseline_rate=1.2)     # only 30 min observed
    fat = shrunk_rate(5.0, 2000.0, baseline_rate=1.2)    # lots of minutes
    assert thin["rate"] < fat["rate"]                    # thin shrinks harder
    assert abs(fat["rate"] - 5.0) < 0.6                  # fat ~ player rate
    assert thin["weight"] < fat["weight"]


def test_shrunk_rate_no_data_is_baseline():
    out = shrunk_rate(None, 0.0, baseline_rate=1.2)
    assert out["rate"] == 1.2 and out["weight"] == 0.0


def test_rate_prior_end_to_end():
    logs = [
        {"minutes": 90, "stats": {"player_shots": 4}},
        {"minutes": 90, "stats": {"player_shots": 5}},
        {"minutes": 90, "stats": {"player_shots": 3}},
    ]
    prior = rate_prior(logs, "player_shots")
    assert prior["n_matches"] == 3
    assert prior["total_minutes"] == 270.0
    assert prior["avg_minutes"] == 90.0
    assert 0 < prior["weight"] < 1
    # shrunk between the player's ~4/90 and the fallback baseline
    assert FALLBACK_BASELINES["player_shots"] < prior["rate"] < 4.0


def test_rate_prior_unknown_player_is_baseline():
    prior = rate_prior([], "player_shots_on_target")
    assert prior["rate"] == FALLBACK_BASELINES["player_shots_on_target"]
    assert prior["weight"] == 0.0


# ---- soccer model ----------------------------------------------------------
def test_expected_lambda_scales_with_minutes():
    assert abs(expected_lambda(4.0, 90) - 4.0) < 1e-9
    assert abs(expected_lambda(4.0, 45) - 2.0) < 1e-9
    assert expected_lambda(4.0, 0) == 0.0


def test_model_p_over_matches_poisson():
    p = model_p_over(4.0, 90, 2.5)
    assert abs(p - poisson_p_over_push_adjusted(4.0, 2.5)) < 1e-12


def test_model_p_over_monotonic_in_line():
    # higher line -> lower P(over)
    assert model_p_over(4.0, 90, 1.5) > model_p_over(4.0, 90, 3.5)


def test_model_prediction_stamps_asserted_provenance():
    logs = [{"minutes": 90, "stats": {"player_shots": 4}} for _ in range(5)]
    pred = model_prediction(logs, "player_shots", 2.5)
    assert pred["sigma_source"] == "fbref_poisson_prior"
    assert pred["firewall_side"] == "asserted_gated"
    assert 0.0 < pred["p_over"] < 1.0
    assert abs(pred["p_over"] + pred["p_under"] - 1.0) < 1e-9


def test_model_prediction_confirmed_bench_collapses_minutes():
    logs = [{"minutes": 90, "stats": {"player_shots": 5}} for _ in range(6)]
    starter = model_prediction(logs, "player_shots", 2.5, starts=True)
    benched = model_prediction(logs, "player_shots", 2.5, starts=False)
    assert benched["expected_minutes"] <= 20.0
    assert benched["p_over"] < starter["p_over"]   # fewer minutes -> lower over
