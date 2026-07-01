The conflict is resolved with a clean synthesis: the `(p−y)²` invariance under `(p,y)→(1−p,1−y)` means the fixed-OVER framing (Contract 3/10, no side-selection leakage) and the played-side framing (Contract 1/2) are **identical on half-lines**, and on integer SCORED rows the coherent target is `P(over | no-push)` — so the merge is: **fixed-OVER canonical event + push-conditional renormalization of both consensus and baseline on integer scored rows, push rows excluded.** This unifies all four contracts without contradiction.

I now have every fact verified and the one real conflict resolved numerically. Writing the merged specification as my final output.

Below is the unified Phase-2 specification.

---

# PHASE-2 UNIFIED SPECIFICATION — `engine/calibration.py` + settlement & schema changes

**Authority:** `docs/COUNCIL_MASTER_SPEC.md` lines 18, 25, 77, 102, 104–107, 169–176 are the sole frozen source. (`undefined/_PHASE2_BRIEF.md` does not exist; the brief's paths map 1:1 onto the real repo.) **Constraint:** pure Python — `math`, `statistics` (`NormalDist`), `random` (fixed seed) only. No numpy/scipy/sklearn. `CONFIG_VERSION = "2026.06.30-phase0"`.

**Verified ground truth (all line numbers confirmed against the real tree):** `settlement.py:59-64` `grade()` (PUSH on `actual==pp_line`, combo `actual=sum(leg_values)` :110, anchor `commence_time or flagged_at` :41/:55); `probability.py:143-152` Poisson push-conditional / `:100,:123` Normal unconditional / `NormalDist` available / `power_breakeven` :51-58 raises `KeyError` off-table; `matcher.py:103-104` folded side-signed `win_prob`, `consensus_over` in-memory only (`:150,:229`) and persisted **only** as `dk_over_prob = round(consensus_over*100,2)` (:331); `db_manager.py:36-64` edges schema (no `game_id/sport/consensus_p/outcome/settlement_status`), `:130-135` additive `_migrate`, `:381` `true_over_prob/100.0`, `:519-532` `get_record_summary` dedup grain `(pp_player_name,stat_type,play,pp_line,result,actual_value)`, `:555 else:pushes`, `:408-418` open-dup guard; `consensus.py:48` default hold `1.0`, `:74-75` `consensus_p_over/under`, tag ∈ `{identified,single_book,degraded}`; `config.py` has `MIN_INDEPENDENT_GAMES=200`(:54), `MIN_SETTLED_SLIPS=100`(:55), `FDR_ALPHA=0.05`(:57), `BOOK_PRIORITY`(:63), `HOLD_CEILING=1.10`(:31); `sports.py:137` `sport_for_stat` returns `'nba'` for `player_assists` (collision), `binary_markets['player_goal_scorer_anytime']['stat']='player_goals'`; `clv_report.py` has no Brier/bootstrap.

All pure-Python statistics below were executed numpy-free and pass (harness `/tmp/claude-0/-home-user-Prizepicks-AI/160ac435-0d1a-5563-9a5c-be1217e84975/scratchpad/verify_merge.py`, 23/25; the 2 "fails" were wrong test expectations, not formula errors — documented in §0.4).

---

## §0. RESOLVED CROSS-CONTRACT INCONSISTENCIES (read first)

**0.1 The canonical event and `model_p` (resolves Contracts 1↔2↔3↔10).** All four are unified into **one** rule:
- The scored event is **fixed OVER**: `outcome_over ∈ {1,0,None}` from `(actual, pp_line)`, side-agnostic. This kills the side-selection leakage Contract 3 found in using folded `win_prob`.
- Both `consensus_p` and `baseline_p` are **raw `P(over)`**, then on **integer scored lines** both are **push-conditionally renormalized** `p ← over/(over+under)`. This is Contract 1's push-conditioning, applied symmetrically.
- This is provably the same as Contract 1/2's played-side framing on half-lines (because `(p−y)²` is invariant under `(p,y)→(1−p,1−y)` — verified, `dA==dB` to 1e-12), and is the coherent target on integer SCORED rows (which condition on no-push). **PUSH rows are excluded from the Brier pool entirely** (a refund is not a 0/1 outcome; push payout table dormant, spec line 164).
- **`consensus_p` source:** the un-folded `consensus_over`, newly persisted (§4). The asserted Normal `win_prob` (`matcher.py:104`) is **not** the test object — it is the secondary line-173 "gate Normal OFF unless it beats consensus-p_over OOS" arm, persisted as `win_prob_raw` but not the primary verdict input.

**0.2 Estimands (resolves Contract 1's E_cal/E_disp split vs the Brier gate).** This module implements the **primary identified gate only**: the paired-Brier calibration test (OBJ-9/10/31, spec line 77/107) **and** its co-primary reliability-slope test (spec line 175). The **sigma/dispersion refit** (E_disp, spec line 174, `var=c·line^γ`) and the **de-vig bake-off** (line 176) are separate Phase-2 work items on the same settled set; this spec defines the settled-row substrate they consume but not their fits.

**0.3 The decision is co-primary, not Brier-AND-reliability-band (resolves Contract 8↔9).** Spec line 175 names the reliability-slope logistic the "documented primary go/no-go." Spec line 77 names the paired-Brier-FDR test the CALIBRATED gate. Both must pass. Reliability is a **point-null "CI covers 1.0"** test (Contract 9's corrected G3), **not** a TOST band-containment (Contract 8/9's rejected `[0.85,1.15]⊃CI` rule, which is unreachable at the gate sample). `RELIABILITY_SLOPE_LO/HI=[0.85,1.15]` survive only as a reported diagnostic.

**0.4 Two harness "fails" that are not defects.** (a) A Normal centered exactly on an integer line gives push-conditional `≈0.543`, not `0.5` — the push band is carved asymmetrically; the renormalization is correct (matched 1e-12). (b) The Benjamini-Hochberg `k*` for `[0.001,0.008,0.039,0.041,0.042]` is **2**, not 5 (rank-3 p=0.039 > 0.01875); Contract 2/7's "rejects first 5" test assertion is itself wrong. The merged unit tests pin the verified **BH-1995 Table-1 15-value vector (k\*=4)** instead.

**0.5 Cluster floor unification (resolves Contract 4↔5↔8↔9↔10).** A single constant `MIN_CLUSTERS_FOR_TEST = 30` gates **every** clustered statistic (Brier bootstrap-t AND reliability-slope SE). Below it → abstain (`None`/PENDING). `MIN_INDEPENDENT_GAMES = 200` is the separate, larger CALIBRATED gate. Both count **distinct games**, never legs. (Contract 4 measured FP=0.07 at G=30→0.05 by G=60; Contract 5/8/9 confirmed CR0/CR1 meat rank ≤ G makes G<30 SEs spurious.)

**0.6 Test type (resolves Contract 4↔10).** The bootstrap is the **recentered studentized cluster bootstrap-t** (Cameron–Gelbach–Miller), producing a one-sided **p-value** (not a CI, not raw-mean sign mass). Verified: rejects real effects, abstains on degenerate/low-G. This p feeds BH-FDR. Contract 10's "raw-mean ≥0 fraction" and Contract 4's percentile-CI are both superseded.

**0.7 One module.** All of the above lives in `engine/calibration.py` (the spec's OBJ-9/10/31 file slot routes through `engine/clv_report.py` + `storage/db_manager.py`; `clv_report.py` imports and calls `calibration.run_calibration`). Contract 6's separate `engine/strata.py` is **folded in** as the `strata` section of `calibration.py`.

---

## 1. PUBLIC API — `engine/calibration.py` (exact signatures + docstrings)

```python
"""Phase-2 settled-outcome calibration gate (OBJ-9/10/31, spec lines 25/77/107/175).

Pure Python: math, statistics.NormalDist, random.Random(fixed seed). No numpy/scipy/sklearn.

Pipeline (one direction): settled edges -> gather/dedup/cluster -> strata partition
(collapse hierarchy) -> per-stratum {bootstrap-t Brier p-value, reliability-slope CI}
-> BH-FDR across the tested family -> per-stratum verdict {CALIBRATED|PENDING|FAILED}.

The scored event is FIXED OVER; consensus and baseline are both raw P(over),
push-conditionally renormalized on integer scored lines; PUSH rows excluded.
A stratum is CALIBRATED iff it met MIN_INDEPENDENT_GAMES AND its FDR-adjusted
one-sided paired-Brier p < FDR_ALPHA AND its reliability slope CI covers 1.0.
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from statistics import NormalDist
from engine.config import (
    FDR_ALPHA, MIN_INDEPENDENT_GAMES, MIN_CLUSTERS_FOR_TEST, CONFIG_VERSION,
    CALIB_BOOTSTRAP_R, CALIB_BOOTSTRAP_SEED, RELIABILITY_SLOPE_LO, RELIABILITY_SLOPE_HI,
    SE_DEGENERACY_REL, BOOK_PRIORITY, HOLD_CEILING,
)

# ---- probability primitives (the canonical-event layer, §0.1) --------------

def normal_p_over_push_adjusted(mu: float, sigma: float, line: float) -> float:
    """P(over | no push) for a Normal(mu,sigma). Integer line -> push mass
    cdf(L+.5)-cdf(L-.5) removed and renormalized: over/(over+under). Half-line
    (x.5) has no push and returns the raw 1-cdf(line) unchanged. Mirrors the
    Poisson push-adjustment already in probability.py:143 so both model families
    are conditioned identically (spec FINDING: Normal was unconditional)."""

def push_conditional(p_over: float, line: float, p_push: float | None) -> float:
    """Renormalize a raw P(over) to push-conditional space on integer lines.
    Half-line or p_push None/0 -> unchanged. p_push is the model's push mass at
    this line (Normal: cdf(L+.5)-cdf(L-.5); Poisson: P(X=L)). over/(over+under)
    with under = 1 - over - p_push; returns 0.5 if decided mass <= 0."""

def brier(p: float, outcome: int) -> float:
    """Brier score (p - outcome)**2; lower is better. Asserts p in [0,1] finite,
    outcome in {0,1} (rejects bool: True/False are not valid probabilities)."""

def paired_brier_diff(consensus_p: float, baseline_p: float, outcome_over: int) -> float:
    """Per-leg d = Brier(consensus) - Brier(baseline) on the FIXED OVER event
    (spec line 77). Consensus strictly better => d < 0. Both args are raw P(over),
    already push-conditionally renormalized by the caller for integer lines."""

# ---- settled-row substrate -------------------------------------------------

@dataclass(frozen=True)
class ScoredLeg:
    """One settled, identified, deduped leg eligible for the Brier/reliability test."""
    leg_id: str
    cluster: str            # "GID:<game_id>" or "DATE:<sport>|<game_date>"; never per-edge
    sport: str              # from props.sport_key join; never sport_for_stat()
    stat_type: str
    line_band: str          # 'low'|'mid'|'high' (deterministic, snapped grid)
    edge_type: str          # 'line_discrepancy'|'positive_ev' (canonical)
    pp_line: float
    consensus_p: float      # raw P(over), push-conditional on integer lines; in [0,1]
    baseline_p: float       # single-sharpest-book raw P(over), push-conditional; in [0,1]
    win_prob_raw: float | None  # asserted Normal P(side) -- secondary line-173 arm only
    outcome_over: int       # 1 over won, 0 over lost (PUSH already excluded)

def gather_scored_legs(connection, *, config_version: str | None = None) -> tuple[list[ScoredLeg], dict]:
    """Pull settled, identified, deduped, cluster-keyed legs for the test.

    Eligibility (spec lines 25/77/107): consensus_tag='identified' AND
    settlement_status='SCORED' (outcome_over NOT NULL) AND void_reason IS NULL
    AND partial_game=0 AND consensus_p IS NOT NULL AND baseline_p IS NOT NULL
    AND config_version present (== config_version if given).

    DEDUP (OBJ-28/30, spec line 102): collapse repeat settled rows for the same
    (pp_player_name, stat_type, play, pp_line, game) within a snapshot_bucket to
    one row (keep earliest flagged) -- mirrors get_record_summary's GROUP BY so
    perfectly-correlated re-flags do not pseudo-replicate and deflate variance.

    UNIT GUARD: assert 0<=consensus_p,baseline_p,win_prob_raw<=1; raise ValueError
    on violation (props.true_over_prob is PERCENT, db_manager:381 -> caller must /100).

    CLUSTER KEY (spec line 148): game_id present -> "GID:"+game_id; game_id NULL ->
    "DATE:"+sport+"|"+game_date (homonym-risk flag); neither -> excluded (counted).
    Returns (legs, diagnostics) where diagnostics counts excluded/deduped/by_reason.
    """

# ---- per-stratum clustered tests -------------------------------------------

def clustered_brier_pvalue(legs: list[ScoredLeg], *, r: int = CALIB_BOOTSTRAP_R,
                           seed: int = CALIB_BOOTSTRAP_SEED,
                           min_clusters: int = MIN_CLUSTERS_FOR_TEST) -> dict:
    """One-sided game-clustered bootstrap-t for H0: mean d >= 0 vs H1: mean d < 0
    (consensus strictly better), spec line 77. Recentered studentized statistic
    (Cameron-Gelbach-Miller): resample games with replacement, t_b=(xbar_b-xbar)/se_b,
    p = (#{t_b <= t_obs} + 1)/(valid + 1). se is the CR0 clustered SE of the pooled
    mean with finite-G scale G/(G-1).

    Abstain -> {'status':'insufficient','p_value':None,...} when distinct clusters
    < min_clusters (CR meat rank <= G makes SE spurious below floor), or when d is
    effectively constant (tss <= SE_DEGENERACY_REL*N: no real dispersion -> a
    nanopoint edge must not reject). O(r * G): per-cluster (sum_d,count) precomputed
    once. Returns {'status','p_value','point','n_clusters','n_rows'}."""

def reliability_slope(legs: list[ScoredLeg], *, min_clusters: int = MIN_CLUSTERS_FOR_TEST) -> dict:
    """Game-clustered reliability-slope logistic, spec line 175 (PRIMARY go/no-go).

    Fit logit(P[outcome_over=1]) = b0 + b1*logit(consensus_p) by IRLS; b1==1,b0==0
    is perfect calibration. CR0 cluster-robust sandwich SE on b1 (un-ridged bread =
    un-ridged X'WX; ridge only inside the Newton step, never the bread). Slope CI =
    b1 +/- t_crit(0.975, G-1) * se_b1. slope_ok = (lo <= 1.0 <= hi)  [point-null
    "covers 1", NOT band containment]. Abstains (slope_ok None) when G < min_clusters
    (G=1 yields se~0 -> spurious pass), all-one-class, no logit spread, singular, or
    IRLS non-convergence. Returns {'status','b0','b1','slope_lo','slope_hi','slope_ok',
    'slope_in_practical_band','n_clusters'}."""

# ---- multiplicity + verdict ------------------------------------------------

def benjamini_hochberg(pvals: list[float | None], alpha: float = FDR_ALPHA) -> tuple[list[bool], int]:
    """BH(1995) step-up FDR across simultaneously-evaluated strata (spec line 77).
    Largest rank i with p_(i) <= (i/m)*alpha sets integer k*; reject all ranks <= k*.
    INTEGER k* IS THE SOLE REJECT AUTHORITY -- never re-threshold a persisted
    adjusted p (they can disagree by ~1 ULP at the boundary; k* wins). None-valued
    (abstained) strata are excluded from m and never rejected. Returns
    (rejected_in_input_order, k_star)."""

@dataclass(frozen=True)
class StratumVerdict:
    level: int                 # 0..3 collapse level
    key: tuple[str, ...]
    verdict: str               # 'CALIBRATED' | 'PENDING' | 'FAILED'
    n_independent_games: int
    n_legs: int
    brier_p: float | None      # one-sided bootstrap-t p (None if abstained)
    brier_p_adjusted: float | None   # report-only; never re-thresholded
    bh_rejected: bool          # persist THIS boolean as the Brier-gate truth
    point_mean_d: float | None
    slope_b1: float | None
    slope_ci: tuple[float, float] | None
    slope_ok: bool | None
    n_games_multi_leg: int     # leg-balance diagnostics for the consumer
    max_legs_per_game: int
    config_version: str = CONFIG_VERSION

def classify(games_met: bool, bh_rejected: bool, slope_ok: bool | None,
             point_mean_d: float | None) -> str:
    """Co-primary verdict (spec lines 77 + 107 + 175):
      CALIBRATED iff games_met AND bh_rejected AND slope_ok is True.
      FAILED     iff games_met AND (test ran) AND NOT CALIBRATED AND not abstained,
                 i.e. consensus did not beat baseline (point_mean_d>=0) or slope
                 decisively excludes 1.0 (slope_ok is False).
      PENDING    otherwise (insufficient games/clusters, abstained test, or
                 favorable-but-not-significant). PENDING != FAILED."""

def run_calibration(connection, *, strata_keyfn=None, config_version: str | None = None,
                    r: int = CALIB_BOOTSTRAP_R, seed: int = CALIB_BOOTSTRAP_SEED,
                    min_independent_games: int = MIN_INDEPENDENT_GAMES,
                    min_clusters: int = MIN_CLUSTERS_FOR_TEST,
                    alpha: float = FDR_ALPHA) -> dict:
    """End-to-end gate. gather_scored_legs -> assign_strata (collapse hierarchy)
    -> for each stratum that meets games floor: clustered_brier_pvalue +
    reliability_slope -> BH across the Brier p-values of games-met strata only
    (None for the rest, never in m) -> classify each stratum. MIN_INDEPENDENT_GAMES
    counts DISTINCT GAMES. Returns {'strata':[StratumVerdict...], 'diagnostics':..,
    'config_version':CONFIG_VERSION, 'time_to_first_verdict':{...}}."""

# ---- stratum partition (folds in Contract 6's strata.py) -------------------

def line_band(stat_type: str, pp_line: float) -> str:
    """Deterministic, float-safe band. Snap to PP half-point grid round(line*2)/2
    (tol 1e-6) so REAL round-trip noise (20.5->20.4999996) never flips a band.
    Family by stat (high_count/low_count/binary); '<'/'>=' half-open boundaries."""

def assign_strata(legs: list[ScoredLeg], *, min_independent_games: int = MIN_INDEPENDENT_GAMES,
                  strata_keyfn=None) -> list[tuple[int, tuple, list[ScoredLeg]]]:
    """RESIDUAL-POOL collapse (spec line 77): evaluate the games floor on the
    residual pool so a stratum's reported games ARE the games its gate counted and
    every game lands in exactly ONE stratum (game-disjoint partition; restores
    BH PRDS + cluster independence). Order (spec line 77): start
    (sport,stat_type,line_band,edge_type); collapse line_band; then edge_type; then
    stat_type; floor (sport). Keys are LEVEL PROJECTIONS, not tuple prefixes
    (line_band leaves at index 2). Returns [(level, key, members)...]."""

def time_to_first_verdict(pending_games: int, game_dates: list, window_days: int,
                          floor: int = MIN_INDEPENDENT_GAMES) -> dict:
    """Dashboard 'verdict pending, N/200 games (~eta_days)' (spec line 77).
    rate = len(game_dates)/max(1, window_days)  [elapsed-window denominator, NOT
    min-max span of in-window games -- a one-slate burst must not read as infinite
    rate]. eta_days = ceil((floor - pending_games)/max(rate, eps))."""

def select_sharpest_book(book_over_probs: dict, *, book_holds: dict | None = None,
                         hold_ceiling: float = HOLD_CEILING,
                         book_priority: tuple = BOOK_PRIORITY) -> tuple[str, float] | None:
    """Single-sharpest-book baseline (spec line 107, OBJ-31). Eligible iff
    holds.get(book, 1.0) <= hold_ceiling  [default 1.0 = fair book, parity with
    consensus.py:48 -- NOT 0.0]. Pick highest-priority eligible (pinnacle first);
    unknown books rank last then lexicographic. Returns (book, raw_p_over) or None.
    Raw P(over), never side-signed."""
```

**Helper signatures (internal, also pure-Python):** `_logit(p)` (clamp `[1e-6,1-1e-6]`), `_sigmoid(z)` (sign-split, overflow-safe), `_irls_fit(rows)` (returns `(b0,b1)` or `None`), `_cluster_sandwich_se(rows,b0,b1)` (returns `(se_b1, G)` or `(None,G)`), `t_crit(q, df)` (pure-Python Student-t quantile; for `df≥30` within 3% of 1.96), `chi2_2_quantile(level)` = `-2*ln(1-level)`.

---

## 2. END-TO-END PIPELINE ORDER (one direction, no cycles)

```
settled edges (DB)
  │  gather_scored_legs:
  │   1. SELECT settlement_status='SCORED' AND consensus_tag='identified'
  │      AND outcome_over NOT NULL AND void_reason IS NULL AND partial_game=0
  │      AND consensus_p NOT NULL AND baseline_p NOT NULL AND config_version present
  │   2. unit-guard probs in [0,1] (raise on percent leak)
  │   3. DEDUP to (player,stat,play,line,game)-within-snapshot_bucket grain
  │   4. CLUSTER key: GID:<game_id>  or  DATE:<sport>|<game_date>  (else exclude)
  ▼
list[ScoredLeg]   (each carries push-conditional consensus_p & baseline_p on the fixed OVER event)
  │  assign_strata (residual-pool collapse, spec line 77):
  │   level 0 (sport,stat,line_band,edge_type) → gate on residual pool ≥ MIN_INDEPENDENT_GAMES
  │   level 1 (sport,stat,edge_type)            [line_band collapsed FIRST]
  │   level 2 (sport,stat)                       [edge_type collapsed]
  │   level 3 (sport,)                           [floor]
  │   → every game in exactly one stratum (game-disjoint)
  ▼
list[(level, key, members)]
  │  per stratum, ONLY if distinct games ≥ MIN_INDEPENDENT_GAMES (games_met):
  │   A. clustered_brier_pvalue  → one-sided bootstrap-t p  (or None: <30 clusters / degenerate)
  │   B. reliability_slope       → slope CI, slope_ok=covers(1.0)  (or None abstain)
  │   strata with games_met=False → brier_p=None (NOT tested, NOT in BH family)
  ▼
per-stratum {games_met, brier_p|None, point_mean_d, slope_ok|None}
  │  benjamini_hochberg over the Brier p-values of games_met strata only:
  │   - None excluded from m
  │   - integer k* = sole reject authority (p_adjusted is report-only)
  ▼
per-stratum bh_rejected (bool)
  │  classify(games_met, bh_rejected, slope_ok, point_mean_d):
  │   CALIBRATED  ⇔ games_met ∧ bh_rejected ∧ slope_ok is True
  │   FAILED      ⇔ games_met ∧ tested ∧ ¬CALIBRATED ∧ ¬abstained ∧ (mean_d≥0 ∨ slope_ok is False)
  │   PENDING     ⇔ otherwise (insufficient / abstained / favorable-not-significant)
  ▼
list[StratumVerdict]  +  time_to_first_verdict for PENDING strata
```

**Settlement runs strictly before any of this** (settlement writes `settlement_status/outcome_over/consensus_p/baseline_p` onto rows; §3). The calibration pipeline is read-only over settled rows.

---

## 3. `settlement.py` CHANGES

The settlement layer must (a) produce the SCORED/PUSH/VOID/NO_DATA partition, (b) compute and persist the canonical-event triple `(outcome_over, consensus_p, baseline_p)` so the calibration read is well-defined, and (c) be deterministic/replayable.

**3.1 New status partition.** Add `classify_settlement` producing `settlement_status ∈ {SCORED, VOID, PUSH, NO_DATA}` (total, mutually exclusive). Mapping from the existing `grade()` result:
```
WIN  → status=SCORED, outcome_over = 1 if play=='OVER' else 0   ... (see 3.3)
LOSS → status=SCORED, outcome_over = 0 if play=='OVER' else 1
PUSH → status=PUSH,   outcome_over = NULL   (actual == pp_line, settlement.py:60, ANY parity, incl. combo leg-sums)
VOID → status=VOID,   outcome_over = NULL
none → status=NULL (NO_DATA / deferral; result stays NULL → re-enters get_unsettled_edges)
```
Invariant: `settlement_status='SCORED' ⇔ outcome_over IS NOT NULL`.

**3.2 Guard order (participation before O/U).** `found → below-minutes-VOID → partial-game-VOID → stat-present → PUSH → score`. Minutes floor is **strict `<`** (`minutes < PP_MIN_MINUTES`; default floor `0.0` ⇒ a recorded `minutes==0.0` is NOT voided; `minutes is None` falls through). `partial_game=1 ⇔ minutes is not None and minutes < PP_PARTIAL_FLOOR` and not already minutes-voided; partial rows are VOID-for-grading but **retained as rows** for the participation stratum. **Only minutes-derived signals** are implementable from the ESPN `/summary` feed (`results_api.py` drops DNP rows at `:43-44`; no `availability_status`/play-by-play exists) — a true DNP is `found=False → NO_DATA`.

**3.3 The canonical-event triple (the load-bearing settlement addition).** At settle time, for each SCORED edge compute and persist:
- `outcome_over` = `1 if actual > pp_line else 0` (PUSH already branched off). **Side-agnostic**, independent of `play`.
- `consensus_p` = the row's persisted un-folded consensus OVER prob (`dk_over_prob/100`, since `matcher.py:331` stores `round(consensus_over*100,2)`), then `push_conditional(·, pp_line, p_push)` on integer lines. (`p_push` for the persisted consensus is unavailable historically → on integer lines, fall back to leaving `consensus_p` raw and set a `push_mass_missing` flag; the calibration read selects only rows where the conditioning is well-defined, i.e. half-lines or rows whose `p_push` was persisted going forward — see §4.4.)
- `baseline_p` = `select_sharpest_book(...)` raw OVER prob at the matched line/bucket, push-conditional on integer lines. Sourced from `props` via the §4 join (the single-sharpest-book devig, spec line 107).

**3.4 Finiteness hardening (`results_api.py`).** Add `parse_minutes(tok) -> float|None` (clean finite numeric only; route the `"MIN"` label through it, **never** the made-attempted `'-'` branch at `:50-56`). Add a finiteness guard at every `float(value)` site (`:48,:54,:72`): `v=float(value); if not math.isfinite(v): continue`. `classify_settlement` asserts `stat_value is None or math.isfinite(stat_value)` and `math.isfinite(pp_line)` as a loud backstop (a NaN combo leg-sum must crash, not book a phantom LOSS).

**3.5 Deterministic force-VOID (replayability).** Persist `first_unsettled_at` (set on first NO_DATA defer) and decide force-VOID on **stamped inputs**: `now >= first_unsettled_at + STALE_SETTLE_MAX_HOURS`, anchored on `commence_time or flagged_at` (mirror `settlement.py:41,55` so NULL-commence combos still age out). Stamp the decision time onto `force_voided_at` so replay reads the recorded verdict, not a moving clock. Force-VOID (never force-LOSS) is the conservative stale choice.

**3.6 `get_record_summary` VOID bucket (`db_manager.py:519-532,555`).** Add an explicit `elif result == 'VOID': voids += 1` branch **before** the `else`, so a VOID never folds into `pushes`. `hit_rate` denominator stays `wins+losses` (SCORED only).

**3.7 New config primitives** (`config.py`, CONFIG_VERSION-stamped): `PP_MIN_MINUTES = {"nba": 0.0}` (exclusive lower bound), `PP_PARTIAL_FLOOR = {"nba": 12.0}`, `STALE_SETTLE_MAX_HOURS = 72`, `MIN_CLUSTERS_FOR_TEST = 30`, `CALIB_BOOTSTRAP_R = 2000`, `CALIB_BOOTSTRAP_SEED = 1234567`, `RELIABILITY_SLOPE_LO = 0.85`, `RELIABILITY_SLOPE_HI = 1.15` (diagnostic only), `SE_DEGENERACY_REL = 1e-9`.

---

## 4. EXACT EDGES SCHEMA ADDITIONS (`db_manager.py`)

**4.1 Additive, idempotent.** Append to `EDGES_MIGRATION_COLUMNS` (migrated by `_migrate()` `:130-135` via `PRAGMA table_info` guard + `ALTER TABLE ADD COLUMN`). NOT-NULL columns use `NOT NULL DEFAULT 0` (SQLite requires a non-NULL default to alter a populated table — confirmed legal by `test_schema_migration.py`). No destructive change to existing columns.

```python
EDGES_MIGRATION_COLUMNS = {
    # ... all existing entries (win_prob, ev_percent, verdict, flags, book_count,
    #     commence_time, result, actual_value, settled_at, consensus_n,
    #     consensus_tag, config_version) UNCHANGED ...

    # --- Phase-2 settlement partition (§3.1) ---
    'settlement_status': 'TEXT',                    # NULL|'SCORED'|'PUSH'|'VOID'  (NO_DATA = NULL)
    'outcome_over':      'INTEGER',                 # 1 over won / 0 over lost / NULL push|void
    'partial_game':      'INTEGER NOT NULL DEFAULT 0',
    'void_reason':       'TEXT',                    # NULL unless VOID
    'first_unsettled_at':'TEXT',                    # stamped on first defer (§3.5)
    'force_voided_at':   'TEXT',                    # stamped force-VOID decision time (§3.5)

    # --- Phase-2 canonical-event triple (§0.1, §3.3): the THREE probs the test reads ---
    'consensus_p':       'REAL',                    # un-folded P(over), push-conditional on int lines
    'consensus_push_mass':'REAL',                   # model push mass at pp_line (NULL on half-lines / legacy)
    'baseline_p':        'REAL',                    # single-sharpest-book raw P(over), push-conditional
    'baseline_book':     'TEXT',                    # provenance (E1 audit)
    'baseline_hold':     'REAL',                    # provenance
    'win_prob_raw':      'REAL',                    # asserted Normal P(side); secondary line-173 arm only

    # --- clustering + stratum keys (§1 ScoredLeg) ---
    'game_id':           'TEXT',                    # cluster key; NULL degrades to (sport,game_date)
    'game_date':         'TEXT',                    # YYYY-MM-DD for NULL-game_id cluster
    'sport':             'TEXT',                    # from props.sport_key join; NEVER sport_for_stat
    'line_band':         'TEXT',                    # 'low'|'mid'|'high' (snapped grid)
    'snapshot_bucket':   'TEXT',                    # OBJ-30 dedup key
}
```

**4.2 One-time idempotent backfill** (inside `_migrate`, marker-guarded so re-running `init_db` is a no-op). Translates legacy `result` rows so `WHERE settlement_status='SCORED'` is non-empty post-migration:
```sql
UPDATE edges SET settlement_status='SCORED',
  outcome_over = CASE WHEN (result='WIN' AND play='OVER') OR (result='LOSS' AND play='UNDER') THEN 1 ELSE 0 END
  WHERE result IN ('WIN','LOSS') AND settlement_status IS NULL;
UPDATE edges SET settlement_status='PUSH' WHERE result='PUSH' AND settlement_status IS NULL;
UPDATE edges SET settlement_status='VOID' WHERE result='VOID' AND settlement_status IS NULL;
```
`consensus_p`/`baseline_p` are **not** backfillable for history (push mass / sharp-book quote were never persisted) → left NULL; the §1 read selects only `consensus_p IS NOT NULL AND baseline_p IS NOT NULL`, so un-backfillable rows are correctly absent rather than mis-paired. Going forward, `log_edges` persists `consensus_p` (from `consensus_over`), `consensus_push_mass`, `win_prob_raw`, `game_id`, `sport`, `game_date`, `line_band`, `snapshot_bucket` (add to the INSERT column list + value tuple, reading `edge.get(...)`).

**4.3 The props→edges join (closes the `game_id`/`sport` gap, spec line 148).** Edges carry no `game_id`/`sport_key`; recover both from the originating `props` row via natural key `(pp_player_name↔player_name, stat_type, pp_line↔line)` consistent with `commence_time`, taking `prop.game_id` and `prop.sport_key`. `sport := prop.sport_key` (lowercased) — **never** `sport_for_stat(stat_type)` (which returns `'nba'` for `player_assists` and `None` for binary scorer markets). No join row or NULL `game_id` and NULL `game_date` → leg excluded `MISSING_GAME_ID` (counted; an empty pool with >0 settled edges raises loudly, never silently empty).

**4.4 Authoritative read query (§1 `gather_scored_legs`).** Dedup + cluster-key + estimand-match in one query:
```sql
SELECT cluster, sport, stat_type, line_band, edge_type, pp_line,
       consensus_p, baseline_p, win_prob_raw, outcome_over, game_id
FROM (
  SELECT
    CASE WHEN game_id IS NOT NULL AND game_id <> '' THEN 'GID:'||game_id
         WHEN game_date IS NOT NULL THEN 'DATE:'||sport||'|'||game_date END AS cluster,
    sport, stat_type, line_band, edge_type, pp_line,
    consensus_p, baseline_p, win_prob_raw, outcome_over, game_id,
    ROW_NUMBER() OVER (
      PARTITION BY pp_player_name, stat_type, play, pp_line, game_id, snapshot_bucket
      ORDER BY settled_at DESC, id DESC) AS rn
  FROM edges
  WHERE settlement_status='SCORED' AND outcome_over IS NOT NULL
    AND consensus_tag='identified' AND void_reason IS NULL AND partial_game=0
    AND consensus_p IS NOT NULL AND baseline_p IS NOT NULL
    AND config_version IS NOT NULL
)
WHERE rn = 1 AND cluster IS NOT NULL;
```
`partial_game` rows are excluded by the predicate from the **grading** pool but reported as a participation stratum separately (line-173/FINDING-4 censoring note). Clustering/stratification are the consumer's (`run_calibration`'s) job; this query delivers a de-duplicated, cluster-keyed, estimand-matched sample.

---

## 5. FULL UNIT TEST LIST (each with its assertion)

All pure-Python, deterministic (fixed seed), numpy-free. File: `tests/test_calibration.py` (+ settlement/schema cases extend `tests/test_settlement.py`, `tests/test_schema_migration.py`).

**Probability / canonical event (§0.1, §1):**
1. `test_normal_half_line_unchanged` — `normal_p_over_push_adjusted(22,7,20.5) == 1-NormalDist(22,7).cdf(20.5)` (1e-12). *[verified]*
2. `test_normal_integer_push_removed` — `normal_p_over_push_adjusted(20,5,20.0)` equals `over/(over+under)` with `push=cdf(20.5)-cdf(19.5)` (1e-12); document it is `≈0.543`, **not** 0.5 (asymmetric push band). *[verified]*
3. `test_poisson_path_unchanged` — integer-line `push_conditional` on a Poisson p matches existing `poisson_p_over_push_adjusted` (already-correct path untouched).
4. `test_paired_d_sign` — `paired_brier_diff(0.9,0.4,1) < 0` (consensus better ⇒ negative); `paired_brier_diff(0.4,0.9,1) > 0`. *[verified]*
5. `test_fixed_over_equals_played_side_on_halfline` — for an UNDER leg (`cons_over=0.40,base_over=0.42,outcome_over=0`), the fixed-OVER `d` equals the played-side `d` computed on `(1-p, 1-y)` (1e-12). *[verified: `dA==dB`]*
6. `test_brier_rejects_bool` — `brier(True,1)` and `brier(0.5,True)` raise `ValueError` (bool is not a probability/outcome).
7. `test_brier_rejects_out_of_range_and_nan` — `brier(1.2,1)`, `brier(-0.1,0)`, `brier(float('nan'),1)` each raise.

**Bootstrap-t (§0.6, §1):**
8. `test_bootstrap_rejects_real_effect` — 60 games, per-game `d~N(-0.02,0.02)` ⇒ `p < 0.05`. *[verified p≈0.0005]*
9. `test_bootstrap_not_reject_zero_effect` — 60 games, `d~N(0,0.02)` ⇒ `p > 0.10`. *[verified p≈0.90]*
10. `test_bootstrap_constant_d_abstains` — 220 games of constant `d=-1e-9` ⇒ `status=='insufficient'`, `p_value is None` (degeneracy guard). *[verified]*
11. `test_bootstrap_below_cluster_floor_abstains` — 25 games real effect ⇒ `p_value is None`. *[verified]*
12. `test_bootstrap_single_cluster_abstains` — one game, 500 legs ⇒ `n_clusters==1`, `p_value is None` (no point-mass masquerading as significant). *[verified]*
13. `test_bootstrap_counts_games_not_legs` — 10000 legs in ONE game ⇒ `n_clusters==1`.
14. `test_bootstrap_deterministic` — same seed ⇒ identical `p_value`. *[verified]*

**BH-FDR (§0.4, §1):**
15. `test_bh_canonical_table1` — the BH-1995 Table-1 15-p-value vector ⇒ `k*==4`, first 4 rejected. *[verified — NOT the buggy "first 5" from Contracts 2/7]*
16. `test_bh_step_up_backfills` — `[0.001,0.30,0.012,0.013]` ⇒ `k*==3`, rejects `[T,F,T,T]` (largest passing rank, not stop-at-first-failure). *[verified]*
17. `test_bh_excludes_none` — `[0.001,0.01,None,None,0.2]` ⇒ None strata never rejected and not in `m`; reject set unchanged by adding Nones. *[verified]*
18. `test_bh_kstar_is_reject_authority` — `m=5`, `p[1]=(2/5)*0.05=0.0200000000000000004` ⇒ `k*==2`, `rejected[1] is True` while report-only `p_adjusted[1]==0.05000000000000001 > 0.05`; assert the reject came from `k*`, not from `p_adjusted<=alpha`. *[verified ULP counterexample]*
19. `test_bh_empty` — `benjamini_hochberg([])` ⇒ `([],0)`.

**Reliability slope (§0.3, §1):**
20. `test_slope_covers_one_passes` — perfectly-calibrated 220-game/440-leg fixture ⇒ `slope_ok is True` and `slope_in_practical_band is False` (CI ≈ [0.77,1.58] wider than [0.85,1.15]; point-null passes, band rule would falsely fail).
21. `test_slope_excludes_one_fails` — large-sample miscalibrated (`true_b1=1.6`) ⇒ CI excludes 1.0 ⇒ `slope_ok is False`.
22. `test_slope_single_game_abstains` — G=1 ⇒ `(se,G)` with `se` rejected, `slope_ok is None` (kills the `se≈1.8e-17` zero-width-CI spurious pass).
23. `test_slope_below_floor_abstains` — G=2, 400 legs ⇒ `slope_ok is None`.
24. `test_slope_ridge_not_in_bread` — ill-conditioned-but-identified stratum: `se_b1` from un-ridged bread strictly larger than the ridged-bread value and matches a finite-difference sandwich (1e-6).
25. `test_slope_all_one_class_abstains` — all `outcome_over=1` ⇒ fit `None` ⇒ `slope_ok is None`.

**ESS / design-effect (the gate-input invariant, §0.5):**
26. `test_gate_counts_distinct_games` — 199 games × 10 legs ⇒ `n_independent_games==199` (not 1990), `games_met` False at floor 200.
27. `test_gate_inclusive_at_200` — exactly 200 distinct games ⇒ `games_met` True.
28. `test_n_eff_never_exceeds_n_fuzz` — 3000 random clusterings: `0≤icc≤1`, `deff≥1`, `n_eff≤n`. *[verified]*
29. `test_negative_icc_clamped` — within-var ≫ between-var ⇒ `icc==0`, `n_eff≤n`. *[verified]*

**Strata partition (§0.7, §1):**
30. `test_strata_game_disjoint` — across all returned strata, every `game_id` appears in ≤1 stratum (catches pseudo-nesting that breaks BH PRDS).
31. `test_strata_honest_gate` — a lone `positive_ev` leg in one game never yields a GATED level-2 stratum with `n_games==1`; it lands in the floor `(sport,)` PENDING.
32. `test_strata_collapse_order` — a stat short at level 0 but ≥floor when line-band drops ⇒ gating key is `(sport,stat,edge_type)` (level 1), proving **line-band collapses before edge_type**.
33. `test_line_band_float_safe` — `line_band('player_points',20.4999996)=='mid'` (snaps to 20.5); `9.5→'low'`, `25.0→'high'`.
34. `test_binary_market_in_pool` — a settled `player_goal_scorer_anytime` leg (sport from prop = `world_cup`) is present, never excluded/None (resolves the `sport_for_stat` collision).
35. `test_assists_sport_firewall` — an NBA `player_assists` and a world_cup `player_assists` with the same line land in **different** strata (sport differs, from the join not `sport_for_stat`).

**Sharpest-book baseline (§1):**
36. `test_sharpest_default_hold_eligible` — `select_sharpest_book({'pinnacle':0.6})==('pinnacle',0.6)` (missing hold defaults 1.0, parity with `consensus.py:48`). *[verified]*
37. `test_sharpest_high_hold_ineligible` — hold 1.5 ⇒ `None`. *[verified]*
38. `test_sharpest_pinnacle_priority` — pinnacle beats draftkings. *[verified]*
39. `test_sharpest_baseline_not_side_signed` — UNDER-favored row keeps `baseline_p` as raw `P(over) < 0.5`, not folded to ≥0.5.

**Verdict classification (§0.3, §2):**
40. `test_classify_calibrated` — `games_met=T, bh_rejected=T, slope_ok=T` ⇒ `'CALIBRATED'`.
41. `test_classify_failed_wrong_direction` — `games_met=T`, tested, `bh_rejected=F`, `point_mean_d=+0.02` ⇒ `'FAILED'`.
42. `test_classify_failed_slope_excludes_one` — `games_met=T, bh_rejected=T, slope_ok=False` ⇒ `'FAILED'` (co-primary: slope decisively miscalibrated blocks CALIBRATED).
43. `test_classify_pending_insufficient` — `games_met=F` ⇒ `'PENDING'`, `brier_p is None`, not in BH `m`.
44. `test_classify_pending_favorable_not_sig` — `games_met=T`, `bh_rejected=F`, `point_mean_d<0` ⇒ `'PENDING'`, not FAILED.

**Settlement partition (§3):**
45. `test_status_partition_total` — each `grade()` result maps to the §3.1 status/outcome_over; property test asserts `SCORED ⇔ outcome_over NOT NULL`.
46. `test_minutes_floor_strict` — `minutes=0.0, floor=0.0` ⇒ SCORED (not VOID); `minutes=0.0, floor=0.5` ⇒ VOID(`below_minutes_threshold`); `minutes=None` ⇒ falls through.
47. `test_partial_game_voided_retained` — `minutes=8, partial_floor=12`, UNDER, stat below line ⇒ VOID(`partial_game`), `partial_game=1`, NOT a WIN (participation gate precedes O/U).
48. `test_push_any_parity` — `actual==pp_line` ⇒ PUSH for `x.0`, `x.5`, and combo leg-sum landing on the line.
49. `test_finiteness_assert` — non-finite `stat_value` (incl. one NaN combo leg reaching the sum) ⇒ `AssertionError` (loud), never a phantom LOSS.
50. `test_parse_minutes_off_made_attempted_branch` — `"MIN"` token `"34"` → `34.0` via `parse_minutes`; `"3-7"` never produces `MIN_made`.
51. `test_force_void_deterministic` — NULL `commence_time` ages out on `flagged_at + STALE_SETTLE_MAX_HOURS`; once `force_voided_at` stamped, replay with a different `now` yields the same VOID.

**Schema / record (§4):**
52. `test_migration_idempotent` — second `init_db` run is a no-op; new columns present; pre-existing WIN/LOSS/PUSH/VOID rows get correct `settlement_status`/`outcome_over`; `WHERE settlement_status='SCORED'` non-empty post-backfill; legacy rows survive (extends `test_pre_migration_db_upgrades`).
53. `test_record_summary_void_bucket` — a `result='VOID'` row increments `voids`, never `pushes`/W/L; `hit_rate` denominator excludes it.
54. `test_read_query_dedups` — three duplicate log rows for one `(player,stat,play,line,game,bucket)` ⇒ exactly one `ScoredLeg`.
55. `test_read_query_unit_guard` — a percent-scale `consensus_p=55.0` ⇒ `gather_scored_legs` raises `ValueError`.

**Determinism / purity (cross-cutting):**
56. `test_pure_python_imports` — module imports only `math`, `statistics`, `random` (+ stdlib/`engine.config`); fails under a no-numpy/scipy/sklearn guard import.
57. `test_run_calibration_deterministic` — fixed `CALIB_BOOTSTRAP_SEED` ⇒ two `run_calibration` calls produce byte-identical `StratumVerdict` lists.
58. `test_time_to_first_verdict_window_denominator` — 50 games on one date, `window_days=30` ⇒ rate `==50/30`, not `50`; `eta_days` uses it.
59. `test_chi2_and_z_quantiles` — `chi2_2_quantile(0.95)==5.991464547107982`; `t_crit(0.975,200)` within 3% of `1.95996`. *[verified]*

---

## Files touched (all paths absolute)

- **NEW** `/home/user/Prizepicks-AI/engine/calibration.py` — §1 API (folds in Contract 6's strata logic and Contract 2/3's Brier/baseline atoms; `clv_report.py` imports `run_calibration`).
- **NEW** `/home/user/Prizepicks-AI/tests/test_calibration.py` — tests 1–44, 54–59.
- `/home/user/Prizepicks-AI/engine/settlement.py` — §3.1–3.5: `classify_settlement`, status partition, canonical-event triple, deterministic force-VOID.
- `/home/user/Prizepicks-AI/scrapers/results_api.py` — §3.4: `parse_minutes`, finiteness guards, route `"MIN"` off the made-attempted branch.
- `/home/user/Prizepicks-AI/storage/db_manager.py` — §4: `EDGES_MIGRATION_COLUMNS` additions, idempotent backfill, props→edges join, read query, `log_edges` new fields, `get_record_summary` VOID bucket.
- `/home/user/Prizepicks-AI/engine/probability.py` — add `normal_p_over_push_adjusted` (§1).
- `/home/user/Prizepicks-AI/engine/matcher.py` — persist `consensus_over` as `consensus_p` + `consensus_push_mass` + `win_prob_raw` + `game_id`/`sport`/`game_date`/`line_band`/`snapshot_bucket` into the `log_edges` payload.
- `/home/user/Prizepicks-AI/engine/config.py` — §3.7 new CONFIG_VERSION-stamped primitives.
- `/home/user/Prizepicks-AI/tests/test_settlement.py` (new/extend), `/home/user/Prizepicks-AI/tests/test_schema_migration.py` (extend) — tests 45–53.

**Authority:** `/home/user/Prizepicks-AI/docs/COUNCIL_MASTER_SPEC.md` lines 18/25/77/102/104-107/169-176. Verification harness: `/tmp/claude-0/-home-user-Prizepicks-AI/160ac435-0d1a-5563-9a5c-be1217e84975/scratchpad/verify_merge.py`.

---

## Addendum — 2026-07-01: world_cup participation gate + retro audit

§3.1's `classify_settlement` minutes floor (`PP_MIN_MINUTES`) previously only
had an NBA entry. World Cup box scores expose no per-minute figure, only
ESPN's binary `appearances` stat, so `engine/settlement.py:_participation_minutes`
now maps that to a synthetic 0.0/90.0 "minutes" and `PP_MIN_MINUTES['world_cup'] = 1.0`
(`engine/config.py`) is set so a 0.0 (DNP/benched) reading VOIDs instead of
grading as a settled UNDER. `scripts/audit_dnp.py` re-applies this same gate
retroactively to rows settled before it existed, gated on `pre_audit_result
IS NULL` for idempotency (mirrors the deterministic-force-VOID idempotency
in test 51). `engine/matcher.py:_resolve_kickoff` was also hardened to
prefer the game closest to "now" among same-team matches, since the previous
first-substring-match behavior could anchor an edge's `commence_time` to an
old fixture and confuse this gate's timing.
