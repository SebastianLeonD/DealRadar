"""Shin / multiplicative / power de-vig (council OBJ-5)."""

from engine.devig import (
    devig_multiplicative,
    devig_power,
    devig_shin,
    devig_two_sided,
)
from engine.probability import implied_prob


def test_devig_removes_vig_probs_sum_to_one():
    for method in ('shin', 'multiplicative', 'power'):
        dv = devig_two_sided(-130, +105, method)
        assert abs(dv['p_over'] + dv['p_under'] - 1.0) < 1e-9


def test_shin_z_solved_from_pair_in_unit_interval():
    dv = devig_two_sided(-130, +105, 'shin')
    assert dv['devig_method'] == 'shin'
    assert 0.0 <= dv['z'] < 1.0


def test_shin_true_prob_between_proportional_and_raw():
    # Shin shades the favourite vs proportional on an asymmetric pair.
    over, under = -200, +170
    shin = devig_shin(over, under)
    assert shin is not None
    p_over_shin, _, z = shin
    p_over_prop, _ = devig_multiplicative(over, under)
    # Both are valid probabilities; Shin differs from proportional when z>0.
    assert 0.0 < p_over_shin < 1.0
    if z > 1e-6:
        assert abs(p_over_shin - p_over_prop) > 1e-6


def test_no_vig_pair_returns_normalized_directly():
    # A pair with booksum <= 1 has no vig to remove.
    dv = devig_two_sided(+100, +100, 'shin')
    assert abs(dv['p_over'] - 0.5) < 1e-9
    assert abs(dv['p_under'] - 0.5) < 1e-9


def test_hold_is_booksum():
    dv = devig_two_sided(-130, +105, 'shin')
    expected = implied_prob(-130) + implied_prob(+105)
    assert abs(dv['hold'] - expected) < 1e-9
    assert dv['hold'] > 1.0  # there is vig


def test_power_devig_matches_legacy_behaviour():
    p_over, p_under = devig_power(-130, +110)
    assert abs(p_over + p_under - 1.0) < 1e-9
    assert 0.0 < p_over < 1.0


def test_favourite_has_higher_true_prob():
    dv = devig_two_sided(-250, +200, 'shin')
    assert dv['p_over'] > dv['p_under']  # -250 is the favourite (over side)
