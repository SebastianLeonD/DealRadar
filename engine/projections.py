"""Model-based pricing for PrizePicks stats no sportsbook posts.

Books price shots/SoT/goals/assists for soccer and nothing else. PrizePicks
posts saves, fouls, tackles, crosses, offsides too — so for those we replace the
missing market line with our own projection from a player's World Cup form
(see scrapers/fbref_stats.py).

A player's expected count next match = (tournament total) / (matches played),
i.e. their per-game average assuming a similar role. That rate feeds the same
push-adjusted Poisson the rest of the engine uses, so win probabilities are
comparable. These plays are ALWAYS flagged (modeled, not market-verified), which
caps their verdict at LEAN.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from engine.name_matcher import match_player_name
from engine.probability import assign_verdict, ev_percent, poisson_p_over_push_adjusted

FBREF_FILE = Path("data/processed/fbref_wc_stats.json")

# PrizePicks stat_type -> the FBref field that measures it. Only stats the books
# don't price live here; shots/SoT/goals stay on the sharp-book path.
FIELD_BY_STAT = {
    "player_goalie_saves": "saves",
    "player_fouls": "fouls",
    "player_fouls_drawn": "fouls_drawn",
    "player_tackles": "tackles",
    "player_crosses": "crosses",
    "player_offsides": "offsides",
    "player_goals_allowed": "goals_allowed",
}

MIN_GAMES_FOR_CONFIDENCE = 2  # one match is too small a sample to trust

# Broader map (incl. book-priced stats) for AI *form context* — not pricing.
# Lets the stats-only analyst show a player's rate for any stat we track.
FORM_FIELD_BY_STAT = {
    "player_shots": "shots",
    "player_shots_on_target": "shots_on_target",
    "player_goals": "goals",
    "player_assists": "assists",
    **FIELD_BY_STAT,
}


def model_stat_types() -> list[str]:
    return list(FIELD_BY_STAT)


def player_form(name: str, stat_type: str, players: list[dict] | None = None) -> dict | None:
    """A player's tournament rate for one stat, for AI context. None if unknown.

    1H props (e.g. player_shots_1h) fall back to the full-match rate.
    """
    players = load_fbref_stats() if players is None else players
    base = stat_type.replace("_1h", "") if stat_type else ""
    field = FORM_FIELD_BY_STAT.get(base)
    if not field or not players:
        return None

    target = _normalize(name)
    record = next((p for p in players if p["normalized"] == target), None)
    if record is None:
        sharp_name, _ = match_player_name(name, [p["player"] for p in players])
        if not sharp_name:
            return None
        record = next(p for p in players if p["player"] == sharp_name)

    games = record.get("matches_played") or 0
    if not games:
        return None
    total = record.get(field) or 0.0
    return {
        "stat": field,
        "per_game": round(total / games, 2),
        "per90": (record.get("per90") or {}).get(field),
        "games": int(games),
        "minutes": int(record.get("minutes") or 0),
        "matched_name": record["player"],
    }


def load_fbref_stats(path: Path = FBREF_FILE) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as file:
        return json.load(file)


def _normalize(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def project_prop(
    pp_name: str,
    stat_type: str,
    pp_line: float,
    players: list[dict],
) -> dict | None:
    """Price one PP prop against the player's FBref form. None if unmodelable."""
    field = FIELD_BY_STAT.get(stat_type)
    if field is None or not players:
        return None

    # Match by normalized name (handles accents); fall back to fuzzy.
    target = _normalize(pp_name)
    record = next((p for p in players if p["normalized"] == target), None)
    match_score = 1.0
    if record is None:
        names = [p["player"] for p in players]
        sharp_name, score = match_player_name(pp_name, names)
        if not sharp_name:
            return None
        record = next(p for p in players if p["player"] == sharp_name)
        match_score = score

    games = record.get("matches_played") or 0
    total = record.get(field) or 0.0
    if not games:
        return None

    lam = total / games  # expected count next match given a similar role
    over = poisson_p_over_push_adjusted(lam, pp_line)
    play = "OVER" if over >= 0.5 else "UNDER"
    win_prob = over if play == "OVER" else 1 - over

    flags = ["Modeled from World Cup form — no betting market exists"]
    if games < MIN_GAMES_FOR_CONFIDENCE:
        flags.append(f"Small sample: only {int(games)} match played so far")

    return {
        "play": play,
        "win_prob": round(win_prob, 4),
        "ev_percent": ev_percent(win_prob),
        "verdict": assign_verdict(win_prob, flags),  # flagged -> caps at LEAN
        "flags": flags,
        "matched_name": record["player"],
        "match_score": match_score,
        "expected": round(lam, 2),
        "games": int(games),
        "team": record.get("team"),
    }
