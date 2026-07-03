"""Fit shadow model v2 (GLM-lite Poisson regression) from cached FBref data.

User-run after each matchday, once soccerdata has cached the new match pages
(they are cached by any settlement/scraper run that touches FBref, or by this
script's own rebuild step):

    source venv/bin/activate
    python scripts/fit_glm_v2.py                # rebuild logs + fit + write coefs
    python scripts/fit_glm_v2.py --skip-rebuild # fit from existing fbref_logs.json

Steps (all resumable — soccerdata never refetches a cached page):
  1. Re-normalize data/processed/fbref_logs.json from the cached soccerdata
     match pages (summary + keepers tables merged, real stats/date/opponent).
  2. Build leak-free training rows per stat family (strictly-before-date
     expanding aggregates, pre-season club priors — engine/glm_model.py).
  3. IRLS-fit 3 coefficients per family; report a group-stage/knockout holdout
     (Poisson NLL + Brier at synthetic lines vs the v1 formula on identical
     player-match rows).
  4. Write data/processed/glm_v2_coefs.json (final fit on ALL matches to date).

Never touches The-Odds-API. Network use is FBref-via-soccerdata only, and only
for match pages not already in ~/soccerdata/data/FBref/.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.glm_model import (
    COEFS_PATH,
    FROZEN_BETA,
    GLM_FAMILIES,
    MIN_FAMILY_ROWS,
    MODEL_SOURCE,
    build_training_rows,
    fit_poisson_irls,
    glm_lambda,
)
from engine.name_matcher import match_player_name, normalize_name
from engine.probability import poisson_p_over_push_adjusted
from engine.rate_prior import FALLBACK_BASELINES, shrunk_rate
from engine.shadow_model import DEFAULT_LOG_CACHE
from scrapers.fbref_api import fetch_player_match_stats, normalize_player_match_rows
from scrapers.fbref_stats import normalize
from storage.db_manager import utc_now

GROUP_STAGE_END = "2026-06-27"          # train/holdout split (time-based)
SYNTHETIC_LINES = (0.5, 1.5, 2.5)       # offline Brier sanity lines
CLUB_STATS_PATH = Path("data/processed/fbref_club_stats.json")
CLUB_JOIN_CACHE = Path("data/processed/glm_v2_club_join.json")


# ---------------------------------------------------------------------------
# Step 1 — rebuild the normalized match-log cache from cached soccerdata HTML
# ---------------------------------------------------------------------------
def rebuild_logs(season: str = "2026") -> list[dict]:
    print("[1/4] Re-normalizing FBref match logs from the soccerdata cache...")
    summary = fetch_player_match_stats(season)
    print(f"      summary table: {len(summary)} player-match rows")
    try:
        keepers = fetch_player_match_stats(season, stat_type="keepers")
    except Exception as error:  # noqa: BLE001 - keepers are additive, not blocking
        print(f"      keepers table unavailable ({error}); saves rows skipped")
        keepers = []
    print(f"      keepers table: {len(keepers)} keeper-match rows")

    by_key = {(r["player"], r["team"], r["date"]): r for r in summary}
    merged_saves = 0
    for rec in keepers:
        key = (rec["player"], rec["team"], rec["date"])
        target = by_key.get(key)
        saves = rec["stats"].get("player_goalie_saves")
        if target is not None and saves is not None:
            target["stats"]["player_goalie_saves"] = saves
            merged_saves += 1
        elif target is None:
            summary.append(rec)
            merged_saves += 1
    print(f"      merged saves into {merged_saves} keeper rows")

    DEFAULT_LOG_CACHE.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_LOG_CACHE.write_text(json.dumps(summary))
    with_stats = sum(1 for r in summary if r.get("stats"))
    dates = sorted({r["date"] for r in summary if r.get("date")})
    print(f"      wrote {len(summary)} records ({with_stats} with stats, "
          f"{dates[0] if dates else '?'} .. {dates[-1] if dates else '?'}) "
          f"-> {DEFAULT_LOG_CACHE}")
    return summary


def load_logs() -> list[dict]:
    records = normalize_player_match_rows(json.loads(DEFAULT_LOG_CACHE.read_text()))
    with_stats = sum(1 for r in records if r.get("stats"))
    if not with_stats:
        raise SystemExit(
            "fbref_logs.json has no per-match stats — run without --skip-rebuild "
            "so the cache is re-normalized first."
        )
    return records


# ---------------------------------------------------------------------------
# Step 2 — club join (exact normalized name, token-prefiltered fuzzy fallback)
# ---------------------------------------------------------------------------
def build_club_index(records: list[dict]) -> dict[str, dict]:
    if not CLUB_STATS_PATH.exists():
        print("      no fbref_club_stats.json — training on WC-only priors")
        return {}
    club_rows = json.loads(CLUB_STATS_PATH.read_text())
    by_norm = {r["normalized"]: r for r in club_rows if r.get("normalized")}

    cached: dict[str, str | None] = {}
    if CLUB_JOIN_CACHE.exists():
        try:
            cached = json.loads(CLUB_JOIN_CACHE.read_text())
        except Exception:  # noqa: BLE001
            cached = {}

    players = sorted({r["player"] for r in records})
    tokens_of = {name: set(normalize_name(name).split()) for name in by_norm}
    index: dict[str, dict] = {}
    exact = fuzzy = 0
    for i, player in enumerate(players):
        if i and i % 200 == 0:
            print(f"      club join {i}/{len(players)}...")
        key = normalize(player)
        if key in by_norm:
            index[player] = by_norm[key]
            exact += 1
            continue
        if player in cached:
            match = cached[player]
        else:
            mine = set(normalize_name(player).split())
            candidates = [n for n, toks in tokens_of.items() if toks & mine]
            match, _ = match_player_name(player, candidates)
            cached[player] = match
        if match:
            index[player] = by_norm[match]
            fuzzy += 1

    CLUB_JOIN_CACHE.write_text(json.dumps(cached, ensure_ascii=False))
    print(f"      club join: {exact} exact + {fuzzy} fuzzy of {len(players)} log players")
    return index


# ---------------------------------------------------------------------------
# Step 3 — per-family fit + holdout report
# ---------------------------------------------------------------------------
def family_baseline(records: list[dict], stat_type: str, through: str) -> float:
    """Fallback per-90 baseline: v1's constants where they exist, else the
    tournament per-90 mean computed from matches up to `through` only."""
    if stat_type in FALLBACK_BASELINES:
        return FALLBACK_BASELINES[stat_type]
    stat = minutes = 0.0
    for rec in records:
        if not rec.get("date") or rec["date"] > through or (rec.get("minutes") or 0) <= 0:
            continue
        stat += rec["stats"].get(stat_type, 0.0) or 0.0
        minutes += rec["minutes"]
    return max(stat / minutes * 90.0, 1e-3) if minutes > 0 else 1.0


def _design(rows: list[dict]):
    X = [[1.0, math.log(r["prior90"]), math.log(r["opp"])] for r in rows]
    y = [r["y"] for r in rows]
    offset = [math.log(max(r["minutes"], 1.0) / 90.0) for r in rows]
    return X, y, offset


def _poisson_nll(lam: float, y: float) -> float:
    lam = max(lam, 1e-9)
    return lam - y * math.log(lam) + math.lgamma(y + 1.0)


def _v1_p_over(row: dict, stat_type: str, line: float) -> float:
    """What v1's formula (270-min EB shrink, no opponent) would say for this
    player-match row, using the same as-of history and actual minutes."""
    wc_min = row["wc_minutes_before"]
    player_rate = (row["wc_stat_before"] / wc_min * 90.0) if wc_min > 0 else None
    baseline = FALLBACK_BASELINES.get(stat_type, 1.0)
    rate = shrunk_rate(player_rate, wc_min, baseline)["rate"]
    return poisson_p_over_push_adjusted(rate * row["minutes"] / 90.0, line)


def holdout_report(rows: list[dict], beta: list[float], stat_type: str) -> dict:
    test = [r for r in rows if r["date"] > GROUP_STAGE_END]
    if not test:
        return {"n_test": 0}
    nll = brier_glm = brier_v1 = 0.0
    n_briers = 0
    for row in test:
        lam = glm_lambda(beta, row["minutes"], row["prior90"], row["opp"])
        nll += _poisson_nll(lam, row["y"])
        for line in SYNTHETIC_LINES:
            outcome = 1.0 if row["y"] > line else 0.0
            brier_glm += (poisson_p_over_push_adjusted(lam, line) - outcome) ** 2
            brier_v1 += (_v1_p_over(row, stat_type, line) - outcome) ** 2
            n_briers += 1
    return {
        "n_test": len(test),
        "nll": round(nll / len(test), 4),
        "brier_glm": round(brier_glm / n_briers, 4),
        "brier_v1": round(brier_v1 / n_briers, 4),
    }


def fit_family(records: list[dict], stat_type: str, club_index: dict[str, dict],
               fit_through: str) -> dict | None:
    baseline = family_baseline(records, stat_type, GROUP_STAGE_END)
    rows = build_training_rows(records, stat_type, club_index, baseline)
    if not rows:
        print(f"      {stat_type}: no training rows — family skipped")
        return None

    train = [r for r in rows if r["date"] <= GROUP_STAGE_END]
    holdout = {"n_test": 0}
    if len(train) >= MIN_FAMILY_ROWS:
        eval_beta, _ = fit_poisson_irls(*_design(train))
        holdout = holdout_report(rows, eval_beta, stat_type)

    frozen = len(rows) < MIN_FAMILY_ROWS
    if frozen:
        beta, converged = list(FROZEN_BETA), True
        print(f"      {stat_type}: {len(rows)} rows < {MIN_FAMILY_ROWS} — "
              f"beta frozen at {FROZEN_BETA} (prior x opponent only)")
    else:
        # Final coefficients: refit on ALL matches strictly before today.
        beta, converged = fit_poisson_irls(*_design(rows))
        if not converged:
            beta, frozen = list(FROZEN_BETA), True
        print(f"      {stat_type}: n={len(rows)} "
              f"beta=({beta[0]:+.3f}, {beta[1]:.3f}, {beta[2]:.3f}) "
              + (f"holdout n={holdout['n_test']} NLL={holdout.get('nll')} "
                 f"Brier glm={holdout.get('brier_glm')} v1={holdout.get('brier_v1')}"
                 if holdout["n_test"] else "(no knockout holdout rows)"))
    return {
        "beta": beta,
        "n_rows": len(rows),
        "frozen": frozen,
        "baseline": round(baseline, 4),
        "holdout": holdout,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-rebuild", action="store_true",
                        help="fit from the existing fbref_logs.json without "
                             "re-parsing the soccerdata cache")
    parser.add_argument("--season", default="2026")
    args = parser.parse_args()

    records = load_logs() if args.skip_rebuild else rebuild_logs(args.season)
    if args.skip_rebuild:
        print(f"[1/4] Using existing {DEFAULT_LOG_CACHE} ({len(records)} records)")

    print("[2/4] Joining club-season priors (2025-26 Big-5, pre-tournament)...")
    club_index = build_club_index(records)

    fit_through = max((r["date"] for r in records if r.get("date")), default=None)
    if fit_through is None:
        raise SystemExit("No dated match records — cannot fit.")

    print(f"[3/4] Fitting Poisson IRLS per family (fit_through={fit_through}, "
          f"holdout = matches after {GROUP_STAGE_END})...")
    families = {}
    for stat_type in GLM_FAMILIES:
        result = fit_family(records, stat_type, club_index, fit_through)
        if result:
            families[stat_type] = result

    payload = {
        "model_source": MODEL_SOURCE,
        "fit_through": fit_through,
        "fitted_at": utc_now(),
        "group_stage_end": GROUP_STAGE_END,
        "families": families,
    }
    COEFS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COEFS_PATH.write_text(json.dumps(payload, indent=2))
    print(f"[4/4] Wrote {len(families)} family fit(s) -> {COEFS_PATH}")


if __name__ == "__main__":
    main()
