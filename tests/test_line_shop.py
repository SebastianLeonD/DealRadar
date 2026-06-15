"""Tests for line-shopping the PrizePicks board against Underdog."""

from engine import line_shop
from scrapers.underdog_api import resolve_stat

UD = [
    {
        "player": "Alexander Isak", "normalized": "alexander isak",
        "join_key": "player_shots", "line": 2.5,
        "higher_price": "+110", "lower_price": "-140",
        "higher_multiplier": 1.1, "lower_multiplier": 0.71,
    },
    {
        "player": "Kylian Mbappé", "normalized": "kylian mbappe",
        "join_key": "player_shots", "line": 3.5,
        "higher_multiplier": 1.0, "lower_multiplier": 1.0,
    },
    {
        "player": "Andrés Cubas", "normalized": "andres cubas",
        "join_key": "label:Passes Attempted", "line": 40.5,
    },
]
INDEX = line_shop.build_index(UD)


# --- stat resolution (scraper) ---

def test_full_match_stat_maps_to_engine_key():
    key, label, mapped = resolve_stat("period_1_2_shots_on_target")
    assert key == "player_shots_on_target" and mapped is True


def test_first_half_stat_gets_the_1h_suffix():
    key, _, _ = resolve_stat("period_1_shots_attempted")
    assert key == "player_shots_1h"


def test_label_only_stat_uses_the_shared_label_key():
    key, label, mapped = resolve_stat("period_1_2_passes")
    assert key == "label:Passes Attempted" and mapped is False


def test_second_half_and_unknown_stats_are_dropped():
    assert resolve_stat("period_2_shots") is None
    assert resolve_stat("period_1_2_corners_won") is None


# --- join key parity with the PrizePicks board ---

def test_pp_join_key_prefers_engine_key():
    assert line_shop.pp_join_key("player_shots", "Shots") == "player_shots"


def test_pp_join_key_falls_back_to_label():
    assert line_shop.pp_join_key(None, "Passes Attempted") == "label:Passes Attempted"


def test_label_keys_match_across_boards():
    # The scraper's label key must equal the PP board's label key, or no join.
    ud_key, _, _ = resolve_stat("period_1_2_passes")
    assert ud_key == line_shop.pp_join_key(None, "Passes Attempted")


# --- the comparison ---

def test_lower_underdog_line_routes_over_to_underdog():
    cmp = line_shop.match_prop("Alexander Isak", "alexander isak", "player_shots", 3.0, INDEX)
    assert cmp["ud_line"] == 2.5
    assert cmp["ud_delta"] == -0.5
    assert cmp["over_app"] == "UD" and cmp["under_app"] == "PP"


def test_equal_line_is_even_both_sides():
    cmp = line_shop.match_prop("Kylian Mbappé", "kylian mbappe", "player_shots", 3.5, INDEX)
    assert cmp["ud_delta"] == 0
    assert cmp["over_app"] == "EVEN" and cmp["under_app"] == "EVEN"


def test_accent_insensitive_name_join():
    cmp = line_shop.match_prop("Andres Cubas", line_shop.normalize("Andres Cubas"),
                               "label:Passes Attempted", 41.5, INDEX)
    assert cmp is not None and cmp["ud_matched_name"] == "Andrés Cubas"


def test_no_underdog_match_returns_none():
    assert line_shop.match_prop("Nobody Here", "nobody here", "player_shots", 1.5, INDEX) is None


def test_duration_mismatch_never_joins():
    # PP first-half prop must not match Underdog's full-match shots line.
    assert line_shop.match_prop("Alexander Isak", "alexander isak",
                                "player_shots_1h", 1.5, INDEX) is None
