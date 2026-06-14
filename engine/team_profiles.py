"""Team form profiles (attack / defense / style) as context for the AI analyst.

Pure stats from FBref (scrapers/fbref_stats.py), never used to manufacture an
edge — just to tell Claude what each team has actually done this tournament,
since its training data can't see the live World Cup.
"""

from __future__ import annotations

import difflib
import json
import unicodedata
from pathlib import Path

TEAMS_FILE = Path("data/processed/fbref_wc_teams.json")

# FBref names vs the names books / PrizePicks use.
ALIASES = {
    "united states": "usa",
    "korea republic": "south korea",
    "ir iran": "iran",
    "turkiye": "turkey",
    "czechia": "czech republic",
    "bosnia-herzegovina": "bosnia",
}


def _norm(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    cleaned = " ".join(stripped.lower().split())
    return ALIASES.get(cleaned, cleaned)


def load_team_profiles(path: Path = TEAMS_FILE) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as file:
        return json.load(file)


def _match(name: str, by_norm: dict[str, dict]) -> dict | None:
    if not name:
        return None
    key = _norm(name)
    if key in by_norm:
        return by_norm[key]
    close = difflib.get_close_matches(key, list(by_norm), n=1, cutoff=0.82)
    return by_norm[close[0]] if close else None


def _attack_line(p: dict) -> str:
    g = p["per_game"]
    return (f"{g['shots']}/g shots, {g['shots_on_target']}/g on target, "
            f"{g['goals']}/g scored")


def _defense_line(p: dict) -> str:
    g = p["per_game"]
    cs = f", {p['clean_sheets']} clean sheet(s)" if p.get("clean_sheets") else ""
    return (f"{g['goals_allowed']}/g conceded, {g['shots_on_target_against']}/g "
            f"on target faced{cs}")


def _style_line(p: dict) -> str:
    g = p["per_game"]
    return (f"{g['fouls']}/g fouls, {g['crosses']}/g crosses, "
            f"{g['tackles']}/g tackles, {g['offsides']}/g offsides")


def team_form(team: str | None, opponent: str | None, profiles: list[dict] | None = None) -> dict:
    """Form lines for the player's team (attack/style) and the opponent (defense).

    Empty dict when no data — early in a tournament most teams haven't played.
    """
    profiles = load_team_profiles() if profiles is None else profiles
    if not profiles:
        return {}
    # Key by the alias-aware norm so book/PP names resolve to FBref names.
    by_norm = {_norm(p["team"]): p for p in profiles}

    own = _match(team, by_norm)
    opp = _match(opponent, by_norm)
    form: dict = {}
    if own:
        form["team_attack"] = _attack_line(own)
        form["team_style"] = _style_line(own)
        form["team_games"] = own["games"]
    if opp:
        form["opponent_defense"] = _defense_line(opp)
        form["opponent_games"] = opp["games"]
    return form
