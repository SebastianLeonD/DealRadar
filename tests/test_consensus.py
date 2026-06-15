"""Two-tier truth model: sharp books price the probability, soft pick'em
apps (Underdog) only price stats the sharps ignore — and never tip a verdict
when a sharp book is present."""

import pytest

from engine.matcher import SOFT_ONLY_FLAG, evaluate_player
from engine.probability import tiered_consensus


# --- the pure consensus function ---

def test_tiered_excludes_soft_when_sharp_present():
    # Default weight 0: the soft 0.70 must not pull the sharp 0.55 estimate.
    consensus, spread = tiered_consensus({"draftkings": 0.55}, {"underdog": 0.70})
    assert consensus == pytest.approx(0.55)
    assert spread == 0.0  # one sharp book -> no disagreement


def test_tiered_spread_is_sharp_only():
    # Underdog disagreeing wildly is a line-shop signal, not market spread.
    consensus, spread = tiered_consensus(
        {"draftkings": 0.56, "fanduel": 0.60}, {"underdog": 0.90}
    )
    assert consensus == pytest.approx(0.58)
    assert spread == pytest.approx(0.04)  # 0.60 - 0.56, ignores underdog


def test_tiered_soft_weight_nudges_not_decides():
    consensus, _ = tiered_consensus({"draftkings": 0.50}, {"underdog": 0.70}, soft_weight=0.25)
    # (0.50 + 0.25*0.70) / 1.25 = 0.54 — a nudge, not an equal vote (which is 0.60).
    assert consensus == pytest.approx(0.54)


def test_tiered_soft_only_carries_estimate():
    # No sharp book -> soft books are all we have.
    consensus, spread = tiered_consensus({}, {"underdog": 0.63})
    assert consensus == pytest.approx(0.63)


# --- evaluate_player end to end ---

def _poisson_book(p_over_at_line, line=2.5):
    """A one-line Poisson ladder priced to roughly p_over at `line`."""
    return {"points": [(line, p_over_at_line)], "captured_at": "2026-06-14T12:00:00"}


def test_soft_book_does_not_tip_verdict_when_sharp_present():
    pp = {"player_name": "X", "line": 2.5, "stat_type": "player_shots", "team": "FRA"}
    # DraftKings says ~52% (a NO); Underdog says ~75%. The soft book must not
    # drag the win prob up — verdict stays driven by the sharp number.
    books = {
        "draftkings": _poisson_book(0.52),
        "underdog": _poisson_book(0.75),
    }
    ev = evaluate_player(pp, books, {}, model="poisson")
    assert ev["book_count"] == 1  # underdog excluded from the truth estimate
    assert SOFT_ONLY_FLAG not in ev["flags"]
    assert ev["win_prob"] == pytest.approx(0.52, abs=0.03)


def test_soft_only_prop_is_flagged_and_capped():
    pp = {"player_name": "X", "line": 2.5, "stat_type": "player_goalie_saves", "team": "FRA"}
    books = {"underdog": _poisson_book(0.75)}  # a stat no sharp book quotes
    ev = evaluate_player(pp, books, {}, model="poisson")
    assert SOFT_ONLY_FLAG in ev["flags"]
    assert ev["book_count"] == 1
    assert ev["verdict"] == "LEAN"  # soft-only never a confident YES
