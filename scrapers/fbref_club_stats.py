"""Pull club-season player form from FBref — pre-tournament stats for the AI.

Before a player has any World Cup minutes, the analyst has nothing to reason
from. Their club season (a large, stable sample) fills that gap. Same 5-table
stat set as the World Cup pull (shots, SoT, goals, fouls, fouls-drawn, offsides,
crosses, tackles-won, interceptions, saves, goals-allowed) — used only as AI
context, never to manufacture an edge.

Coverage is the Big-5 European leagues (~42% of a typical WC squad). Add leagues
to CLUB_LEAGUES for more — each is another scrape. soccerdata caches locally.

Run:  .venv/bin/python scrapers/fbref_club_stats.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import soccerdata as sd

from scrapers.fbref_stats import collect_players, with_rates

# Expand for more coverage (e.g. 'NED-Eredivisie' needs a soccerdata custom
# league_dict entry; Big-5 works out of the box).
CLUB_LEAGUES = ["Big 5 European Leagues Combined"]
SEASON = "2025-2026"
OUTPUT_FILE = Path("data/processed/fbref_club_stats.json")


def main():
    by_name: dict[str, dict] = {}

    for league in CLUB_LEAGUES:
        print(f"Fetching FBref {league} {SEASON} (Cloudflare-protected, first run slow)...")
        fb = sd.FBref(leagues=league, seasons=SEASON)
        players = collect_players(fb)
        for record in players.values():
            record = with_rates(record)
            if (record.get("minutes") or 0) <= 0:
                continue
            record["source"] = league
            # If a player shows up in two leagues (transfer/loan), keep the one
            # with more minutes — the better-sampled rate.
            key = record["normalized"]
            existing = by_name.get(key)
            if not existing or (record.get("minutes") or 0) > (existing.get("minutes") or 0):
                by_name[key] = record

    records = sorted(by_name.values(), key=lambda r: r.get("minutes") or 0, reverse=True)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w") as file:
        json.dump(records, file, indent=2)

    print(f"Saved {len(records)} club players to {OUTPUT_FILE}")
    if records:
        top = records[0]
        print(f"Sample — {top['player']} ({top['team']}), {top['minutes']:.0f} min: "
              f"per90 {json.dumps(top['per90'])}")


if __name__ == "__main__":
    main()
