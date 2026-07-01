"""STALE_MAX_MINUTES (contemporaneity, OBJ-21..24): a book's ladder is dropped
from a player's consensus when its captured_at is stale relative to the
NEWEST book for that player — not stale in wall-clock terms."""

from datetime import datetime, timedelta, timezone

from engine.config import STALE_MAX_MINUTES
from engine.matcher import _drop_dead_books, _drop_stale_books, evaluate_combo


def _iso(dt):
    return dt.isoformat()


def test_books_within_window_are_kept():
    now = datetime.now(timezone.utc)
    books = {
        "draftkings": {"points": [(20.5, 0.55)], "captured_at": _iso(now)},
        "fanduel": {"points": [(20.5, 0.52)], "captured_at": _iso(now - timedelta(minutes=5))},
    }
    kept = _drop_stale_books(books)
    assert set(kept) == {"draftkings", "fanduel"}


def test_book_older_than_stale_max_is_dropped():
    now = datetime.now(timezone.utc)
    books = {
        "draftkings": {"points": [(20.5, 0.55)], "captured_at": _iso(now)},
        "fanduel": {
            "points": [(20.5, 0.52)],
            "captured_at": _iso(now - timedelta(minutes=STALE_MAX_MINUTES + 25)),
        },
    }
    kept = _drop_stale_books(books)
    assert set(kept) == {"draftkings"}


def test_dead_book_with_past_commence_time_is_dropped():
    now = datetime.now(timezone.utc)
    books = {
        "fanduel": {
            "points": [(2.0, 0.94)],
            "captured_at": _iso(now),
            "commence_time": _iso(now - timedelta(days=14)),  # game already played
        },
    }
    kept = _drop_dead_books(books)
    assert kept == {}


def test_book_with_future_commence_time_is_kept():
    now = datetime.now(timezone.utc)
    books = {
        "fanduel": {
            "points": [(2.0, 0.94)],
            "captured_at": _iso(now),
            "commence_time": _iso(now + timedelta(hours=2)),  # game hasn't started
        },
    }
    kept = _drop_dead_books(books)
    assert set(kept) == {"fanduel"}


# --- combos must apply the same dead/stale-ladder hygiene (evaluate_combo) ---

def test_combo_excludes_a_dead_ladder_book():
    now = datetime.now(timezone.utc)
    pp_player = {"player_name": "Player A + Player B", "line": 3.5}
    live_book = {
        "points": [(2.0, 0.55)],
        "captured_at": _iso(now),
        "commence_time": _iso(now + timedelta(hours=2)),
    }
    dead_book = {
        "points": [(2.0, 0.55)],
        "captured_at": _iso(now),
        "commence_time": _iso(now - timedelta(days=1)),  # game already finished
    }
    ladders = {
        "Player A": {"draftkings": live_book, "fanduel": dead_book},
        "Player B": {"draftkings": live_book, "fanduel": dead_book},
    }
    result = evaluate_combo(pp_player, ladders, rate_scale=1.0, extra_flags=[])
    assert result is not None
    evaluation, _, _ = result
    # fanduel's ladder is dead (game already started/finished) for both legs,
    # so only draftkings should have priced the combo.
    assert evaluation["book_count"] == 1
