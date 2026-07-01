"""Consensus tests.

Two independent layers, both ratified by the council:
  * line-matched no-vig consensus (OBJ-1/3) — only books quoting the EXACT line
    average together, and a single book never earns the 'identified' tag;
  * the two-tier sharp/soft truth model — soft pick'em apps (Underdog) price
    stats the sharps ignore but never tip a verdict when a sharp book is present.
"""

import pytest

from engine.consensus import consensus_over_ladder, line_matched_consensus
from engine.matcher import SOFT_ONLY_FLAG, evaluate_player
from engine.probability import tiered_consensus


# --- line-matched no-vig consensus (council OBJ-1/3) ---

def test_equal_weight_mean_in_probability_space():
    c = line_matched_consensus({'dk': 0.60, 'fd': 0.50})
    assert abs(c['consensus_p_over'] - 0.55) < 1e-9
    assert abs(c['consensus_p_under'] - 0.45) < 1e-9
    assert c['consensus_n'] == 2
    assert c['consensus_tag'] == 'identified'
    assert c['consensus_book_set'] == ['dk', 'fd']


def test_single_book_does_not_earn_identified_tag():
    c = line_matched_consensus({'dk': 0.58})
    assert c['consensus_n'] == 1
    assert c['consensus_tag'] == 'single_book'


def test_high_hold_book_is_dropped():
    c = line_matched_consensus(
        {'dk': 0.60, 'fd': 0.50, 'shady': 0.90},
        book_holds={'dk': 1.04, 'fd': 1.05, 'shady': 1.20},
    )
    assert 'shady' not in c['consensus_book_set']
    assert c['consensus_n'] == 2
    assert abs(c['consensus_p_over'] - 0.55) < 1e-9


def test_budget_truncation_withholds_identified_tag():
    c = line_matched_consensus({'dk': 0.60, 'fd': 0.50}, budget_truncated=True)
    assert c['consensus_n'] == 2
    assert c['consensus_tag'] == 'degraded'  # cannot claim consensus over a partial set


def test_fetch_failure_withholds_identified_tag():
    c = line_matched_consensus({'dk': 0.60, 'fd': 0.50}, failed_books=1)
    assert c['consensus_tag'] == 'degraded'


def test_different_lines_are_never_averaged_together():
    # DK quotes 25.5, FD quotes 24.5 — they are different events. Each line
    # gets its own consensus; neither reaches 2 books, so neither is identified.
    ladders = {
        'dk': [(25.5, 0.52)],
        'fd': [(24.5, 0.61)],
    }
    out = consensus_over_ladder(ladders)
    assert set(out) == {25.5, 24.5}
    assert out[25.5]['consensus_n'] == 1
    assert out[24.5]['consensus_n'] == 1
    assert out[25.5]['consensus_tag'] == 'single_book'


def test_same_line_across_books_is_identified():
    ladders = {
        'dk': [(25.5, 0.52)],
        'fd': [(25.5, 0.56)],
        'betmgm': [(25.5, 0.54)],
    }
    out = consensus_over_ladder(ladders)
    assert out[25.5]['consensus_n'] == 3
    assert out[25.5]['consensus_tag'] == 'identified'
    assert abs(out[25.5]['consensus_p_over'] - 0.54) < 1e-9


# --- two-tier sharp/soft (Underdog) truth model ---

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


def test_soft_book_does_not_count_toward_identified_tag():
    # One sharp book (fanduel) + one soft pick'em app (underdog) at the same
    # exact line must NOT satisfy the >=2 count for 'identified' — the tag is
    # the calibration gate's eligibility key and must mean genuinely sharp.
    pp = {"player_name": "X", "line": 1.5, "stat_type": "player_shots", "team": "FRA"}
    books = {
        "fanduel": _poisson_book(0.55, line=1.5),
        "underdog": _poisson_book(0.60, line=1.5),
    }
    ev = evaluate_player(pp, books, {}, model="poisson")
    assert ev["consensus_tag"] == "single_book"


def test_two_sharp_books_at_same_line_is_identified():
    pp = {"player_name": "X", "line": 1.5, "stat_type": "player_shots", "team": "FRA"}
    books = {
        "fanduel": _poisson_book(0.55, line=1.5),
        "draftkings": _poisson_book(0.58, line=1.5),
    }
    ev = evaluate_player(pp, books, {}, model="poisson")
    assert ev["consensus_tag"] == "identified"


# --- evidence-gated verdicts (council-ratified: one sharp book is a pricing
# artifact, not a confirmed edge; YES requires >=2 sharp books at the exact
# PP line, i.e. consensus_tag == 'identified') ---

def test_single_sharp_book_high_prob_capped_at_lean():
    pp = {"player_name": "X", "line": 1.5, "stat_type": "player_shots", "team": "FRA"}
    books = {"draftkings": _poisson_book(0.71, line=1.5)}
    ev = evaluate_player(pp, books, {}, model="poisson")
    assert ev["consensus_tag"] == "single_book"
    assert ev["verdict"] == "LEAN"
    assert any("2+ to confirm a YES" in flag for flag in ev["flags"])


def test_two_sharp_books_identified_reaches_yes():
    pp = {"player_name": "X", "line": 1.5, "stat_type": "player_shots", "team": "FRA"}
    books = {
        "fanduel": _poisson_book(0.60, line=1.5),
        "draftkings": _poisson_book(0.60, line=1.5),
    }
    ev = evaluate_player(pp, books, {}, model="poisson")
    assert ev["consensus_tag"] == "identified"
    assert ev["verdict"] == "YES"
    assert ev["flags"] == []
