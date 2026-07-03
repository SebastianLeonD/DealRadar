"""Pull Pinnacle's Anytime Goalscorer board for the World Cup (free guest API).

Pinnacle's arcadia guest API is open JSON — a static guest key, no auth, no
credits — so this fetches directly, the same way underdog_api.py hits
Underdog. Two requests cover the whole league: one matchups call (players,
teams, start times) and one markets call (every price). Records are staged in
the DK sharp shape so they ingest through the same loader and join consensus
beside DraftKings/FanDuel at the identical stat_type/line.

Anytime Goalscorer is a yes-only market (no "No" side, and field-normalising
is wrong because several players can score in one match), so each price is
de-vigged one-sided with the scorer-market margin from engine/sports.py —
the same haircut DK's anytime-scorer prices get — and mapped to the same
market key: over 0.5 player_goals.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.probability import devig_one_sided
from engine.sports import SPORTS

BASE_URL = "https://guest.api.arcadia.pinnacle.com/0.1"
LEAGUE_ID = 2686  # FIFA World Cup
GUEST_API_KEY = "CmX2KcMrXuFmNg6YFbmTxE0y9CIrOi0R"  # public guest key, not a secret
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
# Sharp-shaped board (de-vigged true probabilities), same format as
# draftkings_data.json — Pinnacle enters consensus as another sharp book.
SHARP_FILE = Path("data/processed/pinnacle_sharp.json")

AGS_CONFIG = SPORTS["world_cup"]["binary_markets"]["player_goal_scorer_anytime"]


def _fetch(path: str) -> list:
    response = requests.get(
        f"{BASE_URL}{path}",
        headers={
            "X-API-Key": GUEST_API_KEY,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _is_anytime_goalscorer(matchup: dict) -> bool:
    special = matchup.get("special") or {}
    return (
        matchup.get("type") == "special"
        and special.get("category") == "Player Props"
        and special.get("description") == "Anytime Goalscorer"
    )


def _game_label(parent: dict) -> str:
    """DK-style 'Away @ Home' from the parent event's participants."""
    sides = {p.get("alignment"): p.get("name") for p in parent.get("participants", [])}
    return f"{sides.get('away', '?')} @ {sides.get('home', '?')}"


def _started(start_time: str | None, now: datetime) -> bool:
    if not start_time:
        return True  # no kickoff time — don't stage it
    try:
        kickoff = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    except ValueError:
        return True
    return kickoff <= now


def build_sharp_board(matchups: list[dict], markets: list[dict],
                      now: datetime | None = None) -> list[dict]:
    """De-vig each future match's Anytime Goalscorer prices into sharp records.

    Joins market.matchupId == special.id (the special's own id, not the
    parent's), then prices[].participantId == special.participants[].id.
    """
    now = now or datetime.now(timezone.utc)
    prices_by_matchup = {
        m["matchupId"]: m.get("prices", [])
        for m in markets
        if m.get("type") == "moneyline" and m.get("key") == "s;0;m"
    }

    records = []
    for matchup in matchups:
        if not _is_anytime_goalscorer(matchup):
            continue
        parent = matchup.get("parent") or {}
        start_time = parent.get("startTime")
        if _started(start_time, now):
            continue

        players = {p["id"]: p.get("name") for p in matchup.get("participants", [])}
        game = _game_label(parent)
        for entry in prices_by_matchup.get(matchup["id"], []):
            name = players.get(entry.get("participantId"))
            price = entry.get("price")
            if not name or price is None:
                continue
            true_over = devig_one_sided(float(price), AGS_CONFIG["margin"])
            records.append({
                "Player": name,
                "Game": game,
                "Stat": AGS_CONFIG["stat"],
                "Line": 0.5,
                "Bookmaker": "pinnacle",
                "Commence_Time": start_time,
                "True_Over_Prob": round(true_over * 100, 2),
                "True_Under_Prob": round((1 - true_over) * 100, 2),
                "Price_Over": price,
                "Price_Under": None,
                "Devig_Method": "one_sided",
            })

    return records


def main():
    print("Fetching Pinnacle World Cup matchups and prices...")
    try:
        matchups = _fetch(f"/leagues/{LEAGUE_ID}/matchups")
        markets = _fetch(f"/leagues/{LEAGUE_ID}/markets/straight")
    except requests.RequestException as error:
        # Leave any previous staging file untouched rather than clobbering
        # good data with an empty board.
        print(f"Pinnacle fetch failed, keeping stale file if any: {error}")
        sys.exit(1)

    records = build_sharp_board(matchups, markets)

    SHARP_FILE.parent.mkdir(parents=True, exist_ok=True)
    # fetched_at rides in the payload so ingest stamps captured_at with the
    # real fetch time — re-ingesting a stale file must not make it look fresh.
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with SHARP_FILE.open("w") as file:
        json.dump({"fetch_complete": True, "fetched_at": fetched_at,
                   "records": records}, file, indent=4, ensure_ascii=False)

    games = {r["Game"] for r in records}
    print(f"Saved {len(records)} de-vigged anytime-goalscorer lines "
          f"across {len(games)} matches to {SHARP_FILE}")


if __name__ == "__main__":
    main()
