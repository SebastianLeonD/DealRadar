"""Phase-2 calibration gate — pure-Python statistics (council OBJ-9/10/31).

Deterministic (fixed seed), numpy-free. Mirrors the verified Phase-2 spec §5.
"""

import math
import random

from statistics import NormalDist

from engine.calibration import (
    ScoredLeg,
    assign_strata,
    benjamini_hochberg,
    bh_adjusted,
    bootstrap_t_pvalue,
    brier,
    chi2_2_quantile,
    classify,
    clustered_brier_pvalue,
    design_effect,
    line_band,
    paired_brier_diff,
    reliability_slope,
    select_sharpest_book,
    t_crit,
    time_to_first_verdict,
)
from engine.probability import normal_p_over_push_adjusted, push_conditional


# ---- helpers ---------------------------------------------------------------
def _leg(cluster, cons, base, y, *, sport="nba", stat="player_points",
         band="mid", etype="line_discrepancy", line=20.5, lid=None):
    return ScoredLeg(
        leg_id=lid or f"{cluster}-{cons}-{y}", cluster=cluster, sport=sport,
        stat_type=stat, line_band=band, edge_type=etype, pp_line=line,
        consensus_p=cons, baseline_p=base, win_prob_raw=None, outcome_over=y,
    )


def _legs_from_d(d_by_game):
    """Build legs whose paired Brier diff equals the requested d (via outcome=1,
    baseline fixed at 0.5, consensus solved): d = (c-1)^2 - (0.5-1)^2."""
    legs = []
    for gi, ds in enumerate(d_by_game):
        for di, d in enumerate(ds):
            # (c-1)^2 = d + 0.25 -> c = 1 - sqrt(d+0.25)
            val = d + 0.25
            val = max(val, 0.0)
            c = 1.0 - math.sqrt(val)
            c = min(max(c, 0.0), 1.0)
            legs.append(_leg(f"G{gi}", c, 0.5, 1, lid=f"G{gi}-{di}"))
    return legs


# ---- probability / canonical event ----------------------------------------
def test_normal_half_line_unchanged():
    got = normal_p_over_push_adjusted(22, 7, 20.5)
    assert abs(got - (1 - NormalDist(22, 7).cdf(20.5))) < 1e-12


def test_normal_integer_centered_is_symmetric():
    # Principled convention: over=1-cdf(L+.5), under=cdf(L-.5) -> 0.5 centered.
    got = normal_p_over_push_adjusted(20, 5, 20.0)
    assert abs(got - 0.5) < 1e-9


def test_push_conditional_halfline_noop():
    assert push_conditional(0.62, 20.5, None) == 0.62


def test_paired_d_sign():
    assert paired_brier_diff(0.9, 0.4, 1) < 0   # consensus better -> negative
    assert paired_brier_diff(0.4, 0.9, 1) > 0


def test_fixed_over_equals_played_side_on_halfline():
    # UNDER leg: fixed-OVER d must equal played-side d on (1-p, 1-y).
    cons_over, base_over, y_over = 0.40, 0.42, 0
    d_fixed = paired_brier_diff(cons_over, base_over, y_over)
    d_played = paired_brier_diff(1 - cons_over, 1 - base_over, 1 - y_over)
    assert abs(d_fixed - d_played) < 1e-12


def test_brier_rejects_bool():
    for bad in (lambda: brier(True, 1), lambda: brier(0.5, True)):
        try:
            bad()
        except ValueError:
            continue
        raise AssertionError("expected ValueError on bool")


def test_brier_rejects_out_of_range_and_nan():
    for args in ((1.2, 1), (-0.1, 0), (float("nan"), 1)):
        try:
            brier(*args)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError on {args}")


# ---- bootstrap-t -----------------------------------------------------------
def _synth_d(n_games, mean, sd, legs_per=2, seed=99):
    rng = random.Random(seed)
    return [[rng.gauss(mean, sd) for _ in range(legs_per)] for _ in range(n_games)]


def test_bootstrap_rejects_real_effect():
    legs = _legs_from_d(_synth_d(60, -0.02, 0.02))
    out = clustered_brier_pvalue(legs)
    assert out["status"] == "ok" and out["p_value"] < 0.05


def test_bootstrap_not_reject_zero_effect():
    legs = _legs_from_d(_synth_d(60, 0.0, 0.02))
    out = clustered_brier_pvalue(legs)
    assert out["status"] == "ok" and out["p_value"] > 0.10


def test_bootstrap_constant_d_abstains():
    values = [-1e-9] * 440
    clusters = [f"G{i}" for i in range(220) for _ in range(2)]
    out = bootstrap_t_pvalue(values, clusters)
    assert out["status"] == "insufficient" and out["p_value"] is None


def test_bootstrap_below_cluster_floor_abstains():
    legs = _legs_from_d(_synth_d(25, -0.05, 0.02))
    out = clustered_brier_pvalue(legs)
    assert out["p_value"] is None


def test_bootstrap_single_cluster_abstains():
    values = [(-0.03) for _ in range(500)]
    clusters = ["G0"] * 500
    out = bootstrap_t_pvalue(values, clusters)
    assert out["n_clusters"] == 1 and out["p_value"] is None


def test_bootstrap_counts_games_not_legs():
    values = [0.01 * (i % 3 - 1) for i in range(10000)]
    clusters = ["G0"] * 10000
    out = bootstrap_t_pvalue(values, clusters)
    assert out["n_clusters"] == 1


def test_bootstrap_deterministic():
    legs = _legs_from_d(_synth_d(50, -0.02, 0.02))
    a = clustered_brier_pvalue(legs)["p_value"]
    b = clustered_brier_pvalue(legs)["p_value"]
    assert a == b


# ---- BH-FDR ----------------------------------------------------------------
def test_bh_canonical_table1():
    # Benjamini-Hochberg 1995, Table 1 — 15 p-values, alpha 0.05 -> k*=4.
    pvals = [0.0001, 0.0004, 0.0019, 0.0095, 0.0201, 0.0278, 0.0298, 0.0344,
             0.0459, 0.3240, 0.4262, 0.5719, 0.6528, 0.7590, 1.000]
    rejected, k_star = benjamini_hochberg(pvals, alpha=0.05)
    assert k_star == 4
    assert sum(rejected) == 4 and all(rejected[:4])


def test_bh_step_up_backfills():
    rejected, k_star = benjamini_hochberg([0.001, 0.30, 0.012, 0.013], alpha=0.05)
    assert k_star == 3
    assert rejected == [True, False, True, True]


def test_bh_excludes_none():
    rejected, k_star = benjamini_hochberg([0.001, 0.01, None, None, 0.2], alpha=0.05)
    assert rejected[2] is False and rejected[3] is False
    assert rejected[0] and rejected[1]


def test_bh_empty():
    assert benjamini_hochberg([]) == ([], 0)


def test_bh_kstar_is_reject_authority():
    # ULP boundary: rank-2 threshold (2/5)*0.05 = 0.020000...4; p=0.0200000000000000004
    pvals = [0.001, 0.0200000000000000004, 0.5, 0.6, 0.7]
    rejected, k_star = benjamini_hochberg(pvals, alpha=0.05)
    adj = bh_adjusted(pvals, alpha=0.05)
    assert k_star == 2 and rejected[1] is True
    # naive "adjusted < alpha" would NOT reject (adj[1] is not < 0.05); k* does.
    assert not (adj[1] < 0.05)


# ---- reliability slope -----------------------------------------------------
def _calibrated_legs(n_games, legs_per=2, seed=7):
    rng = random.Random(seed)
    legs = []
    for g in range(n_games):
        for j in range(legs_per):
            p = rng.uniform(0.2, 0.8)
            y = 1 if rng.random() < p else 0
            legs.append(_leg(f"G{g}", p, 0.5, y, lid=f"G{g}-{j}"))
    return legs


def test_slope_covers_one_passes():
    out = reliability_slope(_calibrated_legs(220))
    assert out["status"] == "ok" and out["slope_ok"] is True


def test_slope_excludes_one_fails():
    # Strongly miscalibrated: outcomes far more extreme than stated probs.
    rng = random.Random(3)
    legs = []
    for g in range(220):
        for j in range(4):
            p = rng.uniform(0.3, 0.7)
            true_p = 1 / (1 + math.exp(-(1.8 * math.log(p / (1 - p)))))
            y = 1 if rng.random() < true_p else 0
            legs.append(_leg(f"G{g}", p, 0.5, y, lid=f"G{g}-{j}"))
    out = reliability_slope(legs)
    assert out["status"] == "ok" and out["slope_ok"] is False


def test_slope_single_game_abstains():
    legs = [_leg("G0", 0.6, 0.5, 1, lid=f"G0-{j}") for j in range(50)]
    legs += [_leg("G0", 0.4, 0.5, 0, lid=f"G0b-{j}") for j in range(50)]
    out = reliability_slope(legs)
    assert out["slope_ok"] is None and out["n_clusters"] == 1


def test_slope_below_floor_abstains():
    legs = _calibrated_legs(2, legs_per=200)
    out = reliability_slope(legs)
    assert out["slope_ok"] is None


def test_slope_all_one_class_abstains():
    legs = [_leg(f"G{g}", 0.6, 0.5, 1) for g in range(40)]
    out = reliability_slope(legs)
    assert out["slope_ok"] is None


# ---- design effect / ESS ---------------------------------------------------
def test_n_eff_never_exceeds_n_fuzz():
    rng = random.Random(11)
    for _ in range(300):
        g = rng.randint(2, 20)
        values, clusters = [], []
        for gi in range(g):
            for _ in range(rng.randint(1, 8)):
                values.append(rng.gauss(0, 1))
                clusters.append(f"G{gi}")
        out = design_effect(values, clusters)
        assert 0.0 <= out["icc"] <= 1.0
        assert out["deff"] >= 1.0
        assert out["n_eff"] <= out["n"] + 1e-9


def test_negative_icc_clamped():
    # within-cluster variance >> between -> icc clamps to 0.
    values = [1, -1, 1, -1, 1, -1, 1, -1]
    clusters = ["A", "A", "B", "B", "C", "C", "D", "D"]
    out = design_effect(values, clusters)
    assert out["icc"] == 0.0 and out["n_eff"] <= out["n"]


# ---- strata ----------------------------------------------------------------
def test_strata_game_disjoint():
    legs = _calibrated_legs(250) + [
        _leg(f"H{g}", 0.6, 0.5, 1, stat="player_assists", band="low") for g in range(250)
    ]
    strata = assign_strata(legs)
    seen = set()
    for _, _, members in strata:
        for c in {m.cluster for m in members}:
            assert c not in seen
            seen.add(c)


def test_strata_collapse_order():
    # 250 games of player_points but spread across line bands so no single band
    # meets the floor, yet (sport,stat,edge_type) does -> graduates at level 1.
    rng = random.Random(5)
    legs = []
    for g in range(250):
        band = ["low", "mid", "high"][g % 3]
        line = {"low": 9.5, "mid": 20.5, "high": 25.0}[band]
        legs.append(_leg(f"G{g}", 0.55, 0.5, rng.randint(0, 1),
                         band=band, line=line, lid=f"G{g}"))
    strata = assign_strata(legs)
    levels = {lvl for lvl, _, _ in strata}
    # line_band collapses before edge_type: the graduating key is level 1.
    assert 1 in levels


def test_line_band_float_safe():
    assert line_band("player_points", 20.4999996) == "mid"
    assert line_band("player_points", 9.5) == "low"
    assert line_band("player_points", 25.0) == "high"


def test_binary_market_band():
    assert line_band("player_goal_scorer_anytime", 0.5) == "binary"


# ---- sharpest book ---------------------------------------------------------
def test_sharpest_default_hold_eligible():
    assert select_sharpest_book({"pinnacle": 0.6}) == ("pinnacle", 0.6)


def test_sharpest_high_hold_ineligible():
    assert select_sharpest_book({"pinnacle": 0.6}, book_holds={"pinnacle": 1.5}) is None


def test_sharpest_pinnacle_priority():
    book, p = select_sharpest_book({"draftkings": 0.55, "pinnacle": 0.58})
    assert book == "pinnacle"


def test_sharpest_not_side_signed():
    book, p = select_sharpest_book({"pinnacle": 0.40})
    assert p == 0.40  # raw P(over) < 0.5, never folded


# ---- classify --------------------------------------------------------------
def test_classify_calibrated():
    assert classify(True, True, True, -0.02) == "CALIBRATED"


def test_classify_failed_wrong_direction():
    assert classify(True, False, True, +0.02) == "FAILED"


def test_classify_failed_slope_excludes_one():
    assert classify(True, True, False, -0.02) == "FAILED"


def test_classify_pending_insufficient():
    assert classify(False, False, None, None) == "PENDING"


def test_classify_pending_favorable_not_sig():
    assert classify(True, False, True, -0.01) == "PENDING"


# ---- quantiles / determinism ----------------------------------------------
def test_chi2_and_t_quantiles():
    assert abs(chi2_2_quantile(0.95) - 5.991464547107982) < 1e-9
    assert abs(t_crit(0.975, 200) - 1.95996) / 1.95996 < 0.03


def test_time_to_first_verdict_window_denominator():
    out = time_to_first_verdict(50, ["2026-06-30"] * 50, window_days=30)
    assert abs(out["rate_per_day"] - 50 / 30) < 1e-9


def test_pure_python_no_heavy_deps():
    import engine.calibration as cal
    import_lines = [
        ln.strip() for ln in open(cal.__file__)
        if ln.strip().startswith(("import ", "from "))
    ]
    blob = "\n".join(import_lines)
    for banned in ("numpy", "scipy", "sklearn", "statsmodels"):
        assert banned not in blob
