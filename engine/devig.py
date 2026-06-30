"""Per-book de-vig as the single identified primitive (council OBJ-5/25/26).

`devig_two_sided` operates on ONE book's Over/Under American price pair only.
De-vigging an averaged or blended pair is forbidden — consensus averages the
already-de-vigged per-book true probabilities (see engine/consensus.py).

Methods:
  * shin          — solve the Shin (1993) insider-trader model. The insider
                    fraction z is determined entirely by the two implied
                    probabilities (2 equations, 2 unknowns), so the output is
                    fully recompute-attributable: no external input enters.
  * multiplicative— proportional normalisation p_i = q_i / booksum.
  * power         — solve k so q_over^k + q_under^k = 1 (favourite-longshot
                    aware).

On Shin non-convergence or z outside [0, 1) the result falls back to
multiplicative and stamps devig_method='proportional_fallback' so the
degradation is visible in the data.
"""

from __future__ import annotations

import math

from engine.probability import implied_prob


def _shin_p_over(z: float, a_over: float, a_under: float) -> tuple[float, float]:
    """Shin true probs for a given insider fraction z (2-outcome closed form)."""
    booksum = a_over + a_under

    def p(a_i: float) -> float:
        root = math.sqrt(z * z + 4.0 * (1.0 - z) * a_i * a_i / booksum)
        return (root - z) / (2.0 * (1.0 - z))

    return p(a_over), p(a_under)


def devig_shin(over_odds: float, under_odds: float) -> tuple[float, float, float] | None:
    """Solve the Shin model for (p_over, p_under, z) from one price pair.

    Returns None if no valid z in [0, 1) makes the true probs sum to 1.
    """
    a_over = implied_prob(over_odds)
    a_under = implied_prob(under_odds)
    booksum = a_over + a_under
    if booksum <= 1.0:  # no vig to remove — nothing for Shin to do
        return a_over / booksum, a_under / booksum, 0.0

    def f(z: float) -> float:
        p_over, p_under = _shin_p_over(z, a_over, a_under)
        return p_over + p_under - 1.0

    # f(0) = sqrt(booksum) - 1 > 0; f rises toward the z->1 limit being <0 for
    # real two-way books, so bisect for the root.
    lo, hi = 0.0, 0.999999
    f_lo, f_hi = f(lo), f(hi)
    if f_lo == 0.0:
        z = 0.0
    elif f_lo * f_hi > 0:  # no sign change — Shin has no valid root here
        return None
    else:
        for _ in range(100):
            mid = (lo + hi) / 2.0
            if f(lo) * f(mid) <= 0:
                hi = mid
            else:
                lo = mid
        z = (lo + hi) / 2.0

    p_over, p_under = _shin_p_over(z, a_over, a_under)
    total = p_over + p_under
    return p_over / total, p_under / total, z


def devig_multiplicative(over_odds: float, under_odds: float) -> tuple[float, float]:
    a_over = implied_prob(over_odds)
    a_under = implied_prob(under_odds)
    total = a_over + a_under
    return a_over / total, a_under / total


def devig_power(over_odds: float, under_odds: float) -> tuple[float, float]:
    """Solve k so implied_over^k + implied_under^k = 1, then normalise."""
    a_over = implied_prob(over_odds)
    a_under = implied_prob(under_odds)
    total = a_over + a_under
    if total <= 1.0:
        return a_over / total, a_under / total
    lo, hi = 1.0, 10.0
    for _ in range(60):
        k = (lo + hi) / 2.0
        if a_over**k + a_under**k > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2.0
    p_over, p_under = a_over**k, a_under**k
    norm = p_over + p_under
    return p_over / norm, p_under / norm


def devig_two_sided(
    over_odds: float,
    under_odds: float,
    method: str = "shin",
) -> dict:
    """De-vig one book's two-sided price. Returns the identified per-book primitive.

    Result keys: p_over, p_under, devig_method (the method that actually
    produced the probs — may be 'proportional_fallback'), z (Shin only),
    hold (booksum, the two-way vig+1).
    """
    a_over = implied_prob(over_odds)
    a_under = implied_prob(under_odds)
    hold = a_over + a_under

    if method == "shin":
        result = devig_shin(over_odds, under_odds)
        if result is not None:
            p_over, p_under, z = result
            return {"p_over": p_over, "p_under": p_under,
                    "devig_method": "shin", "z": z, "hold": hold}
        # Shin failed to converge — degrade visibly.
        p_over, p_under = devig_multiplicative(over_odds, under_odds)
        return {"p_over": p_over, "p_under": p_under,
                "devig_method": "proportional_fallback", "z": None, "hold": hold}

    if method == "power":
        p_over, p_under = devig_power(over_odds, under_odds)
        return {"p_over": p_over, "p_under": p_under,
                "devig_method": "power", "z": None, "hold": hold}

    p_over, p_under = devig_multiplicative(over_odds, under_odds)
    return {"p_over": p_over, "p_under": p_under,
            "devig_method": "multiplicative", "z": None, "hold": hold}
