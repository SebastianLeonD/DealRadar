"""_resolve_kickoff must not anchor a modeled edge to a stale past fixture
when the same team appears in multiple tournament games."""

from datetime import datetime, timedelta, timezone

from engine.matcher import _resolve_kickoff


def test_resolve_kickoff_prefers_upcoming_game_over_past():
    now = datetime.now(timezone.utc)
    past = (now - timedelta(days=14)).isoformat()
    upcoming = (now + timedelta(days=1)).isoformat()
    games = [
        {"game": "Spain @ Portugal", "commence_time": past},
        {"game": "Spain @ Argentina", "commence_time": upcoming},
    ]
    commence_time, game = _resolve_kickoff("Spain", games)
    assert commence_time == upcoming
    assert game == "Spain @ Argentina"
