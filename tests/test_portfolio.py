"""Correlation-aware slip EV/variance/Kelly + slip construction (OBJ-12/35/39)."""

import math

from engine.correlation import build_prior_corr, cholesky, correlated_normals
from engine.payout_table import power_multiplier
from engine.portfolio import construct_slips, simulate_slip


# ---- correlation primitives ------------------------------------------------
def test_prior_corr_structure():
    corr = build_prior_corr(["G1", "G1", "G2"], rho0=0.2)
    assert corr[0][0] == 1.0 and corr[1][1] == 1.0
    assert corr[0][1] == 0.2 and corr[1][0] == 0.2   # same game
    assert corr[0][2] == 0.0 and corr[1][2] == 0.0   # different game


def test_prior_corr_null_game_is_independent():
    corr = build_prior_corr([None, None], rho0=0.3)
    assert corr[0][1] == 0.0   # null game_ids never correlate


def test_cholesky_reconstructs_matrix():
    m = [[1.0, 0.3, 0.0], [0.3, 1.0, 0.0], [0.0, 0.0, 1.0]]
    L = cholesky(m)
    # L @ L^T == m
    n = len(m)
    for i in range(n):
        for j in range(n):
            val = sum(L[i][k] * L[j][k] for k in range(n))
            assert abs(val - m[i][j]) < 1e-12


def test_cholesky_rejects_non_psd():
    bad = [[1.0, 2.0], [2.0, 1.0]]  # correlation 2 is invalid -> not PSD
    try:
        cholesky(bad)
    except ValueError:
        return
    raise AssertionError("expected ValueError on non-PSD matrix")


def test_correlated_normals_shape():
    L = cholesky(build_prior_corr(["G1", "G1"], 0.4))
    out = correlated_normals(L, [1.0, 0.0])
    assert len(out) == 2


# ---- simulation: independence matches closed form --------------------------
def test_power_ev_matches_independent_closed_form():
    # distinct games -> independent; POWER EV = M * prod(p) - 1.
    probs = [0.6, 0.6]
    sim = simulate_slip(probs, ["G1", "G2"], "power", n_sims=40000, seed=1)
    expected = power_multiplier(2) * 0.6 * 0.6 - 1.0
    assert abs(sim["ev_per_dollar"] - expected) < 0.02


def test_p_all_hit_matches_independent():
    sim = simulate_slip([0.5, 0.5, 0.5], ["A", "B", "C"], "power", n_sims=40000, seed=2)
    assert abs(sim["p_all_hit"] - 0.125) < 0.01


def test_deterministic_under_seed():
    a = simulate_slip([0.6, 0.55], ["G1", "G1"], "flex", n_sims=5000, seed=7)
    b = simulate_slip([0.6, 0.55], ["G1", "G1"], "flex", n_sims=5000, seed=7)
    assert a["ev_per_dollar"] == b["ev_per_dollar"]
    assert a["p_all_hit"] == b["p_all_hit"]


# ---- correlation effects (the council's whole point) -----------------------
def test_positive_correlation_raises_all_hit_probability():
    indep = simulate_slip([0.6, 0.6], ["G1", "G2"], "power", n_sims=40000, seed=3)
    corr = simulate_slip([0.6, 0.6], ["G1", "G1"], "power", rho0=0.5,
                         n_sims=40000, seed=3)
    # same-direction same-game correlation lifts the all-hit probability
    assert corr["p_all_hit"] > indep["p_all_hit"] + 0.01


def test_flex_correlation_is_non_monotone():
    # For a 6-leg FLEX, positive correlation HELPS the 6/6 tier but the partial
    # tiers (5/6, 4/6) shift — so correlated FLEX EV != independent FLEX EV and
    # cannot be a per-leg-separable number.
    probs = [0.62] * 6
    indep = simulate_slip(probs, [f"G{i}" for i in range(6)], "flex",
                          n_sims=40000, seed=4)
    corr = simulate_slip(probs, ["G0"] * 6, "flex", rho0=0.5, n_sims=40000, seed=4)
    assert corr["hit_distribution"][6] > indep["hit_distribution"][6]   # all-hit up
    assert abs(corr["ev_per_dollar"] - indep["ev_per_dollar"]) > 0.01   # materially different


# ---- Kelly -----------------------------------------------------------------
def test_kelly_zero_when_no_edge():
    # 2-pick power at p=0.5 each: EV = 3*0.25 - 1 = -0.25 < 0 -> no stake.
    sim = simulate_slip([0.5, 0.5], ["G1", "G2"], "power", n_sims=20000, seed=5)
    assert sim["ev_per_dollar"] < 0
    assert sim["kelly_pct"] == 0.0


def test_kelly_positive_when_edge():
    sim = simulate_slip([0.7, 0.7], ["G1", "G2"], "power", n_sims=20000, seed=6)
    assert sim["ev_per_dollar"] > 0
    assert sim["kelly_pct"] > 0.0


# ---- slip construction -----------------------------------------------------
def _picks(probs):
    return [{"player": f"P{i}", "game_id": f"G{i}", "win_prob": p}
            for i, p in enumerate(probs)]


def test_construct_slips_ranks_and_caps_count():
    out = construct_slips(_picks([0.72, 0.70, 0.68, 0.66]),
                          max_slips=2, n_sims=8000, seed=8)
    assert len(out) <= 2
    if len(out) == 2:
        assert out[0]["ev_per_dollar"] >= out[1]["ev_per_dollar"]


def test_construct_slips_variance_cap_excludes_volatile():
    picks = _picks([0.7, 0.7, 0.7, 0.7])
    loose = construct_slips(picks, var_cap=1e9, n_sims=6000, seed=9, max_slips=10)
    tight = construct_slips(picks, var_cap=2.0, n_sims=6000, seed=9, max_slips=10)
    assert len(tight) <= len(loose)
    assert all(s["variance"] <= 2.0 for s in tight)


def test_construct_slips_empty_when_no_positive_ev():
    out = construct_slips(_picks([0.5, 0.5]), n_sims=6000, seed=10)
    assert out == []
