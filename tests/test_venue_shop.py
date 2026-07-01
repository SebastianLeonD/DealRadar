"""Venue-shopping rule (Feature A): PP vs Underdog line for the same side."""

from engine.matcher import _venue_comparison


def _books(ud_line: float) -> dict:
    return {"underdog": {"points": [(ud_line, 0.5)], "captured_at": "x"}}


def test_over_prefers_lower_underdog_line():
    venue, note = _venue_comparison("OVER", 2.5, _books(2.0))
    assert venue == "underdog"
    assert "Underdog line 2.0 is softer than PP 2.5 for the OVER" == note


def test_under_prefers_higher_underdog_line():
    venue, note = _venue_comparison("UNDER", 2.5, _books(3.0))
    assert venue == "underdog"
    assert "Underdog line 3.0 is softer than PP 2.5 for the UNDER" == note


def test_over_with_worse_underdog_line_favours_prizepicks():
    venue, note = _venue_comparison("OVER", 2.5, _books(3.0))
    assert venue == "prizepicks"
    assert "PrizePicks line 2.5 is softer than Underdog 3.0 for the OVER" == note


def test_equal_lines_favour_prizepicks_with_same_line_note():
    venue, note = _venue_comparison("OVER", 2.5, _books(2.5))
    assert venue == "prizepicks"
    assert note == "Same line both apps"


def test_missing_underdog_data_favours_prizepicks_only_note():
    venue, note = _venue_comparison("OVER", 2.5, {})
    assert venue == "prizepicks"
    assert note == "Only on PrizePicks"
