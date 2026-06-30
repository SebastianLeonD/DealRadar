"""Phase-2 settled-outcome calibration gate (council OBJ-9/10/31).

This module MEASURES whether a probability source is honest on realized
outcomes, and GATES: nothing asserted may flag a bet until it out-Briers the
identified consensus null out-of-sample, per regime, on enough independent
game-nights. It never fits a calibration map — the walk-forward isotonic map is
Phase 3; Phase 2 only measures and gates.

Pure Python (math, statistics.NormalDist, random.Random with a fixed seed). No
numpy/scipy/statsmodels/sklearn.

Pipeline (one direction, no cycles):
  settled edges -> gather_scored_legs (dedup, cluster-key) -> assign_strata
  (collapse hierarchy) -> per stratum {clustered bootstrap-t Brier p-value,
  reliability-slope CI} -> Benjamini-Hochberg FDR across the tested family ->
  classify each stratum {CALIBRATED | PENDING | FAILED}.

Key invariants (Phase-2 spec):
  * The scored event is FIXED OVER (no side-selection leakage); consensus_p and
    baseline_p are both raw P(over), push-conditionally renormalized on integer
    lines; PUSH rows are excluded entirely.
  * Every clustered statistic abstains below MIN_CLUSTERS_FOR_TEST distinct
    games; CALIBRATED additionally requires MIN_INDEPENDENT_GAMES distinct games.
  * Both the paired-Brier FDR test AND the reliability-slope point-null
    ("CI covers 1.0") must pass — they are co-primary.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import NormalDist

from engine.config import (
    CALIB_BOOTSTRAP_R,
    CALIB_BOOTSTRAP_SEED,
    CONFIG_VERSION,
    FDR_ALPHA,
    HOLD_CEILING,
    MIN_CLUSTERS_FOR_TEST,
    MIN_INDEPENDENT_GAMES,
    SE_DEGENERACY_REL,
)
from engine.config import BOOK_PRIORITY

_STD_NORMAL = NormalDist()

# Line-band cutoffs (snapped to the half-point grid). Family by stat.
BINARY_STATS = {"player_goal_scorer_anytime"}
_BAND_CUTOFFS = {"player_points": (14.5, 22.5)}
_DEFAULT_CUTOFFS = (2.5, 5.5)


# ---------------------------------------------------------------------------
# Numerical helpers (pure Python)
# ---------------------------------------------------------------------------
def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1.0 - 1e-6)
    return math.log(p / (1.0 - p))


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    ez = math.exp(z)
    return ez / (1.0 + ez)


def t_crit(q: float, df: int) -> float:
    """Student-t quantile via a Cornish-Fisher expansion of the normal quantile.

    For df >= ~29 (our gate floor is G-1 with G >= 30) this is within a fraction
    of a percent of the true t quantile, with no scipy dependency.
    """
    if df <= 0:
        return float("inf")
    z = _STD_NORMAL.inv_cdf(q)
    g1 = (z ** 3 + z) / 4.0
    g2 = (5 * z ** 5 + 16 * z ** 3 + 3 * z) / 96.0
    g3 = (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / 384.0
    return z + g1 / df + g2 / (df ** 2) + g3 / (df ** 3)


def chi2_2_quantile(level: float) -> float:
    """Inverse CDF of a chi-square with 2 dof: -2 ln(1 - level)."""
    return -2.0 * math.log(1.0 - level)


def _inv2x2(m: list[list[float]]) -> list[list[float]] | None:
    a, b = m[0]
    c, d = m[1]
    det = a * d - b * c
    if det == 0 or not math.isfinite(det):
        return None
    return [[d / det, -b / det], [-c / det, a / det]]


# ---------------------------------------------------------------------------
# Probability atoms — the canonical (fixed-OVER) event layer
# ---------------------------------------------------------------------------
def brier(p: float, outcome: int) -> float:
    """Brier score (p - outcome)**2. Rejects bools (True/False are not
    probabilities/outcomes) and out-of-range / non-finite inputs."""
    if isinstance(p, bool) or isinstance(outcome, bool):
        raise ValueError("brier: bool is not a valid probability/outcome")
    if not isinstance(p, (int, float)) or not math.isfinite(p) or not (0.0 <= p <= 1.0):
        raise ValueError(f"brier: p out of range or non-finite: {p!r}")
    if outcome not in (0, 1):
        raise ValueError(f"brier: outcome must be 0 or 1: {outcome!r}")
    return (p - outcome) ** 2


def paired_brier_diff(consensus_p: float, baseline_p: float, outcome_over: int) -> float:
    """Per-leg d = Brier(consensus) - Brier(baseline) on the fixed-OVER event.

    Consensus strictly better => d < 0. Both args are raw P(over) (already
    push-conditionally renormalized by the caller on integer lines).
    """
    return brier(consensus_p, outcome_over) - brier(baseline_p, outcome_over)


# ---------------------------------------------------------------------------
# Settled-row substrate
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScoredLeg:
    """One settled, identified, deduped leg eligible for the Brier/slope test."""

    leg_id: str
    cluster: str            # "GID:<game_id>" or "DATE:<sport>|<game_date>"
    sport: str
    stat_type: str
    line_band: str
    edge_type: str
    pp_line: float
    consensus_p: float      # raw P(over), push-conditional on integer lines
    baseline_p: float       # single-sharpest-book raw P(over), push-conditional
    win_prob_raw: float | None
    outcome_over: int       # 1 over won, 0 over lost (PUSH already excluded)


@dataclass(frozen=True)
class StratumVerdict:
    level: int
    key: tuple
    verdict: str
    n_independent_games: int
    n_legs: int
    brier_p: float | None
    brier_p_adjusted: float | None
    bh_rejected: bool
    point_mean_d: float | None
    slope_b1: float | None
    slope_ci: tuple | None
    slope_ok: bool | None
    config_version: str = CONFIG_VERSION


# ---------------------------------------------------------------------------
# Clustered bootstrap-t (Cameron-Gelbach-Miller), one-sided
# ---------------------------------------------------------------------------
def _cluster_aggregates(values: list[float], clusters: list[str]):
    sum_by: dict[str, float] = {}
    cnt_by: dict[str, int] = {}
    for v, c in zip(values, clusters):
        sum_by[c] = sum_by.get(c, 0.0) + v
        cnt_by[c] = cnt_by.get(c, 0) + 1
    keys = list(sum_by)
    return [sum_by[k] for k in keys], [cnt_by[k] for k in keys]


def _clustered_se_of_mean(sum_d: list[float], cnt: list[int], xbar: float) -> float | None:
    """CR0 clustered SE of the pooled mean with a finite-G G/(G-1) scale."""
    g = len(sum_d)
    if g < 2:
        return None
    n = sum(cnt)
    meat = sum((sum_d[i] - cnt[i] * xbar) ** 2 for i in range(g))
    var = (g / (g - 1.0)) * meat / (n * n)
    if var <= 0 or not math.isfinite(var):
        return None
    return math.sqrt(var)


def bootstrap_t_pvalue(
    values: list[float],
    clusters: list[str],
    *,
    r: int = CALIB_BOOTSTRAP_R,
    seed: int = CALIB_BOOTSTRAP_SEED,
    min_clusters: int = MIN_CLUSTERS_FOR_TEST,
) -> dict:
    """One-sided game-clustered bootstrap-t for H0: mean d >= 0 vs H1: mean d < 0.

    Recentered studentized statistic: resample whole clusters with replacement,
    t_b = (xbar_b - xbar) / se_b; p = (#{t_b <= t_obs} + 1) / (valid + 1).
    Abstains (status='insufficient', p_value=None) below min_clusters distinct
    clusters or when d is effectively constant (no real dispersion).
    """
    n = len(values)
    sum_d, cnt = _cluster_aggregates(values, clusters)
    g = len(sum_d)
    if g < min_clusters:
        return {"status": "insufficient", "p_value": None, "point": None,
                "n_clusters": g, "n_rows": n}

    xbar = sum(values) / n
    tss = sum((v - xbar) ** 2 for v in values)
    if tss <= SE_DEGENERACY_REL * n:  # constant d: a nanopoint edge must not reject
        return {"status": "insufficient", "p_value": None, "point": xbar,
                "n_clusters": g, "n_rows": n}

    se = _clustered_se_of_mean(sum_d, cnt, xbar)
    if se is None:
        return {"status": "insufficient", "p_value": None, "point": xbar,
                "n_clusters": g, "n_rows": n}
    t_obs = xbar / se

    rng = random.Random(seed)
    scale = g / (g - 1.0)
    le = 0
    valid = 0
    for _ in range(r):
        idx = [rng.randrange(g) for _ in range(g)]
        nb = 0
        sdb = 0.0
        for j in idx:
            nb += cnt[j]
            sdb += sum_d[j]
        xbar_b = sdb / nb
        meat_b = 0.0
        for j in idx:
            meat_b += (sum_d[j] - cnt[j] * xbar_b) ** 2
        var_b = scale * meat_b / (nb * nb)
        if var_b <= 0 or not math.isfinite(var_b):
            continue
        t_b = (xbar_b - xbar) / math.sqrt(var_b)
        if t_b <= t_obs:
            le += 1
        valid += 1

    p = (le + 1) / (valid + 1)
    return {"status": "ok", "p_value": p, "point": xbar,
            "n_clusters": g, "n_rows": n}


def clustered_brier_pvalue(legs: list[ScoredLeg], **kwargs) -> dict:
    """Bootstrap-t one-sided p-value over per-leg paired Brier differences."""
    values = [paired_brier_diff(lg.consensus_p, lg.baseline_p, lg.outcome_over) for lg in legs]
    clusters = [lg.cluster for lg in legs]
    return bootstrap_t_pvalue(values, clusters, **kwargs)


# ---------------------------------------------------------------------------
# Design effect / effective sample size (reporting)
# ---------------------------------------------------------------------------
def design_effect(values: list[float], clusters: list[str]) -> dict:
    """One-way-ANOVA intraclass correlation, design effect, and ESS.

    icc clamped to [0, 1]; deff = 1 + (mbar - 1) * icc >= 1; n_eff = n / deff <= n.
    """
    sum_d, cnt = _cluster_aggregates(values, clusters)
    g = len(sum_d)
    n = sum(cnt)
    if g < 2 or n <= g:
        return {"icc": 0.0, "deff": 1.0, "n_eff": float(n), "n": n, "g": g}

    xbar = sum(values) / n
    means = [sum_d[i] / cnt[i] for i in range(g)]
    ssb = sum(cnt[i] * (means[i] - xbar) ** 2 for i in range(g))
    by_cluster: dict[str, list[float]] = {}
    for v, c in zip(values, clusters):
        by_cluster.setdefault(c, []).append(v)
    ssw = sum((v - sum(vs) / len(vs)) ** 2 for vs in by_cluster.values() for v in vs)

    msb = ssb / (g - 1)
    msw = ssw / (n - g)
    m0 = (n - sum(c * c for c in cnt) / n) / (g - 1)
    denom = msb + (m0 - 1) * msw
    icc = 0.0 if denom <= 0 else (msb - msw) / denom
    icc = min(1.0, max(0.0, icc))
    mbar = n / g
    deff = max(1.0, 1.0 + (mbar - 1) * icc)
    return {"icc": icc, "deff": deff, "n_eff": n / deff, "n": n, "g": g}


# ---------------------------------------------------------------------------
# Reliability-slope logistic regression with cluster-robust SEs
# ---------------------------------------------------------------------------
def _irls_fit(rows: list[tuple[float, int]], max_iter: int = 50, tol: float = 1e-9):
    """IRLS/Newton logistic fit of y on [1, x]. Returns (b0, b1) or None.

    A tiny ridge stabilises the Newton STEP only; the returned coefficients are
    the un-ridged MLE at convergence.
    """
    b0, b1 = 0.0, 0.0
    ridge = 1e-8
    for _ in range(max_iter):
        g0 = g1 = 0.0
        h00 = h01 = h11 = 0.0
        for x, y in rows:
            p = _sigmoid(b0 + b1 * x)
            w = max(p * (1.0 - p), 1e-12)
            resid = y - p
            g0 += resid
            g1 += resid * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        hess = [[h00 + ridge, h01], [h01, h11 + ridge]]
        inv = _inv2x2(hess)
        if inv is None:
            return None
        d0 = inv[0][0] * g0 + inv[0][1] * g1
        d1 = inv[1][0] * g0 + inv[1][1] * g1
        b0 += d0
        b1 += d1
        if abs(d0) < tol and abs(d1) < tol:
            if not (math.isfinite(b0) and math.isfinite(b1)):
                return None
            return b0, b1
    return None


def _cluster_sandwich_se_b1(rows, clusters, b0, b1):
    """CR0 cluster-robust sandwich SE for the slope. Bread is the UN-ridged
    (X'WX)^-1; meat sums per-cluster score outer products with a G/(G-1) scale.
    Returns (se_b1, G) or (None, G)."""
    h00 = h01 = h11 = 0.0
    score_by: dict[str, list[float]] = {}
    for (x, y), c in zip(rows, clusters):
        p = _sigmoid(b0 + b1 * x)
        w = max(p * (1.0 - p), 1e-12)
        h00 += w
        h01 += w * x
        h11 += w * x * x
        s = score_by.setdefault(c, [0.0, 0.0])
        resid = y - p
        s[0] += resid
        s[1] += resid * x
    bread = _inv2x2([[h00, h01], [h01, h11]])
    g = len(score_by)
    if bread is None or g < 2:
        return None, g
    m00 = m01 = m11 = 0.0
    for s0, s1 in score_by.values():
        m00 += s0 * s0
        m01 += s0 * s1
        m11 += s1 * s1
    scale = g / (g - 1.0)
    m00 *= scale; m01 *= scale; m11 *= scale
    # V = bread * meat * bread ; we need V[1][1].
    bm10 = bread[1][0] * m00 + bread[1][1] * m01
    bm11 = bread[1][0] * m01 + bread[1][1] * m11
    v11 = bm10 * bread[1][0] + bm11 * bread[1][1]
    if v11 <= 0 or not math.isfinite(v11):
        return None, g
    return math.sqrt(v11), g


def reliability_slope(legs: list[ScoredLeg], *, min_clusters: int = MIN_CLUSTERS_FOR_TEST) -> dict:
    """Game-clustered reliability-slope logistic (PRIMARY go/no-go).

    Fits logit(P[outcome_over=1]) = b0 + b1 * logit(consensus_p). Perfect
    calibration is b1 == 1. slope_ok is the point-null "CI covers 1.0". Abstains
    (slope_ok=None) below min_clusters games, with one outcome class, no logit
    spread, a singular fit, or non-convergence.
    """
    g_distinct = len({lg.cluster for lg in legs})
    base = {"status": "insufficient", "b0": None, "b1": None,
            "slope_lo": None, "slope_hi": None, "slope_ok": None,
            "n_clusters": g_distinct}
    if g_distinct < min_clusters:
        return base
    ys = {lg.outcome_over for lg in legs}
    if len(ys) < 2:
        return base
    rows = [(_logit(lg.consensus_p), lg.outcome_over) for lg in legs]
    xs = [x for x, _ in rows]
    if max(xs) - min(xs) < 1e-9:  # no predictor spread
        return base
    fit = _irls_fit(rows)
    if fit is None:
        return base
    b0, b1 = fit
    clusters = [lg.cluster for lg in legs]
    se, g = _cluster_sandwich_se_b1(rows, clusters, b0, b1)
    if se is None:
        return base
    crit = t_crit(0.975, g - 1)
    lo, hi = b1 - crit * se, b1 + crit * se
    return {"status": "ok", "b0": b0, "b1": b1,
            "slope_lo": lo, "slope_hi": hi,
            "slope_ok": lo <= 1.0 <= hi, "n_clusters": g}


# ---------------------------------------------------------------------------
# Benjamini-Hochberg FDR
# ---------------------------------------------------------------------------
def benjamini_hochberg(pvals: list, alpha: float = FDR_ALPHA) -> tuple[list[bool], int]:
    """BH(1995) step-up FDR. The integer k* is the SOLE reject authority — a
    persisted adjusted p must never be re-thresholded. None-valued (abstained)
    strata are excluded from m and never rejected.
    """
    indexed = [(p, i) for i, p in enumerate(pvals) if p is not None]
    m = len(indexed)
    rejected = [False] * len(pvals)
    if m == 0:
        return rejected, 0
    indexed.sort(key=lambda t: t[0])
    k_star = 0
    for rank, (p, _) in enumerate(indexed, start=1):
        if p <= (rank / m) * alpha:
            k_star = rank
    for rank, (_, original_i) in enumerate(indexed, start=1):
        if rank <= k_star:
            rejected[original_i] = True
    return rejected, k_star


def bh_adjusted(pvals: list, alpha: float = FDR_ALPHA) -> list:
    """Report-only BH-adjusted p-values (monotone). k* still governs rejection."""
    indexed = sorted(((p, i) for i, p in enumerate(pvals) if p is not None), key=lambda t: t[0])
    m = len(indexed)
    adj = [None] * len(pvals)
    prev = 1.0
    for rank in range(m, 0, -1):
        p, original_i = indexed[rank - 1]
        val = min(prev, p * m / rank)
        adj[original_i] = val
        prev = val
    return adj


# ---------------------------------------------------------------------------
# Strata partition (game-disjoint collapse hierarchy)
# ---------------------------------------------------------------------------
def line_band(stat_type: str, pp_line: float) -> str:
    """Deterministic, float-safe line band. Snaps to the half-point grid so
    round-trip float noise never flips a band."""
    if stat_type in BINARY_STATS:
        return "binary"
    snapped = round(pp_line * 2) / 2.0
    lo, hi = _BAND_CUTOFFS.get(stat_type, _DEFAULT_CUTOFFS)
    if snapped < lo:
        return "low"
    if snapped < hi:
        return "mid"
    return "high"


def _game_level_key(legs: list[ScoredLeg], level: int):
    """The key a whole game shares at a level, or None if its legs disagree.

    Game-disjointness (each game in exactly one stratum) requires assigning a
    game to a finer stratum only when all its legs agree on that level's key.
    """
    if level == 0:
        keys = {(lg.sport, lg.stat_type, lg.line_band, lg.edge_type) for lg in legs}
    elif level == 1:
        keys = {(lg.sport, lg.stat_type, lg.edge_type) for lg in legs}
    elif level == 2:
        keys = {(lg.sport, lg.stat_type) for lg in legs}
    else:
        keys = {(lg.sport,) for lg in legs}
    return next(iter(keys)) if len(keys) == 1 else None


def assign_strata(
    legs: list[ScoredLeg],
    *,
    min_independent_games: int = MIN_INDEPENDENT_GAMES,
) -> list[tuple[int, tuple, list[ScoredLeg]]]:
    """Game-disjoint residual-pool collapse (spec line 77).

    Order: (sport,stat,line_band,edge_type) -> collapse line_band ->
    collapse edge_type -> (sport,stat) -> floor (sport,). A group graduates to
    a gated stratum only when its residual pool has >= min_independent_games
    distinct games; otherwise its games fall through to the next coarser level.
    The floor emits every remaining game (possibly still short -> PENDING).
    """
    games: dict[str, list[ScoredLeg]] = {}
    for lg in legs:
        games.setdefault(lg.cluster, []).append(lg)

    remaining = dict(games)
    result: list[tuple[int, tuple, list[ScoredLeg]]] = []

    for level in (0, 1, 2, 3):
        groups: dict[tuple, list[str]] = {}
        for cluster, glegs in remaining.items():
            key = _game_level_key(glegs, level)
            if key is None:
                continue  # legs disagree at this level -> consider at a coarser one
            groups.setdefault(key, []).append(cluster)

        for key, clusters in groups.items():
            graduates = level == 3 or len(clusters) >= min_independent_games
            if not graduates:
                continue
            members = [lg for c in clusters for lg in remaining[c]]
            result.append((level, key, members))
            for c in clusters:
                remaining.pop(c, None)

        if not remaining:
            break

    return result


# ---------------------------------------------------------------------------
# Baseline book selection
# ---------------------------------------------------------------------------
def select_sharpest_book(
    book_over_probs: dict[str, float],
    *,
    book_holds: dict[str, float] | None = None,
    hold_ceiling: float = HOLD_CEILING,
    book_priority: tuple = BOOK_PRIORITY,
) -> tuple[str, float] | None:
    """Single-sharpest-book baseline (OBJ-31). Eligible iff hold <= ceiling
    (missing hold defaults to 1.0, a fair book). Highest-priority eligible book
    wins (pinnacle first); unknown books rank last then lexicographic. Returns
    (book, raw P(over)) or None — never side-signed."""
    holds = book_holds or {}
    eligible = [b for b in book_over_probs if holds.get(b, 1.0) <= hold_ceiling]
    if not eligible:
        return None

    def rank(book: str):
        try:
            return (0, book_priority.index(book), book)
        except ValueError:
            return (1, len(book_priority), book)

    best = min(eligible, key=rank)
    return best, book_over_probs[best]


# ---------------------------------------------------------------------------
# Verdict classification + time-to-first-verdict
# ---------------------------------------------------------------------------
def classify(games_met: bool, bh_rejected: bool, slope_ok, point_mean_d) -> str:
    """Co-primary verdict. CALIBRATED iff the games floor is met AND the paired-
    Brier FDR test rejects AND the reliability slope covers 1.0. FAILED iff the
    test ran and consensus failed to beat baseline or the slope decisively
    excludes 1.0. PENDING otherwise (insufficient or favorable-not-significant).
    """
    if games_met and bh_rejected and slope_ok is True:
        return "CALIBRATED"
    tested = point_mean_d is not None
    if games_met and tested and not bh_rejected and (
        (point_mean_d is not None and point_mean_d >= 0) or slope_ok is False
    ):
        return "FAILED"
    if games_met and bh_rejected and slope_ok is False:
        return "FAILED"
    return "PENDING"


def time_to_first_verdict(
    pending_games: int,
    game_dates: list[str],
    window_days: int,
    floor: int = MIN_INDEPENDENT_GAMES,
) -> dict:
    """Dashboard 'verdict pending, N/floor games (~eta_days)'. Rate uses the
    elapsed window as denominator so a one-slate burst never reads as an
    infinite accrual rate."""
    rate = len(game_dates) / max(1, window_days)
    remaining = max(0, floor - pending_games)
    eta_days = None if rate <= 0 else math.ceil(remaining / max(rate, 1e-9))
    return {"have": pending_games, "floor": floor, "rate_per_day": rate,
            "eta_days": 0 if remaining == 0 else eta_days}


# ---------------------------------------------------------------------------
# Settled-row read (DB)
# ---------------------------------------------------------------------------
_READ_SQL = """
SELECT cluster, sport, stat_type, line_band, edge_type, pp_line,
       consensus_p, baseline_p, win_prob_raw, outcome_over, leg_id
FROM (
  SELECT
    CASE WHEN game_id IS NOT NULL AND game_id <> '' THEN 'GID:' || game_id
         WHEN game_date IS NOT NULL THEN 'DATE:' || sport || '|' || game_date
    END AS cluster,
    sport, stat_type, line_band, edge_type, pp_line,
    consensus_p, baseline_p, win_prob_raw, outcome_over,
    CAST(id AS TEXT) AS leg_id,
    ROW_NUMBER() OVER (
      PARTITION BY pp_player_name, stat_type, play, pp_line, game_id, snapshot_bucket
      ORDER BY settled_at DESC, id DESC) AS rn
  FROM edges
  WHERE settlement_status = 'SCORED' AND outcome_over IS NOT NULL
    AND consensus_tag = 'identified' AND void_reason IS NULL AND partial_game = 0
    AND consensus_p IS NOT NULL AND baseline_p IS NOT NULL
    AND config_version IS NOT NULL
)
WHERE rn = 1 AND cluster IS NOT NULL
"""


def gather_scored_legs(connection, *, config_version: str | None = None) -> tuple[list[ScoredLeg], dict]:
    """Pull settled, identified, deduped, cluster-keyed legs for the test.

    Probabilities are unit-guarded to [0, 1] (props.true_over_prob is percent;
    the caller must divide by 100 before persisting). Raises on a percent leak.
    """
    rows = connection.execute(_READ_SQL).fetchall()
    legs: list[ScoredLeg] = []
    diagnostics = {"rows": len(rows), "kept": 0, "skipped_config": 0}
    for row in rows:
        d = dict(row)
        for field in ("consensus_p", "baseline_p"):
            v = d[field]
            if v is None or not (0.0 <= v <= 1.0):
                raise ValueError(
                    f"gather_scored_legs: {field}={v!r} outside [0,1] "
                    "(percent leak? divide true_over_prob by 100)"
                )
        wpr = d["win_prob_raw"]
        if wpr is not None and not (0.0 <= wpr <= 1.0):
            raise ValueError(f"gather_scored_legs: win_prob_raw={wpr!r} outside [0,1]")
        legs.append(ScoredLeg(
            leg_id=d["leg_id"], cluster=d["cluster"], sport=(d["sport"] or "").lower(),
            stat_type=d["stat_type"], line_band=d["line_band"] or line_band(d["stat_type"], d["pp_line"]),
            edge_type=(d["edge_type"] or "").lower().replace(" ", "_"),
            pp_line=d["pp_line"], consensus_p=d["consensus_p"], baseline_p=d["baseline_p"],
            win_prob_raw=wpr, outcome_over=int(d["outcome_over"]),
        ))
    diagnostics["kept"] = len(legs)
    return legs, diagnostics


# ---------------------------------------------------------------------------
# End-to-end gate
# ---------------------------------------------------------------------------
def run_calibration(
    connection=None,
    legs: list[ScoredLeg] | None = None,
    *,
    config_version: str | None = None,
    r: int = CALIB_BOOTSTRAP_R,
    seed: int = CALIB_BOOTSTRAP_SEED,
    min_independent_games: int = MIN_INDEPENDENT_GAMES,
    min_clusters: int = MIN_CLUSTERS_FOR_TEST,
    alpha: float = FDR_ALPHA,
) -> dict:
    """Run the full Phase-2 gate. Pass a DB connection (read settled edges) or a
    pre-built list of ScoredLeg (for testing). Returns strata verdicts +
    diagnostics; reproducible under the fixed seed.
    """
    diagnostics = {"source": "legs" if legs is not None else "db"}
    if legs is None:
        if connection is None:
            raise ValueError("run_calibration needs a connection or legs")
        legs, gather_diag = gather_scored_legs(connection, config_version=config_version)
        diagnostics.update(gather_diag)

    strata = assign_strata(legs, min_independent_games=min_independent_games)

    interim = []
    for level, key, members in strata:
        n_games = len({lg.cluster for lg in members})
        games_met = n_games >= min_independent_games
        if games_met:
            bp = clustered_brier_pvalue(members, r=r, seed=seed, min_clusters=min_clusters)
            sl = reliability_slope(members, min_clusters=min_clusters)
        else:
            bp = {"status": "insufficient", "p_value": None, "point": None}
            sl = {"slope_ok": None, "b1": None, "slope_lo": None, "slope_hi": None}
        interim.append((level, key, members, n_games, games_met, bp, sl))

    # BH only over the Brier p-values of games-met strata (None excluded from m).
    pvals = [(bp["p_value"] if games_met else None) for (_, _, _, _, games_met, bp, _) in interim]
    rejected, k_star = benjamini_hochberg(pvals, alpha=alpha)
    adjusted = bh_adjusted(pvals, alpha=alpha)

    verdicts: list[StratumVerdict] = []
    for i, (level, key, members, n_games, games_met, bp, sl) in enumerate(interim):
        verdict = classify(games_met, rejected[i], sl["slope_ok"], bp.get("point"))
        verdicts.append(StratumVerdict(
            level=level, key=key, verdict=verdict,
            n_independent_games=n_games, n_legs=len(members),
            brier_p=bp.get("p_value"), brier_p_adjusted=adjusted[i],
            bh_rejected=rejected[i], point_mean_d=bp.get("point"),
            slope_b1=sl.get("b1"),
            slope_ci=(sl.get("slope_lo"), sl.get("slope_hi"))
            if sl.get("slope_lo") is not None else None,
            slope_ok=sl.get("slope_ok"),
        ))

    return {"strata": verdicts, "k_star": k_star,
            "diagnostics": diagnostics, "config_version": CONFIG_VERSION}


def main() -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from storage.db_manager import DB_PATH, get_connection, init_db

    init_db()
    with get_connection(DB_PATH) as connection:
        result = run_calibration(connection)

    diag = result["diagnostics"]
    print(f"Phase-2 calibration gate (config {result['config_version']})")
    print(f"  scored legs read: {diag.get('kept', 0)} | strata: {len(result['strata'])}")
    if not result["strata"]:
        print("  No identified, settled legs yet. Nothing to grade — verdict pending.")
        return
    print("-" * 96)
    for s in result["strata"]:
        slope = f"{s.slope_b1:.3f}" if s.slope_b1 is not None else "  n/a"
        p = f"{s.brier_p:.4f}" if s.brier_p is not None else "  n/a"
        print(f"  [{s.verdict:10}] {str(s.key):42} games={s.n_independent_games:4} "
              f"brier_p={p} slope={slope} ok={s.slope_ok}")
    print("-" * 96)
    print("  CALIBRATED = consensus out-Briers the sharp-book baseline OOS AND the "
          "reliability slope covers 1.0.")


if __name__ == '__main__':
    main()
