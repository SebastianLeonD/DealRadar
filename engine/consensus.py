"""Line-matched no-vig consensus — the identified ground truth (OBJ-1/3).

The headline consensus averages per-book de-vigged true probabilities ACROSS
BOOKS QUOTING THE SAME (player, stat, line) within one snapshot bucket. It is
computed in NO-VIG PROBABILITY space (not logit): the estimand P(Over) and the
PrizePicks break-even comparison both live in probability units, and logit
averaging injects Jensen curvature bias near the 0/1 tails where points props
sit.

A line earns the 'identified' tag ONLY when at least MIN_BOOKS_FOR_CONSENSUS
genuinely two-sided books contribute AND no book was dropped by budget
truncation or a typed fetch failure below the floor (OBJ credit-cost /
http-robustness). Otherwise the tag is withheld and the line is flagged
single-book/degraded — it may not back an identified verdict.

Cross-line mapping (folding books quoting *different* lines into one number via
a sigma displacement) is ASSERTED/GATED and deliberately lives elsewhere; it
never produces the identified consensus_true_p.
"""

from __future__ import annotations

from engine.config import HOLD_CEILING, MIN_BOOKS_FOR_CONSENSUS


def line_matched_consensus(
    book_probs: dict[str, float],
    *,
    book_holds: dict[str, float] | None = None,
    min_books: int = MIN_BOOKS_FOR_CONSENSUS,
    budget_truncated: bool = False,
    failed_books: int = 0,
) -> dict:
    """Equal-weight no-vig consensus for one (player, stat, line) in one bucket.

    book_probs: {book: de-vigged true_p_over at THIS exact line}. Every value
        must already be a single book's two-sided de-vig output.
    book_holds: optional {book: booksum}; books above HOLD_CEILING are dropped.
    budget_truncated / failed_books: degradation signals that withhold the tag.

    Returns: consensus_p_over, consensus_p_under, consensus_n, consensus_book_set,
    consensus_tag in {'identified', 'single_book', 'degraded'}.
    """
    holds = book_holds or {}
    contributing = {
        book: p
        for book, p in book_probs.items()
        if holds.get(book, 1.0) <= HOLD_CEILING
    }

    n = len(contributing)
    if n == 0:
        return {
            "consensus_p_over": None,
            "consensus_p_under": None,
            "consensus_n": 0,
            "consensus_book_set": [],
            "consensus_tag": "degraded",
        }

    p_over = sum(contributing.values()) / n  # mean in probability space
    book_set = sorted(contributing)

    if budget_truncated or failed_books > 0:
        # A partial book set never earns the identified tag even if n >= min:
        # we cannot claim consensus over books we did not (or failed to) fetch.
        tag = "degraded"
    elif n >= min_books:
        tag = "identified"
    else:
        tag = "single_book"

    return {
        "consensus_p_over": p_over,
        "consensus_p_under": 1.0 - p_over,
        "consensus_n": n,
        "consensus_book_set": book_set,
        "consensus_tag": tag,
    }


def consensus_over_ladder(
    book_ladders: dict[str, list[tuple[float, float]]],
    *,
    min_books: int = MIN_BOOKS_FOR_CONSENSUS,
    budget_truncated: bool = False,
    failed_books: int = 0,
) -> dict[float, dict]:
    """Line-matched consensus across a set of book ladders.

    book_ladders: {book: [(line, true_p_over), ...]} — each book's de-vigged
        ladder for one (player, stat) in one bucket.

    Returns {line: consensus dict}. Only lines quoted by >= 1 book appear; the
    'identified' tag still requires >= min_books AT THAT EXACT LINE, which is
    the whole point — P(over 25.5) and P(over 24.5) are different events and are
    never averaged together.
    """
    by_line: dict[float, dict[str, float]] = {}
    for book, ladder in book_ladders.items():
        for line, p_over in ladder:
            by_line.setdefault(line, {})[book] = p_over

    out: dict[float, dict] = {}
    for line, probs in by_line.items():
        out[line] = line_matched_consensus(
            probs,
            min_books=min_books,
            budget_truncated=budget_truncated,
            failed_books=failed_books,
        )
    return out
