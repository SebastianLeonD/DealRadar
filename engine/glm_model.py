"""Shadow model v2: "GLM-lite" Poisson regression for World Cup player props.

Three fitted coefficients per stat family (scripts/fit_glm_v2.py):

    log lambda = log(minutes / 90)            # exposure offset
               + b0                           # club->tournament level shift
               + b1 * log(prior90)            # EB pseudo-count player prior
               + b2 * log(opp)                # opponent concession multiplier

b1 < 1 is FITTED regression-to-the-mean — the one thing v1 asserts by fiat
(the 270-minute shrinkage constant). P(over) reuses the same push-adjusted
Poisson tail as v1 (engine/probability.py).

FIREWALL: every number here is ASSERTED/GATED (firewall_side='asserted_gated').
Predictions are logged to the model_predictions sidecar table only — they never
touch verdicts, flags, or sizing, and v1's model_* edge columns are untouched.
Failure semantics mirror v1: any missing input (no logs, no coefficient file,
stale fit, ineligible stat) -> glm_fields() returns None and the edge logs with
no glm_v2 row. The shadow path never raises into the matcher.

Inference is pure stdlib (math/json); numpy is only imported inside the IRLS
fitter, which runs offline in scripts/fit_glm_v2.py.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date as _date
from pathlib import Path

from engine.probability import poisson_p_over_push_adjusted
from engine.rate_prior import FALLBACK_BASELINES, rate_prior

MODEL_NAME = "glm_v2"
MODEL_SOURCE = "fbref_glm_v2"

COEFS_PATH = Path("data/processed/glm_v2_coefs.json")
CLUB_STATS_PATH = Path("data/processed/fbref_club_stats.json")

# Stat families the GLM is fitted for. The first five are the canonical PP
# markets served through the matcher hook; tackles/crosses are trained too
# (PP posts them as model-priced stats) but only canonical stats are served —
# price_model_edges never writes model_* fields.
GLM_FAMILIES = (
    "player_shots",
    "player_shots_on_target",
    "player_goals",
    "player_assists",
    "player_goalie_saves",
    "player_tackles",
    "player_crosses",
)

# stat_type -> field name in fbref_club_stats.json / fbref_wc_stats.json.
CLUB_FIELD = {
    "player_shots": "shots",
    "player_shots_on_target": "shots_on_target",
    "player_goals": "goals",
    "player_assists": "assists",
    "player_goalie_saves": "saves",
    "player_tackles": "tackles",
    "player_crosses": "crosses",
}

CLUB_MINUTES_CAP = 900.0        # club influence capped at ~10 full matches
BASELINE_PSEUDO_GAMES = 1.0     # one 90-minute pseudo-game of baseline
OPP_SHRINK_GAMES = 3.0          # (g*raw + 3) / (g + 3): 1-game noise -> ~1.0
CREDIBILITY_MINUTES = 270.0     # same half-weight constant as v1 (comparable buckets)
MIN_FAMILY_ROWS = 300           # fewer rows -> freeze beta at (0, 1, 1)
MIN_PSEUDO_MINUTES = 90.0       # training rows on a pure-baseline prior teach nothing
RIDGE_TAU = 1e-3
STALE_COEFS_DAYS = 21           # a fit older than this is treated as missing
RATE_FLOOR = 1e-4               # keeps log(prior90)/log(opp) finite

FROZEN_BETA = (0.0, 1.0, 1.0)   # degrades to "prior x opponent multiplier"


# ---------------------------------------------------------------------------
# Feature construction (ONE code path shared by training and inference)
# ---------------------------------------------------------------------------
def prior90(
    wc_stat: float,
    wc_minutes: float,
    club_per90: float | None,
    club_minutes: float | None,
    baseline: float,
) -> tuple[float, float]:
    """Gamma-conjugate pseudo-count blend of WC-to-date, club season, baseline.

    Returns (per-90 rate, informative_minutes) where informative_minutes is the
    WC + capped-club evidence behind the rate (baseline pseudo-game excluded).
    """
    m_c = min(club_minutes or 0.0, CLUB_MINUTES_CAP)
    numerator = (
        wc_stat
        + (club_per90 or 0.0) * m_c / 90.0
        + baseline * BASELINE_PSEUDO_GAMES
    )
    denominator = wc_minutes / 90.0 + m_c / 90.0 + BASELINE_PSEUDO_GAMES
    return max(numerator / denominator, RATE_FLOOR), wc_minutes + m_c


def team_rate_table(records: list[dict], stat_type: str) -> dict[str, list[float]]:
    """{team -> [games, opponent-relevant total]} from normalized match records.

    For shots/SoT/tackles/crosses the relevant quantity is what the team
    CONCEDES (opposing players' counts vs them). For saves the direction flips:
    a keeper's workload is the opponent's SoT PRODUCTION, so the table holds
    each team's own SoT for-side total.

    Records must already be restricted to "before now" by the caller — training
    passes strictly-before-date slices, inference passes everything.
    """
    produced = stat_type == "player_goalie_saves"
    quantity_stat = "player_shots_on_target" if produced else stat_type

    table: dict[str, list[float]] = {}
    games: dict[str, set] = {}
    for rec in records:
        if (rec.get("minutes") or 0) <= 0:
            continue
        team, opp, day = rec.get("team"), rec.get("opponent"), rec.get("date")
        credit_team = team if produced else opp
        if team and day is not None:
            games.setdefault(team, set()).add(day)
        if not credit_team:
            continue
        value = rec.get("stats", {}).get(quantity_stat, 0.0) or 0.0
        entry = table.setdefault(credit_team, [0.0, 0.0])
        entry[1] += value

    for team, days in games.items():
        table.setdefault(team, [0.0, 0.0])[0] = float(len(days))
    return table


def opponent_factor(table: dict[str, list[float]], opponent: str | None) -> float:
    """Shrunk-toward-1.0 multiplier for the opponent's concession/production
    rate relative to the tournament mean. Unresolvable -> 1.0 (degrade, not NULL)."""
    if not opponent or opponent not in table:
        return 1.0
    per_game = [tot / g for g, tot in table.values() if g > 0]
    tournament_mean = sum(per_game) / len(per_game) if per_game else 0.0
    if tournament_mean <= 0:
        return 1.0
    g, total = table[opponent]
    if g <= 0:
        return 1.0
    raw = (total / g) / tournament_mean
    return (g * raw + OPP_SHRINK_GAMES) / (g + OPP_SHRINK_GAMES)


def glm_lambda(beta: list[float], minutes: float, prior_rate: float, opp: float) -> float:
    """exp(offset + b0 + b1*log(prior90) + b2*log(opp)), overflow-guarded."""
    eta = (
        math.log(max(minutes, 1.0) / 90.0)
        + beta[0]
        + beta[1] * math.log(max(prior_rate, RATE_FLOOR))
        + beta[2] * math.log(max(opp, RATE_FLOOR))
    )
    return math.exp(min(max(eta, -20.0), 10.0))


# ---------------------------------------------------------------------------
# IRLS fitter (offline only; the single numpy import lives here)
# ---------------------------------------------------------------------------
def fit_poisson_irls(
    X, y, offset, *, tau: float = RIDGE_TAU, max_iter: int = 50, tol: float = 1e-8,
) -> tuple[list[float], bool]:
    """Newton-Raphson on the Poisson log-likelihood with a damped Hessian.

    beta <- beta + solve(X'WX + tau*I, X'(y - lambda)), W = diag(lambda).
    Warm start (log(global_mean_adj), 1, 1). Returns (beta, converged).
    """
    import numpy as np

    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    offset = np.asarray(offset, dtype=float)

    # Warm start: b1 = b2 = 1 and b0 matching total counts to total exposure.
    base = offset + X[:, 1] + X[:, 2]
    expected = float(np.exp(np.clip(base, -20.0, 10.0)).sum())
    b0 = math.log(max(y.sum(), 0.5) / max(expected, 1e-9))
    beta = np.array([b0, 1.0, 1.0])

    identity = np.eye(X.shape[1])
    for _ in range(max_iter):
        lam = np.exp(np.clip(offset + X @ beta, -20.0, 10.0))
        gradient = X.T @ (y - lam)
        hessian = X.T @ (X * lam[:, None]) + tau * identity
        try:
            step = np.linalg.solve(hessian, gradient)
        except np.linalg.LinAlgError:
            return list(FROZEN_BETA), False
        beta = beta + step
        if not np.all(np.isfinite(beta)):
            return list(FROZEN_BETA), False
        if float(np.linalg.norm(step)) < tol:
            return [float(b) for b in beta], True
    return [float(b) for b in beta], False


# ---------------------------------------------------------------------------
# Training rows (as-of, leak-free; used by scripts/fit_glm_v2.py and tests)
# ---------------------------------------------------------------------------
def build_training_rows(
    records: list[dict],
    stat_type: str,
    club_index: dict[str, dict],
    baseline: float,
) -> list[dict]:
    """One row per (player, match) for a family, with strictly-before-date
    expanding aggregates. Rows whose prior rests on < MIN_PSEUDO_MINUTES of
    real evidence are excluded (pure-baseline rows teach nothing about b1).

    club_index maps the FBref log player name -> club record (join done by the
    caller). Saves rows are restricted to keeper records (the keepers table only
    lists GKs, so presence of the stat is the position signal).
    """
    dated = [r for r in records if r.get("date") and (r.get("minutes") or 0) > 0]
    dated.sort(key=lambda r: r["date"])

    club_field = CLUB_FIELD[stat_type]
    rows: list[dict] = []
    player_cum: dict[str, list[float]] = {}   # player -> [stat_sum, minute_sum]
    seen: list[dict] = []                     # records strictly before current date

    index = 0
    while index < len(dated):
        day = dated[index]["date"]
        batch = []
        while index < len(dated) and dated[index]["date"] == day:
            batch.append(dated[index])
            index += 1

        table = team_rate_table(seen, stat_type)
        for rec in batch:
            if stat_type == "player_goalie_saves" and stat_type not in rec["stats"]:
                continue  # outfield row in the saves family
            wc_stat, wc_min = player_cum.get(rec["player"], (0.0, 0.0))
            club = club_index.get(rec["player"])
            club_per90 = (club or {}).get("per90", {}).get(club_field)
            club_minutes = (club or {}).get("minutes")
            rate, informative = prior90(wc_stat, wc_min, club_per90, club_minutes, baseline)
            if informative < MIN_PSEUDO_MINUTES:
                continue
            opp = opponent_factor(table, rec.get("opponent"))
            rows.append({
                "player": rec["player"],
                "date": day,
                "y": rec["stats"].get(stat_type, 0.0) or 0.0,
                "minutes": rec["minutes"],
                "prior90": rate,
                "opp": opp,
                "wc_stat_before": wc_stat,
                "wc_minutes_before": wc_min,
                "informative_minutes": informative,
            })

        for rec in batch:  # only after the whole matchday is priced
            cum = player_cum.setdefault(rec["player"], [0.0, 0.0])
            cum[0] += rec["stats"].get(stat_type, 0.0) or 0.0
            cum[1] += rec["minutes"]
            seen.append(rec)

    return rows


# ---------------------------------------------------------------------------
# Inference (matcher hook)
# ---------------------------------------------------------------------------
_coefs_cache: dict = {"path": None, "mtime": None, "data": None}
_club_cache: dict = {"path": None, "mtime": None, "by_name": None}
_club_match_cache: dict[str, str | None] = {}


def load_coefs(path: Path = COEFS_PATH) -> dict | None:
    """Coefficient file, mtime-cached. None when missing, unreadable, or stale."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _coefs_cache["path"] == str(path) and _coefs_cache["mtime"] == mtime:
        return _coefs_cache["data"]
    try:
        data = json.loads(Path(path).read_text())
    except Exception:  # noqa: BLE001 - shadow path must not break
        return None
    _coefs_cache.update({"path": str(path), "mtime": mtime, "data": data})
    return data


def _coefs_fresh(coefs: dict, today: str | None = None) -> bool:
    fit_through = coefs.get("fit_through")
    if not fit_through:
        return False
    try:
        fitted = _date.fromisoformat(str(fit_through)[:10])
        now = _date.fromisoformat(today) if today else _date.today()
    except ValueError:
        return False
    return (now - fitted).days <= STALE_COEFS_DAYS


def load_club_index(path: Path = CLUB_STATS_PATH) -> dict[str, dict]:
    """{normalized club player name -> club record}, mtime-cached, best-effort."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}
    if _club_cache["path"] == str(path) and _club_cache["mtime"] == mtime:
        return _club_cache["by_name"]
    try:
        rows = json.loads(Path(path).read_text())
        by_name = {r["normalized"]: r for r in rows if r.get("normalized")}
    except Exception:  # noqa: BLE001
        by_name = {}
    _club_cache.update({"path": str(path), "mtime": mtime, "by_name": by_name})
    _club_match_cache.clear()
    return by_name


def club_record_for(player: str, club_index: dict[str, dict]) -> dict | None:
    """Club-season record for an FBref log player name: exact normalized join
    first, fuzzy name match as fallback (design's id-join replaced — see docs)."""
    if not club_index:
        return None
    from scrapers.fbref_stats import normalize

    key = normalize(player)
    if key in club_index:
        return club_index[key]
    if key not in _club_match_cache:
        from engine.name_matcher import match_player_name

        matched, _ = match_player_name(key, list(club_index))
        _club_match_cache[key] = matched
    matched = _club_match_cache[key]
    return club_index.get(matched) if matched else None


def resolve_opponent_team(opponent: str | None, records: list[dict]) -> str | None:
    """Map a book-side opponent name ('South Korea') to the FBref team name in
    the logs ('Korea Republic'). None when it can't be matched confidently."""
    if not opponent:
        return None
    teams = sorted({r.get("team") for r in records if r.get("team")})
    if opponent in teams:
        return opponent
    from engine.name_matcher import match_player_name

    matched, _ = match_player_name(opponent, teams)
    return matched


def glm_fields(
    sharp_name: str,
    stat_type: str,
    line: float,
    play: str,
    *,
    logs: list[dict],
    logs_by_player: dict[str, list[dict]],
    opponent: str | None = None,
    coefs_path: Path = COEFS_PATH,
    club_path: Path = CLUB_STATS_PATH,
) -> dict | None:
    """glm_v2 sidecar fields for one prop, or None (= no row logged).

    Reads nothing from the market evaluation — firewall-clean vs the
    Brier-vs-consensus test. Never raises.
    """
    try:
        coefs = load_coefs(coefs_path)
        if not coefs or not _coefs_fresh(coefs):
            return None
        family = (coefs.get("families") or {}).get(stat_type)
        if not family or not family.get("beta"):
            return None

        played = [r for r in logs if (r.get("minutes") or 0) > 0]
        if not played:
            return None  # no WC appearances -> no expected-minutes basis

        prior = rate_prior(logs, stat_type)  # reuse v1's avg-minutes logic
        expected_minutes = prior["avg_minutes"] or 0.0
        if expected_minutes <= 0:
            return None

        wc_stat = sum(r.get("stats", {}).get(stat_type, 0.0) or 0.0 for r in played)
        wc_minutes = sum(r.get("minutes") or 0.0 for r in played)

        club = club_record_for(sharp_name, load_club_index(club_path))
        club_per90 = (club or {}).get("per90", {}).get(CLUB_FIELD[stat_type])
        club_minutes = (club or {}).get("minutes")
        baseline = family.get("baseline")
        if baseline is None:
            baseline = FALLBACK_BASELINES.get(stat_type, 1.0)

        rate, informative = prior90(wc_stat, wc_minutes, club_per90, club_minutes, baseline)

        all_records = [rec for recs in logs_by_player.values() for rec in recs]
        table = team_rate_table(all_records, stat_type)
        opp = opponent_factor(table, resolve_opponent_team(opponent, all_records))

        lam = glm_lambda(family["beta"], expected_minutes, rate, opp)
        p_over = round(poisson_p_over_push_adjusted(lam, line), 4)
        p_side = p_over if play == "OVER" else round(1.0 - p_over, 4)
        credibility = informative / (informative + CREDIBILITY_MINUTES)
        return {
            "model_p": p_over,
            "model_p_side": p_side,
            "model_lambda": round(lam, 4),
            "model_credibility": round(credibility, 4),
            "model_n_matches": len(played),
            "model_source": MODEL_SOURCE,
        }
    except Exception:  # noqa: BLE001 - shadow lane: a miss must never cost an edge
        return None
