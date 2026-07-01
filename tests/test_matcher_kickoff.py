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


def test_resolve_kickoff_returns_none_when_no_commence_time_parses():
    """An unparseable/missing commence_time on every candidate match must not
    fall back to matches[0] — that silently anchors the edge to an arbitrary
    game (the original bug). No good guess means no kickoff."""
    games = [
        {"game": "Spain @ Portugal", "commence_time": "not-a-timestamp"},
        {"game": "Spain @ Argentina", "commence_time": None},
    ]
    commence_time, game = _resolve_kickoff("Spain", games)
    assert commence_time is None
    assert game is None


def test_resolve_kickoff_grace_window_is_2h45m_not_6h():
    """The upcoming/in-progress grace shrank from 6h to 2.75h (aligned with
    MATCH_OVER_HOURS=2.5h + buffer): a game that started 4h ago must now be
    treated as past, not still 'in progress'."""
    now = datetime.now(timezone.utc)
    just_past_grace = (now - timedelta(hours=4)).isoformat()
    long_past = (now - timedelta(days=10)).isoformat()
    games = [
        {"game": "Spain @ Portugal", "commence_time": long_past},
        {"game": "Spain @ Argentina", "commence_time": just_past_grace},
    ]
    commence_time, game = _resolve_kickoff("Spain", games)
    # Both are "past" under the new 2.75h grace, so the latest (most recent)
    # past game wins, not the 4h-ago one being miscategorized as upcoming.
    assert commence_time == just_past_grace
    assert game == "Spain @ Argentina"
