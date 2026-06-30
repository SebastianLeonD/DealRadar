"""Versioned config primitives (council master-spec OBJ-41).

Every sourced tunable the engine depends on lives here with a CONFIG_VERSION
stamp so any historical edge/verdict is reproducible: the version is written
onto each edge row, and changing a primitive bumps the version. Nothing in the
identified or asserted layers may hardcode one of these numbers elsewhere.

Firewall note: these are *inputs*, not learned quantities. The ones that drive
identified verdicts (MIN_BOOKS_FOR_CONSENSUS, SNAPSHOT_GRAN, STALE_MAX) are
structural; the ones that size risk (rho0, KELLY_FRACTION) are conservative
Phase-1 priors that the calibration loop later replaces.
"""

from __future__ import annotations

# Bump whenever any primitive below changes. Stamped onto edges for replay.
CONFIG_VERSION = "2026.06.30-phase0"
EFFECTIVE_DATE = "2026-06-30"

# --- Consensus (identified) -------------------------------------------------
# A line-matched consensus needs at least this many genuinely two-sided books
# quoting the SAME line before it earns the 'identified' tag (OBJ-1/3).
MIN_BOOKS_FOR_CONSENSUS = 2

# Contemporaneity: books are only averaged within one snapshot bucket, and a
# quote older than STALE_MAX is dropped from that bucket (OBJ-21..24).
SNAPSHOT_GRAN_MINUTES = 5
STALE_MAX_MINUTES = 15

# Drop a book whose two-way booksum exceeds this (pathological hold) (OBJ-1).
HOLD_CEILING = 1.10

# --- De-vig (identified) ----------------------------------------------------
# Default per-book de-vig method. Shin's insider fraction z is solved from the
# same Over/Under price pair, so the output is fully determined (OBJ-5).
DEFAULT_DEVIG_METHOD = "shin"

# --- Risk priors (asserted / gated) -----------------------------------------
# Conservative Phase-1 correlation prior for two legs in the same game; 0 for
# cross-game. Phase-3 replaces this with a shrinkage-estimated matrix (OBJ-16).
RHO0_SAME_GAME = 0.15
RHO0_CROSS_GAME = 0.0

# Fractional Kelly multiplier (Phase-1). Full Kelly on shared-leg parlays is
# ruinous; quarter-Kelly is the conservative default (OBJ-36/38).
KELLY_FRACTION = 0.25
# Flat-stake baseline Kelly must beat OOS is a FRACTION of current bankroll
# (compounding), not a fixed dollar unit (OBJ-38).
BASELINE_STAKE_FRACTION = 0.01

# --- Calibration gates (identified loop) ------------------------------------
# An independent-game floor before a stratum can earn a CALIBRATED verdict;
# strata collapse up a fixed hierarchy until this is met (OBJ-9).
MIN_INDEPENDENT_GAMES = 200
MIN_SETTLED_SLIPS = 100
# False-discovery rate for the per-stratum paired-bootstrap Brier test (OBJ-10).
FDR_ALPHA = 0.05

# Every clustered statistic (Brier bootstrap-t AND reliability-slope SE) abstains
# below this many DISTINCT games — the cluster-robust meat has rank <= G, so SEs
# below the floor are spurious (Phase-2 spec §0.5). Separate from, and smaller
# than, the larger MIN_INDEPENDENT_GAMES verdict gate.
MIN_CLUSTERS_FOR_TEST = 30
CALIB_BOOTSTRAP_R = 2000          # bootstrap-t resamples
CALIB_BOOTSTRAP_SEED = 1234567    # fixed: run_calibration is reproducible
# Reliability slope: the gate is the point-null "CI covers 1.0"; this practical
# band is a reported diagnostic only (Phase-2 spec §0.3).
RELIABILITY_SLOPE_LO = 0.85
RELIABILITY_SLOPE_HI = 1.15
SE_DEGENERACY_REL = 1e-9          # below this total-SS the paired d is constant -> abstain

# --- Settlement (Phase-2) ---------------------------------------------------
# Strict minutes floor per sport: minutes < floor -> VOID (a recorded 0.0 with a
# 0.0 floor is NOT voided). Partial-game floor flags but retains the row.
PP_MIN_MINUTES = {"nba": 0.0}
PP_PARTIAL_FLOOR = {"nba": 12.0}
STALE_SETTLE_MAX_HOURS = 72       # deterministic force-VOID horizon (replayable)

# --- Credit / robustness (engineering) --------------------------------------
MAX_CREDITS_PER_SLATE = 500
# Deterministic truncation order: keep the sharpest books, drop the rest first
# (reverse priority). A budget-truncated line withholds the identified tag.
BOOK_PRIORITY = ("pinnacle", "draftkings", "fanduel", "betmgm", "williamhill_us")
HTTP_TIMEOUT_SECONDS = 10.0
HTTP_MAX_RETRIES = 4
HTTP_BACKOFF_BASE_SECONDS = 0.5


def snapshot_bucket(captured_at_iso: str) -> str:
    """Floor an ISO timestamp to the SNAPSHOT_GRAN bucket (OBJ-21).

    Books are only compared within one bucket so consensus is contemporaneous.
    """
    from datetime import datetime, timezone

    ts = datetime.fromisoformat(captured_at_iso.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    floored_minute = (ts.minute // SNAPSHOT_GRAN_MINUTES) * SNAPSHOT_GRAN_MINUTES
    bucket = ts.replace(minute=floored_minute, second=0, microsecond=0)
    return bucket.isoformat()
