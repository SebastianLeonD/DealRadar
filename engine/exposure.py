"""Binding exposure caps + slip gating (council Pillars 3/4, OBJ-3/12/35/37).

Phase 1 ships the *binding* protections, not the full portfolio optimiser:

  * POWER per-leg gate is EXACT under independence (p^n * M = 1), so it is a
    legitimate per-leg filter. FLEX per-leg break-evens are NOT separable from
    the joint distribution of the legs, so FLEX is a screening heuristic only
    and never a slip-level gate (OBJ-35/39).

  * Same-game positive correlation is real and unmodelled in Phase 1, so the
    caps below are BINDING selection constraints (a blunt but honest proxy for
    rho): a hard per-game leg cap, a per-player cap, and a total-leg cap. These
    are not display-only warnings.

  * The displayed slip break-even is inflated by a conservative same-game
    correlation prior (rho0). This is an ASSERTED Phase-1 prior — positive
    correlation raises variance, so we demand a higher edge — and is replaced
    by the Phase-3 estimated correlation matrix once it clears the gate.
"""

from __future__ import annotations

from engine.config import RHO0_SAME_GAME
from engine.payout_table import POWER_PAYOUTS, power_breakeven

# Phase-1 binding caps (conservative defaults; live in config later if tuned).
MAX_LEGS_PER_GAME = 2
MAX_LEGS_PER_PLAYER = 1
MAX_TOTAL_LEGS = 6


def passes_power_gate(win_prob: float, n_legs: int) -> bool:
    """A leg clears the POWER gate iff its true win prob beats the break-even.

    Exact under independence; conservative (slightly strict) for positively
    correlated legs, which is the safe direction.
    """
    if n_legs not in POWER_PAYOUTS:
        return False
    return win_prob > power_breakeven(n_legs)


def correlation_adjusted_breakeven(n_legs: int, rho0: float = RHO0_SAME_GAME) -> float:
    """Per-leg break-even with a conservative same-game correlation PENALTY.

    This is a RISK adjustment, not an EV identity. On pure expected value,
    positive same-direction correlation actually *helps* a POWER slip (it lifts
    the all-hit probability), which would lower the required edge. But it also
    raises variance, so for disciplined selection we demand a higher per-leg
    win prob, never a lower one.

    The penalty is an explicit, asserted Phase-1 prior — a multiplicative bump
    that scales with rho0 and the correlated-leg fraction (n-1)/n:

        adjusted = base * (1 + rho0 * (n - 1) / n)

    With rho0 = 0 it is exactly the independent break-even. The Phase-3
    estimated correlation matrix replaces this once it clears the gate.
    """
    base = power_breakeven(n_legs)
    if rho0 <= 0 or n_legs <= 1:
        return base
    penalty = rho0 * (n_legs - 1) / n_legs
    return round(min(0.999, base * (1.0 + penalty)), 4)


def apply_exposure_caps(
    picks: list[dict],
    *,
    max_legs_per_game: int = MAX_LEGS_PER_GAME,
    max_legs_per_player: int = MAX_LEGS_PER_PLAYER,
    max_total_legs: int = MAX_TOTAL_LEGS,
) -> tuple[list[dict], list[dict]]:
    """Select legs under binding caps; the most-binding cap wins, ties drop the
    lowest edge.

    Each pick needs `win_prob` and `player`; `game_id` (preferred) or `team`
    keys the same-game cluster. Picks are considered strongest-first; a leg
    that would breach any cap is dropped with a reason. Returns (kept, dropped).
    """
    ordered = sorted(picks, key=lambda p: p.get('win_prob', 0.0), reverse=True)
    kept: list[dict] = []
    dropped: list[dict] = []
    per_game: dict[str, int] = {}
    per_player: dict[str, int] = {}

    for pick in ordered:
        if len(kept) >= max_total_legs:
            dropped.append({**pick, 'drop_reason': f'total-leg cap ({max_total_legs}) reached'})
            continue
        cluster = pick.get('game_id') or pick.get('team') or ''
        player = pick.get('player') or pick.get('pp_player_name') or ''

        if max_legs_per_player and per_player.get(player, 0) >= max_legs_per_player:
            dropped.append({**pick, 'drop_reason': f'per-player cap ({max_legs_per_player})'})
            continue
        if cluster and per_game.get(cluster, 0) >= max_legs_per_game:
            dropped.append({**pick, 'drop_reason': f'per-game cap ({max_legs_per_game}) for {cluster}'})
            continue

        kept.append(pick)
        per_game[cluster] = per_game.get(cluster, 0) + 1
        per_player[player] = per_player.get(player, 0) + 1

    return kept, dropped
