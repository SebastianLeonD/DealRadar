"""Tests for model-based pricing of book-less PrizePicks stats."""

from engine.projections import FIELD_BY_STAT, model_stat_types, project_prop

PLAYERS = [
    {
        "player": "Andrés Cubas",
        "team": "Paraguay",
        "normalized": "andres cubas",
        "matches_played": 2.0,
        "fouls": 6.0,        # 3 per game
        "tackles": 4.0,
        "saves": 0.0,
    },
    {
        "player": "Patrick Beach",
        "team": "Australia",
        "normalized": "patrick beach",
        "matches_played": 2.0,
        "saves": 8.0,        # 4 per game
        "fouls": 0.0,
    },
]


def test_project_prop_picks_over_when_rate_clears_line():
    proj = project_prop("Andrés Cubas", "player_fouls", 1.5, PLAYERS)
    assert proj["play"] == "OVER"
    assert proj["win_prob"] > 0.7
    assert proj["expected"] == 3.0  # 6 fouls / 2 games


def test_project_prop_picks_under_when_rate_below_line():
    proj = project_prop("Patrick Beach", "player_goalie_saves", 6.5, PLAYERS)
    assert proj["play"] == "UNDER"  # 4/game projected, line is 6.5


def test_modeled_plays_are_always_flagged_and_capped_at_lean():
    proj = project_prop("Andrés Cubas", "player_fouls", 0.5, PLAYERS)
    # Even at ~99% win prob, the "no market" flag caps the verdict at LEAN.
    assert proj["verdict"] == "LEAN"
    assert any("no betting market" in flag for flag in proj["flags"])


def test_small_sample_adds_a_warning_flag():
    one_game = [{**PLAYERS[0], "matches_played": 1.0}]
    proj = project_prop("Andrés Cubas", "player_fouls", 1.5, one_game)
    assert any("Small sample" in flag for flag in proj["flags"])


def test_accent_insensitive_name_match():
    proj = project_prop("Andres Cubas", "player_fouls", 1.5, PLAYERS)  # no accent
    assert proj is not None
    assert proj["matched_name"] == "Andrés Cubas"


def test_unmodelable_stat_returns_none():
    assert project_prop("Andrés Cubas", "player_shots", 1.5, PLAYERS) is None


def test_missing_player_returns_none():
    assert project_prop("Nobody Here", "player_fouls", 1.5, PLAYERS) is None


def test_no_games_played_returns_none():
    no_games = [{**PLAYERS[0], "matches_played": 0.0}]
    assert project_prop("Andrés Cubas", "player_fouls", 1.5, no_games) is None


def test_model_stat_types_match_field_map():
    assert set(model_stat_types()) == set(FIELD_BY_STAT)
    assert "player_shots" not in model_stat_types()  # book-priced, not modeled
