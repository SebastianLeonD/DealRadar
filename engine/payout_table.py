"""PrizePicks payout multipliers as a sourced, versioned primitive (OBJ-11/34).

EVERY EV, break-even, Kelly, and FLEX-simulation number reads from this table.
No multiplier or break-even literal may live anywhere else in the engine. Each
entry carries source_url + effective_date so it is auditable and updatable when
PrizePicks changes payouts.

POWER: pick N, all must hit; single multiplier per N.
FLEX:  pick N, tiered payout by number correct (partial credit).

The POWER per-leg break-even is exact under independence (p^n * M = 1), so it is
a legitimate per-leg gate. The FLEX per-leg break-even is NOT separable from the
joint distribution of the legs and is a screening heuristic ONLY (OBJ-35/39).
"""

from __future__ import annotations

SOURCE_URL = "https://prizepicks.com/how-to-play"
EFFECTIVE_DATE = "2026-06-30"

# board size -> multiplier (all legs must hit)
POWER_PAYOUTS: dict[int, float] = {
    2: 3.0,
    3: 5.0,
    4: 10.0,
    5: 20.0,
    6: 37.5,
}

# board size -> {number correct -> multiplier}
FLEX_PAYOUTS: dict[int, dict[int, float]] = {
    3: {3: 2.25, 2: 1.25},
    4: {4: 5.0, 3: 1.5},
    5: {5: 10.0, 4: 2.0, 3: 0.4},
    6: {6: 25.0, 5: 2.0, 4: 0.4},
}


def power_multiplier(n_legs: int) -> float:
    if n_legs not in POWER_PAYOUTS:
        raise KeyError(f"No POWER payout for {n_legs} legs (have {sorted(POWER_PAYOUTS)})")
    return POWER_PAYOUTS[n_legs]


def flex_ladder(n_legs: int) -> dict[int, float]:
    if n_legs not in FLEX_PAYOUTS:
        raise KeyError(f"No FLEX payout for {n_legs} legs (have {sorted(FLEX_PAYOUTS)})")
    return dict(FLEX_PAYOUTS[n_legs])


def power_breakeven(n_legs: int) -> float:
    """Per-leg true win prob that makes a POWER slip zero-EV under independence.

    p^n * M = 1  =>  p = M ** (-1/n). Exact only under independence; positive
    same-game correlation raises the all-hit probability, so this is a
    conservative (slightly high) required edge for correlated legs (OBJ-34).
    """
    return power_multiplier(n_legs) ** (-1.0 / n_legs)


def power_ev(per_leg_probs: list[float]) -> float:
    """EV per $1 staked on a POWER slip assuming independent legs.

    Returns multiplier * P(all hit) - 1.
    """
    n = len(per_leg_probs)
    p_all = 1.0
    for p in per_leg_probs:
        p_all *= p
    return power_multiplier(n) * p_all - 1.0
