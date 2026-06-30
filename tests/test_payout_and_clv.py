"""Payout-table primitive (OBJ-11/34) and probability-units CLV (OBJ-2)."""

import math

from engine.clv_report import calculate_clv_line, calculate_clv_prob
from engine.payout_table import (
    FLEX_PAYOUTS,
    POWER_PAYOUTS,
    power_breakeven,
    power_ev,
    power_multiplier,
)


def test_power_breakeven_is_inverse_nth_root_of_multiplier():
    for n, m in POWER_PAYOUTS.items():
        be = power_breakeven(n)
        # p^n * M == 1 at break-even
        assert math.isclose(be ** n * m, 1.0, rel_tol=1e-9)


def test_power_breakeven_two_pick_three_x():
    assert math.isclose(power_breakeven(2), (1 / 3.0) ** 0.5, rel_tol=1e-9)


def test_power_ev_zero_at_breakeven():
    n = 3
    be = power_breakeven(n)
    assert abs(power_ev([be] * n)) < 1e-9


def test_power_ev_positive_above_breakeven():
    n = 3
    be = power_breakeven(n)
    assert power_ev([be + 0.05] * n) > 0


def test_flex_ladder_has_partial_credit_tiers():
    ladder = FLEX_PAYOUTS[6]
    assert ladder[6] > ladder[5] > ladder[4]  # more correct pays more


def test_clv_prob_over_positive_when_market_moves_up():
    # flagged at 0.55 true, closed at 0.60 -> +0.05 for an OVER bet
    assert calculate_clv_prob('OVER', 0.55, 0.60) == 0.05


def test_clv_prob_under_sign_flips():
    # same move HURTS an UNDER bet
    assert calculate_clv_prob('UNDER', 0.55, 0.60) == -0.05


def test_clv_line_is_secondary_diagnostic():
    assert calculate_clv_line('OVER', 25.5, 26.5) == 1.0
    assert calculate_clv_line('UNDER', 25.5, 26.5) == -1.0


def test_missing_multiplier_raises():
    try:
        power_multiplier(7)
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown board size")
