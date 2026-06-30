"""Asserted soccer model: turn an FBref rate prior into P(over) for a prop.

This is the first data-driven soccer pricing model — a Poisson count model
seeded by the minutes-weighted, shrunk per-90 rate from engine/rate_prior.py.
For a player expected to play `expected_minutes`, the count rate is
    lambda = rate_per_90 * expected_minutes / 90
and P(over the line) is the push-adjusted Poisson tail (engine/probability.py).

FIREWALL: every probability this produces is ASSERTED, not identified. It rests
on a chosen distribution (Poisson — a negative-binomial upgrade for
overdispersion is the planned successor) and on a rate prior estimated from
limited data. It is stamped sigma_source='fbref_poisson_prior' and may NOT flag
a bet until it out-Briers the market-consensus baseline out-of-sample through
the Phase-2 calibration gate. It is a candidate model under test, not truth.
"""

from __future__ import annotations

from engine.probability import poisson_p_over_push_adjusted
from engine.rate_prior import rate_prior

MODEL_SIGMA_SOURCE = "fbref_poisson_prior"


def expected_lambda(rate_per_90: float, expected_minutes: float) -> float:
    """Poisson rate for the stat over the player's expected minutes on the pitch."""
    return max(0.0, rate_per_90 * max(0.0, expected_minutes) / 90.0)


def model_p_over(
    rate_per_90: float,
    expected_minutes: float,
    line: float,
) -> float:
    """Push-adjusted P(over `line`) for a Poisson count at the expected lambda."""
    lam = expected_lambda(rate_per_90, expected_minutes)
    return poisson_p_over_push_adjusted(lam, line)


def model_prediction(
    logs: list[dict],
    stat_type: str,
    line: float,
    *,
    expected_minutes: float | None = None,
    baseline_rate: float | None = None,
    starts: bool | None = None,
) -> dict:
    """Full asserted prediction for one soccer prop from a player's recent logs.

    expected_minutes defaults to the player's recent average (a presumed
    starter plays ~90); when `starts` is known from a lineup feed, a confirmed
    non-starter is scaled down. Returns the prediction plus the provenance the
    calibration gate needs.
    """
    prior = rate_prior(logs, stat_type, baseline_rate=baseline_rate)

    if expected_minutes is None:
        expected_minutes = prior["avg_minutes"] or 90.0
    if starts is False:
        # A confirmed benching collapses expectations (sub cameo at most). The
        # real lineup signal comes from a FotMob/Sofascore feed, not FBref.
        expected_minutes = min(expected_minutes, 20.0)

    p_over = model_p_over(prior["rate"], expected_minutes, line)
    return {
        "stat_type": stat_type,
        "line": line,
        "p_over": round(p_over, 4),
        "p_under": round(1.0 - p_over, 4),
        "lambda": round(expected_lambda(prior["rate"], expected_minutes), 4),
        "rate_per_90": round(prior["rate"], 4),
        "expected_minutes": expected_minutes,
        "credibility": prior["weight"],          # 0..1: how much is player vs baseline
        "n_matches": prior["n_matches"],
        "sigma_source": MODEL_SIGMA_SOURCE,       # asserted, gated by Phase 2
        "firewall_side": "asserted_gated",
    }
