"""Pull World Cup player stats from FBref (via soccerdata) for model-based pricing.

PrizePicks posts many soccer stats no sportsbook prices (saves, fouls, tackles,
crosses, offsides). No book line exists to compare against, so we build our own
projection from a player's tournament form instead. This scraper gathers the raw
material: each WC player's season-to-date totals + per-90 rates.

FBref's World Cup feed is the simplified Opta box score, so it covers
shots/SoT/goals, fouls/fouls-drawn/offsides/crosses/tackles-won/interceptions,
and goalkeeper saves/goals-against. It does NOT carry passes, dribbles, key
passes, or clearances for international tournaments — those live only in
domestic-league data.

soccerdata clears FBref's Cloudflare with undetected-chromedriver and caches
every page locally, so re-runs are fast and only new matches trigger a fetch.

Run:  .venv/bin/python scrapers/fbref_stats.py
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soccerdata as sd

from engine.sports import get_sport

OUTPUT_FILE = Path("data/processed/fbref_wc_stats.json")
TEAMS_FILE = Path("data/processed/fbref_wc_teams.json")
LEAGUE = "INT-World Cup"
SEASON = "2026"

# FBref column -> our flat field name, grouped by the season table that holds it.
TABLE_FIELDS = {
    "standard": {
        "MP": "matches_played",
        "Min": "minutes",
        "90s": "nineties",
        "Gls": "goals",
        "Ast": "assists",
    },
    "shooting": {"Sh": "shots", "SoT": "shots_on_target"},
    "misc": {
        "Fls": "fouls",
        "Fld": "fouls_drawn",
        "Off": "offsides",
        "Crs": "crosses",
        "TklW": "tackles",
        "Int": "interceptions",
    },
    "keeper": {"Saves": "saves", "GA": "goals_allowed", "SoTA": "shots_on_target_against"},
}

# Team-level tables -> a per-team attack / defense / style profile. Same 5
# summary tables FBref exposes for the tournament; used only as AI context
# (never to manufacture an edge).
TEAM_TABLE_FIELDS = {
    "standard": {"MP": "games", "90s": "nineties"},
    "shooting": {"Sh": "shots", "SoT": "shots_on_target", "Gls": "goals", "G/Sh": "goals_per_shot"},
    "keeper": {
        "GA": "goals_allowed",
        "SoTA": "shots_on_target_against",
        "Saves": "saves",
        "CS": "clean_sheets",
        "Save%": "save_pct",
    },
    "misc": {
        "Fls": "fouls",
        "Fld": "fouls_drawn",
        "Off": "offsides",
        "Crs": "crosses",
        "TklW": "tackles",
        "Int": "interceptions",
    },
}

# Counting fields turned into per-game rates in the team profile.
TEAM_PER_GAME = [
    "shots", "shots_on_target", "goals", "goals_allowed", "shots_on_target_against",
    "saves", "fouls", "fouls_drawn", "offsides", "crosses", "tackles", "interceptions",
]


def normalize(name: str) -> str:
    """Accent- and case-insensitive key for matching FBref names to PP names."""
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def _flatten(column) -> str:
    return column[1] if isinstance(column, tuple) else column


def collect_players(fb: "sd.FBref") -> dict[tuple[str, str], dict]:
    """Merge the WC season tables into one record per (team, player)."""
    players: dict[tuple[str, str], dict] = {}

    for table, fields in TABLE_FIELDS.items():
        frame = fb.read_player_season_stats(stat_type=table)
        frame.columns = [_flatten(c) for c in frame.columns]
        # FBref repeats some names (e.g. Gls as a total and as a per-90); the
        # raw total comes first, which is what we want.
        frame = frame.loc[:, ~frame.columns.duplicated()]
        for (_, _, team, player), row in frame.iterrows():
            record = players.setdefault(
                (team, player),
                {"player": player, "team": team, "normalized": normalize(player)},
            )
            for source_col, field in fields.items():
                if source_col in frame.columns:
                    value = row[source_col]
                    record[field] = None if value != value else float(value)  # NaN-safe

    return players


def collect_teams(fb: "sd.FBref") -> list[dict]:
    """Build one attack/defense/style profile per team from the season tables."""
    teams: dict[str, dict] = {}

    for table, fields in TEAM_TABLE_FIELDS.items():
        frame = fb.read_team_season_stats(stat_type=table)
        frame.columns = [_flatten(c) for c in frame.columns]
        frame = frame.loc[:, ~frame.columns.duplicated()]
        for index, row in frame.iterrows():
            team = index[-1]  # (league, season, team)
            record = teams.setdefault(team, {"team": team, "normalized": normalize(team)})
            for source_col, field in fields.items():
                if source_col in frame.columns:
                    value = row[source_col]
                    record[field] = None if value != value else float(value)

    profiles = []
    for record in teams.values():
        nineties = record.get("nineties") or 0.0
        if not nineties:
            continue
        per_game = {
            field: round((record.get(field) or 0.0) / nineties, 2)
            for field in TEAM_PER_GAME
        }
        profiles.append({
            "team": record["team"],
            "normalized": record["normalized"],
            "games": int(record.get("games") or 0),
            "per_game": per_game,
            "goals_per_shot": record.get("goals_per_shot"),
            "save_pct": record.get("save_pct"),
            "clean_sheets": int(record.get("clean_sheets") or 0),
        })
    profiles.sort(key=lambda p: p["games"], reverse=True)
    return profiles


def with_rates(record: dict) -> dict:
    """Add per-90 rates; FBref leaves zeros blank, so missing counts read as 0."""
    nineties = record.get("nineties") or 0.0
    counting = [
        "goals", "assists", "shots", "shots_on_target", "fouls", "fouls_drawn",
        "offsides", "crosses", "tackles", "interceptions", "saves", "goals_allowed",
    ]
    per90 = {}
    for field in counting:
        total = record.get(field) or 0.0
        per90[field] = round(total / nineties, 3) if nineties else None
    record["per90"] = per90
    return record


def main():
    sport = get_sport()
    if sport["odds_api_key"] != "soccer_fifa_world_cup":
        print(f"Warning: ACTIVE_SPORT is '{sport['label']}', not World Cup. "
              "FBref WC stats only apply to the World Cup board.")

    print(f"Fetching FBref {LEAGUE} {SEASON} season stats (Cloudflare-protected, "
          "first run is slow)...")
    fb = sd.FBref(leagues=LEAGUE, seasons=SEASON)

    players = collect_players(fb)
    records = [with_rates(record) for record in players.values()]
    records = [r for r in records if (r.get("minutes") or 0) > 0]
    records.sort(key=lambda r: r.get("minutes") or 0, reverse=True)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w") as file:
        json.dump(records, file, indent=2)

    teams = sorted({r["team"] for r in records})
    print(f"Saved {len(records)} players across {len(teams)} teams to {OUTPUT_FILE}")

    team_profiles = collect_teams(fb)
    with TEAMS_FILE.open("w") as file:
        json.dump(team_profiles, file, indent=2)
    print(f"Saved {len(team_profiles)} team profiles to {TEAMS_FILE}")

    if team_profiles:
        top = team_profiles[0]
        pg = top["per_game"]
        print(f"Sample team — {top['team']} ({top['games']}g): "
              f"{pg['shots_on_target']} SoT, {pg['goals']} goals, "
              f"{pg['goals_allowed']} conceded, {pg['fouls']} fouls per game")


if __name__ == "__main__":
    main()
