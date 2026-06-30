"""Correlation-aware slip EV/variance/Kelly and slip construction (council OBJ-12/35/36/39).

The output layer: it turns a pool of flagged legs into ranked slip
recommendations whose EV, variance, and stake are computed under the same-game
correlation prior — not under the independence assumption that silently
mis-prices parlays.

Why simulation. FLEX payouts are a NON-MONOTONE function of leg correlation:
positive same-direction correlation fattens both tails, HELPING the all-hit
tier but HURTING the partial-hit (5/6, 4/6) tiers FLEX leans on. There is no
per-leg-separable formula for FLEX EV, so we evaluate it by a Gaussian-copula
Monte-Carlo over the leg outcomes (engine/correlation.py builds the copula).
POWER all-hit is evaluated the same way for consistency.

Sizing. The per-slip fractional Kelly is computed from the SIMULATED payout
distribution, so it is correlation-aware for a single slip. Full simultaneous
Kelly across slips that SHARE legs (a correlated portfolio of slips) is the
Phase-3 refinement; this module sizes each slip independently with a hard
fractional cap, which is the conservative direction.
"""

from __future__ import annotations

import math
from random import Random
from statistics import NormalDist

from engine.config import KELLY_FRACTION, RHO0_SAME_GAME
from engine.correlation import build_prior_corr, cholesky, correlated_normals
from engine.payout_table import FLEX_PAYOUTS, POWER_PAYOUTS, power_multiplier

_STD_NORMAL = NormalDist()
DEFAULT_SIMS = 10000
DEFAULT_SEED = 20260630
# A slip is too volatile to recommend above this payout-variance cap (per $1).
DEFAULT_VAR_CAP = 25.0
MAX_SLIP_LEGS = 6


def _payout_for_hits(structure: str, n_legs: int, hits: int) -> float:
    """Gross multiplier returned for `hits` correct of `n_legs` (0 = total loss)."""
    if structure == "power":
        return POWER_PAYOUTS.get(n_legs, 0.0) if hits == n_legs else 0.0
    return FLEX_PAYOUTS.get(n_legs, {}).get(hits, 0.0)


def _kelly_from_outcomes(payouts: list[float], multiplier: float = KELLY_FRACTION) -> float:
    """Fractional Kelly from an empirical payout sample (equal-weight draws).

    Maximises mean(log(1 - f + f * m)) over the simulated gross multipliers m by
    golden-section search on f in [0, 1); returns 0 when the slip has no edge.
    Scaled by the conservative fractional multiplier.
    """
    if not payouts:
        return 0.0
    if sum(m - 1.0 for m in payouts) <= 0:  # non-positive EV -> no bet
        return 0.0

    def growth(f: float) -> float:
        total = 0.0
        for m in payouts:
            wealth = 1.0 - f + f * m
            if wealth <= 0:
                return float("-inf")
            total += math.log(wealth)
        return total / len(payouts)

    lo, hi = 0.0, 0.999
    gr = (math.sqrt(5) - 1) / 2
    a, b = hi - gr * (hi - lo), lo + gr * (hi - lo)
    fa, fb = growth(a), growth(b)
    for _ in range(80):
        if fa < fb:
            lo, a, fa = a, b, fb
            b = lo + gr * (hi - lo)
            fb = growth(b)
        else:
            hi, b, fb = b, a, fa
            a = hi - gr * (hi - lo)
            fa = growth(a)
    return round(max(0.0, (lo + hi) / 2) * multiplier, 4)


def simulate_slip(
    probs: list[float],
    game_ids: list,
    structure: str,
    *,
    rho0: float = RHO0_SAME_GAME,
    n_sims: int = DEFAULT_SIMS,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Correlation-aware EV / variance / Kelly for one slip via a Gaussian copula.

    Each leg wins with its marginal win probability; same-game legs co-move with
    latent correlation rho0. Returns ev_per_dollar, ev_percent, variance, std,
    kelly_pct, p_all_hit, and the hit-count distribution. Deterministic by seed.
    """
    n = len(probs)
    L = cholesky(build_prior_corr(game_ids, rho0))
    rng = Random(seed)
    thresholds = [_STD_NORMAL.inv_cdf(min(max(p, 1e-9), 1 - 1e-9)) for p in probs]

    payouts: list[float] = []
    hit_counts = [0] * (n + 1)
    all_hits = 0
    for _ in range(n_sims):
        z = correlated_normals(L, [rng.gauss(0.0, 1.0) for _ in range(n)])
        # Leg i wins when its latent draw falls below Phi^-1(p_i): P = p_i.
        hits = sum(1 for i in range(n) if z[i] < thresholds[i])
        hit_counts[hits] += 1
        if hits == n:
            all_hits += 1
        payouts.append(_payout_for_hits(structure, n, hits))

    mean_payout = sum(payouts) / n_sims
    ev = mean_payout - 1.0
    var = sum((m - mean_payout) ** 2 for m in payouts) / n_sims
    return {
        "structure": structure,
        "n_legs": n,
        "ev_per_dollar": round(ev, 4),
        "ev_percent": round(ev * 100, 2),
        "variance": round(var, 4),
        "std": round(math.sqrt(var), 4),
        "kelly_pct": round(_kelly_from_outcomes(payouts) * 100, 2),
        "p_all_hit": all_hits / n_sims,
        "hit_distribution": [c / n_sims for c in hit_counts],
    }


def construct_slips(
    picks: list[dict],
    *,
    rho0: float = RHO0_SAME_GAME,
    max_slips: int = 3,
    var_cap: float = DEFAULT_VAR_CAP,
    n_sims: int = DEFAULT_SIMS,
    seed: int = DEFAULT_SEED,
    max_legs: int = MAX_SLIP_LEGS,
) -> list[dict]:
    """Rank slip recommendations by correlation-aware EV subject to a variance
    cap (council OBJ-12/35).

    `picks` are pre-selected, exposure-capped legs (strongest first), each with
    `win_prob`, `player`, and `game_id` (or `team`). Enumerates POWER and FLEX
    slips over the strongest legs, simulates each under the correlation prior,
    keeps positive-EV slips within the variance cap, and returns the top
    `max_slips` by EV. FLEX EV/variance come ONLY from the joint simulation.
    """
    pool = sorted(picks, key=lambda p: p.get("win_prob", 0.0), reverse=True)[:max_legs]
    suggestions: list[dict] = []

    for size in range(2, len(pool) + 1):
        legs = pool[:size]
        probs = [leg["win_prob"] for leg in legs]
        game_ids = [leg.get("game_id") or leg.get("team") for leg in legs]
        correlated = len({g for g in game_ids if g is not None}) < len([g for g in game_ids if g is not None])

        for structure in ("power", "flex"):
            if structure == "power" and size not in POWER_PAYOUTS:
                continue
            if structure == "flex" and size not in FLEX_PAYOUTS:
                continue
            sim = simulate_slip(probs, game_ids, structure, rho0=rho0,
                                n_sims=n_sims, seed=seed)
            if sim["ev_per_dollar"] <= 0 or sim["variance"] > var_cap:
                continue
            suggestions.append({
                "structure": f"{size}-pick {structure}",
                "players": [leg["player"] for leg in legs],
                "ev_per_dollar": sim["ev_per_dollar"],
                "ev_percent": sim["ev_percent"],
                "variance": sim["variance"],
                "std": sim["std"],
                "kelly_pct": sim["kelly_pct"],
                "p_all_hit": round(sim["p_all_hit"], 4),
                "correlated_legs": correlated,
            })

    # Highest EV first; on ties prefer lower variance (steadier growth).
    suggestions.sort(key=lambda s: (-s["ev_per_dollar"], s["variance"]))
    return suggestions[:max_slips]
