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
    print(f"Teams with data: {', '.join(teams)}")
    if records:
        top = records[0]
        print(f"Sample — {top['player']} ({top['team']}), {top['minutes']:.0f} min: "
              f"per90 {json.dumps(top['per90'])}")


if __name__ == "__main__":
    main()
