"""Tests for team-form context (resolution + name aliasing)."""

from engine.team_profiles import defense_rank, team_form

PROFILES = [
    {
        "team": "Brazil",
        "normalized": "brazil",
        "games": 1,
        "clean_sheets": 0,
        "save_pct": 60.0,
        "goals_per_shot": 0.11,
        "per_game": {
            "shots": 12.0, "shots_on_target": 5.0, "goals": 1.0,
            "goals_allowed": 1.0, "shots_on_target_against": 3.0, "saves": 2.0,
            "fouls": 16.0, "fouls_drawn": 14.0, "offsides": 2.0, "crosses": 16.0,
            "tackles": 12.0, "interceptions": 8.0,
        },
    },
    {
        "team": "United States",  # FBref name; books say "USA"
        "normalized": "united states",
        "games": 1,
        "clean_sheets": 1,
        "save_pct": 80.0,
        "goals_per_shot": 0.2,
        "per_game": {
            "shots": 10.0, "shots_on_target": 4.0, "goals": 4.0,
            "goals_allowed": 1.0, "shots_on_target_against": 2.0, "saves": 1.0,
            "fouls": 10.0, "fouls_drawn": 12.0, "offsides": 1.0, "crosses": 8.0,
            "tackles": 9.0, "interceptions": 7.0,
        },
    },
]


def test_team_form_resolves_own_attack_and_opponent_defense():
    form = team_form("Brazil", "United States", PROFILES)
    assert "12.0/g shots" in form["team_attack"]
    assert "5.0/g on target" in form["team_attack"]
    assert "conceded" in form["opponent_defense"]
    assert form["team_games"] == 1


def test_alias_matches_book_name_to_fbref_name():
    # Opponent comes through as "USA" (book naming) -> United States profile.
    form = team_form("Brazil", "USA", PROFILES)
    assert "opponent_defense" in form
    assert "clean sheet" in form["opponent_defense"]


def test_unknown_team_yields_no_form():
    form = team_form("Atlantis", "Wakanda", PROFILES)
    assert form == {}


def test_empty_profiles_is_safe():
    assert team_form("Brazil", "USA", []) == {}


def test_defense_rank_orders_by_fewest_shots_conceded():
    profiles = PROFILES + [
        {
            "team": "Spain",
            "normalized": "spain",
            "games": 1,
            "clean_sheets": 1,
            "per_game": {**PROFILES[0]["per_game"], "shots_on_target_against": 1.0},
        }
    ]
    ranks = defense_rank(profiles)
    # Spain concedes the fewest (1.0) -> rank 1; Brazil the most (3.0) -> rank 3.
    assert ranks["spain"] == (1, 3)
    assert ranks["united states"] == (2, 3)
    assert ranks["brazil"] == (3, 3)


def test_opponent_defense_line_includes_rank():
    form = team_form("Brazil", "United States", PROFILES)
    assert "rank 1/2" in form["opponent_defense"]
    assert form["opponent_defense_rank"] == (1, 2)
