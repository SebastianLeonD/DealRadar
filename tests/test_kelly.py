import pytest

from engine.probability import _slip_outcomes, best_slips, kelly_fraction


def test_kelly_zero_without_edge():
    assert kelly_fraction([0.5, 0.5], "power") == 0.0
    assert kelly_fraction([0.4, 0.4, 0.4], "flex") == 0.0


def test_kelly_positive_with_edge_and_bounded():
    frac = kelly_fraction([0.7, 0.7], "power")
    assert 0.0 < frac < 1.0


def test_kelly_scales_with_multiplier():
    full = kelly_fraction([0.72, 0.72], "power", multiplier=1.0)
    quarter = kelly_fraction([0.72, 0.72], "power", multiplier=0.25)
    assert quarter == pytest.approx(full * 0.25, abs=1e-3)


def test_slip_outcomes_probabilities_sum_to_one():
    outcomes = _slip_outcomes([0.6, 0.65, 0.7], "flex")
    assert outcomes is not None
    assert sum(p for p, _ in outcomes) == pytest.approx(1.0, abs=1e-9)


def test_best_slips_includes_kelly_pct():
    picks = [
        {"player": "A", "team": "FRA", "win_prob": 0.72},
        {"player": "B", "team": "ENG", "win_prob": 0.68},
        {"player": "C", "team": "BRA", "win_prob": 0.66},
    ]
    slips = best_slips(picks)
    assert slips
    assert all("kelly_pct" in s for s in slips)
    assert all(0.0 <= s["kelly_pct"] <= 100.0 for s in slips)
