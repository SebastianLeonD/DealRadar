"""Minutes-weighted, shrunk per-90 rate priors for soccer stats.

A player's recent FBref logs give a noisy read on their underlying rate: a
striker can take 0 shots one match and 6 the next, and a 20-minute cameo is not
the same evidence as a full 90. So we do NOT trust a raw "last game" number.
Instead we estimate a per-90 rate that is:

  * minutes-weighted — sum(stat) / sum(minutes) * 90, so cameos count less;
  * shrunk toward a baseline — an empirical-Bayes credibility blend that pulls a
    thin sample toward a positional/team baseline and only trusts the player's
    own rate once enough minutes have accrued.

The output feeds the (asserted, calibration-gated) soccer model in
engine/soccer_model.py. It never flags a bet on its own.
"""

from __future__ import annotations

# Credibility half-weight, in minutes: at this many observed minutes the blend
# is 50/50 player-vs-baseline. ~3 full matches is a deliberately cautious floor.
DEFAULT_SHRINKAGE_MINUTES = 270.0

# Conservative fallback baselines (per-90) when no team/positional baseline is
# supplied. Calibrated loosely to typical World Cup outfield volume; the model
# is gated, so these are starting points, not asserted truth.
FALLBACK_BASELINES = {
    "player_shots": 1.2,
    "player_shots_on_target": 0.45,
    "player_goals": 0.18,
    "player_assists": 0.13,
    "player_goalie_saves": 3.0,
}


def minutes_weighted_rate(logs: list[dict], stat_type: str) -> tuple[float | None, float]:
    """Per-90 rate weighted by minutes, plus total minutes observed.

    `logs` are normalized match records (scrapers.fbref_api). Returns
    (rate_per_90 or None if no minutes, total_minutes).
    """
    total_stat = 0.0
    total_minutes = 0.0
    for rec in logs:
        minutes = rec.get("minutes") or 0.0
        if minutes <= 0:
            continue
        total_minutes += minutes
        total_stat += rec.get("stats", {}).get(stat_type, 0.0)
    if total_minutes <= 0:
        return None, 0.0
    return total_stat / total_minutes * 90.0, total_minutes


def shrunk_rate(
    player_rate: float | None,
    total_minutes: float,
    baseline_rate: float,
    *,
    shrinkage_minutes: float = DEFAULT_SHRINKAGE_MINUTES,
) -> dict:
    """Credibility-blend a player's per-90 rate toward a baseline.

    weight w = total_minutes / (total_minutes + shrinkage_minutes); the shrunk
    rate is w * player_rate + (1 - w) * baseline_rate. With no player data the
    baseline stands (w = 0). Returns {rate, weight, baseline, player_rate}.
    """
    if player_rate is None or total_minutes <= 0:
        return {"rate": baseline_rate, "weight": 0.0,
                "baseline": baseline_rate, "player_rate": None}
    w = total_minutes / (total_minutes + shrinkage_minutes)
    rate = w * player_rate + (1.0 - w) * baseline_rate
    return {"rate": rate, "weight": round(w, 4),
            "baseline": baseline_rate, "player_rate": player_rate}


def rate_prior(
    logs: list[dict],
    stat_type: str,
    *,
    baseline_rate: float | None = None,
    shrinkage_minutes: float = DEFAULT_SHRINKAGE_MINUTES,
) -> dict:
    """End-to-end per-90 rate prior for one player/stat from their recent logs.

    Returns {rate, weight, baseline, player_rate, total_minutes, n_matches,
    avg_minutes} — `rate` is the shrunk per-90 estimate the model consumes, and
    `avg_minutes` is a starting guess for expected minutes (capped at 90).
    """
    if baseline_rate is None:
        baseline_rate = FALLBACK_BASELINES.get(stat_type, 1.0)
    player_rate, total_minutes = minutes_weighted_rate(logs, stat_type)
    blended = shrunk_rate(player_rate, total_minutes, baseline_rate,
                          shrinkage_minutes=shrinkage_minutes)
    played = [r for r in logs if (r.get("minutes") or 0) > 0]
    avg_minutes = (total_minutes / len(played)) if played else 0.0
    blended.update({
        "total_minutes": total_minutes,
        "n_matches": len(played),
        "avg_minutes": min(90.0, round(avg_minutes, 1)),
        "stat_type": stat_type,
    })
    return blended
