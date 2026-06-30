"""Binding exposure caps + POWER-exact gate (council Pillars 3/4)."""

from engine.exposure import (
    apply_exposure_caps,
    correlation_adjusted_breakeven,
    passes_power_gate,
)
from engine.payout_table import power_breakeven


def test_power_gate_is_exact_breakeven():
    be = power_breakeven(3)
    assert not passes_power_gate(be - 0.001, 3)
    assert passes_power_gate(be + 0.001, 3)


def test_unknown_board_size_fails_gate():
    assert not passes_power_gate(0.99, 7)


def test_correlation_adjusted_breakeven_never_below_independent():
    for n in (2, 3, 4, 5, 6):
        base = power_breakeven(n)
        adj = correlation_adjusted_breakeven(n)
        assert adj >= base  # correlation only raises the bar


def test_zero_rho_recovers_independent_breakeven():
    for n in (2, 3, 4):
        assert abs(correlation_adjusted_breakeven(n, rho0=0.0) - power_breakeven(n)) < 1e-9


def test_per_game_cap_binds():
    picks = [
        {'player': 'A', 'game_id': 'G1', 'win_prob': 0.70},
        {'player': 'B', 'game_id': 'G1', 'win_prob': 0.68},
        {'player': 'C', 'game_id': 'G1', 'win_prob': 0.66},  # 3rd same-game leg
        {'player': 'D', 'game_id': 'G2', 'win_prob': 0.65},
    ]
    kept, dropped = apply_exposure_caps(picks, max_legs_per_game=2)
    kept_games = [p['game_id'] for p in kept]
    assert kept_games.count('G1') == 2
    assert any(d['player'] == 'C' for d in dropped)


def test_per_player_cap_binds():
    picks = [
        {'player': 'A', 'game_id': 'G1', 'win_prob': 0.70},
        {'player': 'A', 'game_id': 'G1', 'win_prob': 0.69},  # same player twice
    ]
    kept, dropped = apply_exposure_caps(picks, max_legs_per_player=1)
    assert len(kept) == 1
    assert len(dropped) == 1


def test_total_leg_cap_binds():
    picks = [{'player': f'P{i}', 'game_id': f'G{i}', 'win_prob': 0.6} for i in range(8)]
    kept, _ = apply_exposure_caps(picks, max_total_legs=6, max_legs_per_player=1)
    assert len(kept) == 6


def test_strongest_legs_survive_ties():
    picks = [
        {'player': 'A', 'game_id': 'G1', 'win_prob': 0.80},
        {'player': 'B', 'game_id': 'G1', 'win_prob': 0.60},
        {'player': 'C', 'game_id': 'G1', 'win_prob': 0.55},
    ]
    kept, dropped = apply_exposure_caps(picks, max_legs_per_game=1)
    assert [p['player'] for p in kept] == ['A']  # highest win_prob kept
