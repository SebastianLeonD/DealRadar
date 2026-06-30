"""Probability engine: de-vigging, line-ladder interpolation, EV, and slips.

Converts sharp-book prices into a true probability for ANY PrizePicks line,
not just the line the book happens to post. Two strategies:

1. Ladder interpolation — when a book posts alternate lines, fit a normal
   distribution through the two quantile points nearest the PP line.
2. Single-anchor fallback — with only one line, assume a normal with a
   dispersion heuristic calibrated to NBA player points and solve for the mean.
"""

from __future__ import annotations

import math
from itertools import combinations
from statistics import NormalDist

STD_NORMAL = NormalDist()

# Break-even win probability per pick for a PrizePicks 5/6 flex slip.
BREAKEVEN_PROB = 0.5425

# Verdict thresholds (per-pick true win probability).
PLAY_THRESHOLD = 0.57

# PrizePicks payout multipliers. Verify in-app occasionally; PP adjusts these.
POWER_PAYOUTS = {2: 3.0, 3: 5.0, 4: 10.0}
FLEX_PAYOUTS = {
    3: {3: 2.25, 2: 1.25},
    4: {4: 5.0, 3: 1.5},
    5: {5: 10.0, 4: 2.0, 3: 0.4},
    6: {6: 25.0, 5: 2.0, 4: 0.4},
}


def implied_prob(american_odds: float) -> float:
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100)
    return 100 / (american_odds + 100)


def devig_power(over_odds: float, under_odds: float) -> tuple[float, float]:
    """Power-method de-vig: solve k so that ip_over^k + ip_under^k = 1.

    Less biased than proportional de-vig on lopsided lines, where the
    favorite-longshot effect concentrates the vig on the longshot side.
    """
    ip_over = implied_prob(over_odds)
    ip_under = implied_prob(under_odds)

    total = ip_over + ip_under
    if total <= 1.0:  # no vig to remove (or arb) — proportional is exact enough
        return ip_over / total, ip_under / total

    low, high = 1.0, 10.0
    for _ in range(60):
        k = (low + high) / 2
        if ip_over**k + ip_under**k > 1.0:
            low = k
        else:
            high = k

    k = (low + high) / 2
    p_over, p_under = ip_over**k, ip_under**k
    norm = p_over + p_under
    return p_over / norm, p_under / norm


def devig_one_sided(odds: float, book_margin: float = 0.045) -> float:
    """De-vig a single-sided price (common on alternate lines).

    Assumes half the book's two-way margin sits on this side. Pass the
    margin measured from the same book's main line when available.
    """
    return min(0.999, implied_prob(odds) / (1 + book_margin / 2))


def _sigma_heuristic(mu: float) -> float:
    """Dispersion heuristic for NBA player points (std ~7 for a 25 ppg scorer)."""
    return 1.2 * math.sqrt(max(mu, 0.25)) + 1.0


def fit_mu_from_anchor(line: float, p_over: float) -> float:
    """Solve the distribution mean from one (line, P(over)) anchor point."""
    p_over = min(max(p_over, 0.001), 0.999)
    low, high = 0.25, 80.0
    for _ in range(60):
        mu = (low + high) / 2
        sigma = _sigma_heuristic(mu)
        if 1 - NormalDist(mu, sigma).cdf(line) < p_over:
            low = mu
        else:
            high = mu
    return (low + high) / 2


def _prob_from_single_anchor(line: float, p_over: float, target_line: float) -> float:
    mu = fit_mu_from_anchor(line, p_over)
    sigma = _sigma_heuristic(mu)
    return 1 - NormalDist(mu, sigma).cdf(target_line)


def _prob_from_pair(
    point_a: tuple[float, float],
    point_b: tuple[float, float],
    target_line: float,
) -> float | None:
    """Fit a normal through two quantile points: line_i = mu + sigma * z_i."""
    (line_a, p_a), (line_b, p_b) = point_a, point_b
    p_a = min(max(p_a, 0.001), 0.999)
    p_b = min(max(p_b, 0.001), 0.999)

    z_a = STD_NORMAL.inv_cdf(1 - p_a)
    z_b = STD_NORMAL.inv_cdf(1 - p_b)
    if abs(z_b - z_a) < 1e-9:
        return None

    sigma = (line_b - line_a) / (z_b - z_a)
    if not 0.5 <= sigma <= 25.0:  # probabilities not coherent across the lines
        return None

    mu = line_a - sigma * z_a
    return 1 - NormalDist(mu, sigma).cdf(target_line)


def _poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) for Poisson(lam), computed iteratively (no scipy)."""
    if k < 0:
        return 0.0
    term = math.exp(-lam)
    total = term
    for i in range(1, k + 1):
        term *= lam / i
        total += term
    return min(total, 1.0)


def poisson_p_over(lam: float, line: float) -> float:
    """P(X > line) for a Poisson count stat (line is typically x.5)."""
    return 1.0 - _poisson_cdf(math.floor(line), lam)


def poisson_p_over_push_adjusted(lam: float, line: float) -> float:
    """P(over) conditional on no push. Integer lines push when X == line
    (PrizePicks refunds the pick), so the win probability must exclude
    that mass: P(win over | no push) = P(X > L) / (1 - P(X = L))."""
    if line != int(line):
        return poisson_p_over(lam, line)
    over = poisson_p_over(lam, line)
    under = _poisson_cdf(int(line) - 1, lam)
    decided = over + under
    return over / decided if decided > 0 else 0.5


def push_conditional(p_over: float, line: float, p_push: float | None) -> float:
    """Renormalize a raw P(over) into push-conditional space on integer lines
    (Phase-2 calibration spec §0.1). Half-lines (x.5) and p_push None/0 are
    returned unchanged. On integer lines the push mass is carved out and the
    remaining decided mass renormalized: over / (over + under), with
    under = 1 - over - p_push. Returns 0.5 if no decided mass survives.
    """
    if line == int(line) and p_push:
        under = 1.0 - p_over - p_push
        decided = p_over + under
        return p_over / decided if decided > 0 else 0.5
    return p_over


def normal_p_over_push_adjusted(mu: float, sigma: float, line: float) -> float:
    """P(over | no push) for a Normal(mu, sigma), mirroring the Poisson path so
    both model families condition on no-push identically (Phase-2 spec §0.1).

    Half-line: 1 - cdf(line) (no push, returned unchanged). Integer line L for
    an integer-valued stat (X rounds to nearest integer): over wins on X > L+0.5,
    under on X < L-0.5, push on L-0.5 < X < L+0.5. So over = 1 - cdf(L+0.5),
    push mass = cdf(L+0.5) - cdf(L-0.5), renormalized via push_conditional. A
    centered Normal (mu == L) therefore returns exactly 0.5, as it must by
    symmetry. The Normal was previously unconditional on integer lines.
    """
    dist = NormalDist(mu, sigma)
    if line != int(line):
        return 1.0 - dist.cdf(line)
    over = 1.0 - dist.cdf(line + 0.5)
    p_push = dist.cdf(line + 0.5) - dist.cdf(line - 0.5)
    return push_conditional(over, line, p_push)


def fit_lambda_from_anchor(line: float, p_over: float) -> float:
    """Solve the Poisson rate from one (line, P(over)) anchor point."""
    p_over = min(max(p_over, 0.001), 0.999)
    low, high = 0.005, 80.0
    for _ in range(60):
        lam = (low + high) / 2
        if poisson_p_over(lam, line) < p_over:
            low = lam
        else:
            high = lam
    return (low + high) / 2


def clean_ladder(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Sort by line and drop points that break monotonicity (p_over must fall)."""
    cleaned: list[tuple[float, float]] = []
    for line, p_over in sorted(points):
        while cleaned and cleaned[-1][1] <= p_over:
            cleaned.pop()
        cleaned.append((line, p_over))
    return cleaned


def prob_over_at_line(
    ladder: list[tuple[float, float]],
    target_line: float,
    model: str = 'normal',
    rate_scale: float = 1.0,
) -> float | None:
    """P(over target_line) implied by a book's ladder of (line, p_over) points.

    model='normal' fits gaussians (high-count stats like NBA points);
    model='poisson' fits a discrete rate (low-count stats like soccer shots).

    rate_scale thins the Poisson rate before evaluating — used to derive
    partial-duration probabilities (e.g. first-half shots ≈ 45% of the
    full-match rate) from full-match prices.
    """
    points = clean_ladder(ladder)
    if not points:
        return None

    if rate_scale == 1.0:
        for line, p_over in points:
            if abs(line - target_line) < 1e-9:
                return p_over

    if model == 'poisson':
        anchor_line, anchor_prob = min(points, key=lambda pt: abs(pt[0] - target_line))
        lam = fit_lambda_from_anchor(anchor_line, anchor_prob) * rate_scale
        return poisson_p_over_push_adjusted(lam, target_line)

    if len(points) >= 2:
        nearest = sorted(points, key=lambda pt: abs(pt[0] - target_line))[:2]
        nearest.sort()
        estimate = _prob_from_pair(nearest[0], nearest[1], target_line)
        if estimate is not None:
            return estimate

    anchor_line, anchor_prob = min(points, key=lambda pt: abs(pt[0] - target_line))
    return _prob_from_single_anchor(anchor_line, anchor_prob, target_line)


def ev_percent(win_prob: float) -> float:
    """Edge over the flex break-even, in probability points."""
    return round((win_prob - BREAKEVEN_PROB) * 100, 2)


def assign_verdict(win_prob: float, flags: list[str]) -> str:
    if win_prob < BREAKEVEN_PROB:
        return 'NO'
    if flags:
        return 'LEAN'  # math says yes, but a trap flag demands a manual look
    if win_prob >= PLAY_THRESHOLD:
        return 'YES'
    return 'LEAN'


def _hit_distribution(probs: list[float]) -> list[float]:
    """P(exactly k hits) for independent picks, via dynamic programming."""
    dist = [1.0]
    for p in probs:
        nxt = [0.0] * (len(dist) + 1)
        for k, mass in enumerate(dist):
            nxt[k] += mass * (1 - p)
            nxt[k + 1] += mass * p
        dist = nxt
    return dist


def slip_ev(probs: list[float], structure: str) -> float | None:
    """EV per $1 staked for a slip of the given picks (assumes independence)."""
    n = len(probs)
    dist = _hit_distribution(probs)

    if structure == 'power':
        payout = POWER_PAYOUTS.get(n)
        if payout is None:
            return None
        return round(dist[n] * payout - 1, 4)

    payouts = FLEX_PAYOUTS.get(n)
    if payouts is None:
        return None
    expected = sum(dist[k] * payouts.get(k, 0.0) for k in range(n + 1))
    return round(expected - 1, 4)


# Fractional-Kelly multiplier. Full Kelly is brutally volatile on parlay
# products; a quarter-Kelly stake is the common conservative choice.
KELLY_MULTIPLIER = 0.25


def _slip_outcomes(probs: list[float], structure: str) -> list[tuple[float, float]] | None:
    """[(probability, gross_multiplier)] over k-of-n hits for a slip."""
    n = len(probs)
    dist = _hit_distribution(probs)
    if structure == 'power':
        payout = POWER_PAYOUTS.get(n)
        if payout is None:
            return None
        return [(dist[k], payout if k == n else 0.0) for k in range(n + 1)]
    payouts = FLEX_PAYOUTS.get(n)
    if payouts is None:
        return None
    return [(dist[k], payouts.get(k, 0.0)) for k in range(n + 1)]


def kelly_fraction(
    probs: list[float],
    structure: str,
    multiplier: float = KELLY_MULTIPLIER,
) -> float:
    """Growth-optimal bankroll fraction for a slip, scaled by fractional Kelly.

    Maximises expected log-growth over the slip's payout outcomes (assumes
    independent legs, like slip_ev). Returns 0 when the slip has no edge.
    """
    outcomes = _slip_outcomes(probs, structure)
    if not outcomes:
        return 0.0
    if sum(p * (m - 1.0) for p, m in outcomes) <= 0:  # no positive EV -> no bet
        return 0.0

    def growth(f: float) -> float:
        total = 0.0
        for p, m in outcomes:
            wealth = 1.0 - f + f * m
            if wealth <= 0:
                return float('-inf')
            total += p * math.log(wealth)
        return total

    lo, hi = 0.0, 0.999
    for _ in range(200):
        m1 = lo + (hi - lo) / 3.0
        m2 = hi - (hi - lo) / 3.0
        if growth(m1) < growth(m2):
            lo = m1
        else:
            hi = m2
    return round((lo + hi) / 2.0 * multiplier, 4)


def best_slips(picks: list[dict], max_picks: int = 6) -> list[dict]:
    """Rank slip structures over the strongest picks.

    `picks` need `win_prob`, `player`, and `team`; strongest picks first.
    Same-team picks are kept but flagged — correlated legs raise variance
    and PP may block some combos.
    """
    pool = sorted(picks, key=lambda p: p['win_prob'], reverse=True)[:max_picks]
    suggestions = []

    for size in range(2, min(len(pool), max_picks) + 1):
        legs = pool[:size]
        probs = [leg['win_prob'] for leg in legs]
        teams = [leg.get('team') or '' for leg in legs]
        correlated = len(set(teams)) < len(teams)

        for structure in ('power', 'flex'):
            ev = slip_ev(probs, structure)
            if ev is None:
                continue
            suggestions.append({
                'structure': f"{size}-pick {structure}",
                'players': [leg['player'] for leg in legs],
                'ev_per_dollar': ev,
                'ev_percent': round(ev * 100, 1),
                'kelly_pct': round(kelly_fraction(probs, structure) * 100, 1),
                'correlated_teams': correlated,
            })

    # Best slip = highest EV; on ties prefer fewer legs (lower variance).
    suggestions.sort(key=lambda s: (-s['ev_per_dollar'], s['structure']))
    return suggestions


def consensus_probability(book_probs: dict[str, float]) -> tuple[float, float]:
    """Average P(over) across books, plus max disagreement between books."""
    values = list(book_probs.values())
    avg = sum(values) / len(values)
    spread = max(values) - min(values) if len(values) > 1 else 0.0
    return avg, spread
