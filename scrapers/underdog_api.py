"""Pull Underdog Fantasy's pick'em board for the active soccer slate.

Unlike PrizePicks (bot-walled, hence the manual paste) Underdog's lines endpoint
is open JSON — no key, no auth — so this fetches it directly, the same way
draftkings_api.py hits The-Odds-API. The board is filtered to FIFA player props
and normalised to the engine's stat keys so it can be line-shopped against the
PrizePicks board (see engine/line_shop.py).

Underdog joins:
    over_under_lines[].over_under.appearance_stat -> appearance_id + machine stat
    appearances[]  -> player_id, team_id, match_id
    players[]      -> name, country, position, image, sport_id
    games[]        -> "Home vs Away" title, home/away team ids, scheduled_at

Only `balanced` line types are kept (boosts/specials carry custom multipliers
that break flat pick'em comparisons), and only full-match / 1H durations the
engine can represent.
"""

import json
import sys
import unicodedata
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.probability import devig_power

LINES_URL = "https://api.underdogfantasy.com/beta/v6/over_under_lines"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
OUTPUT_FILE = Path("data/processed/underdog_data.json")
# Sharp-shaped board (de-vigged true probabilities) the matcher prices against,
# the same format as draftkings_data.json — Underdog enters as another book.
SHARP_FILE = Path("data/processed/underdog_sharp.json")

SPORT_ID = "FIFA"

# Underdog machine-stat base (after the period_ prefix) -> engine stat key.
UD_STAT_MAP = {
    "shots_attempted": "player_shots",
    "shots_on_target": "player_shots_on_target",
    "goals": "player_goals",
    "assists": "player_assists",
    "saves": "player_goalie_saves",
    "goals_against": "player_goals_allowed",
    "tackles": "player_tackles",
}

# Unpriced stats worth line-shopping by label. Value must equal PrizePicks'
# raw stat_type string so the two boards join (see engine/line_shop.py).
UD_LABEL_MAP = {
    "passes": "Passes Attempted",
    "goals_assists": "Goal + Assist",
}


def _normalize(name: str) -> str:
    stripped = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def resolve_stat(machine_stat: str):
    """(join_key, label, mapped) for a UD machine stat, or None to drop it.

    join_key is the engine stat key for priced stats (carrying a _1h suffix for
    first-half props) or 'label:<name>' for unpriced ones — the same key the
    PrizePicks board computes, so the boards match on it.
    """
    duration = None
    if machine_stat.startswith("period_1_2_"):
        base = machine_stat[len("period_1_2_"):]
    elif machine_stat.startswith("period_1_"):
        base, duration = machine_stat[len("period_1_"):], "1h"
    elif machine_stat.startswith("period_2_"):
        return None  # 2nd-half only — nothing on the PP board to shop against
    else:
        base = machine_stat

    suffix = "_1h" if duration == "1h" else ""
    if base in UD_STAT_MAP:
        return UD_STAT_MAP[base] + suffix, base.replace("_", " ").title(), True
    if base in UD_LABEL_MAP:
        label = UD_LABEL_MAP[base]
        return f"label:{label}{suffix}", label, False
    return None


def fetch_board() -> dict:
    response = requests.get(
        LINES_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _full_name(player: dict) -> str:
    parts = [player.get("first_name"), player.get("last_name")]
    return " ".join(p for p in parts if p).strip()


def _matchup(game: dict, team_id: str) -> tuple[str | None, str | None]:
    """The player's team and opponent from a game's 'Home vs Away' title."""
    title = game.get("full_team_names_title") or game.get("short_title") or ""
    sides = [s.strip() for s in title.split(" vs ")]
    if len(sides) != 2:
        return None, None
    home, away = sides
    if team_id == game.get("home_team_id"):
        return home, away
    if team_id == game.get("away_team_id"):
        return away, home
    return None, None


def _option_prices(options: list[dict]) -> dict:
    """Higher/lower american price + payout multiplier, keyed by side."""
    prices = {}
    for option in options:
        side = "higher" if option.get("choice") == "higher" else "lower"
        try:
            multiplier = float(option.get("payout_multiplier"))
        except (TypeError, ValueError):
            multiplier = None
        prices[f"{side}_price"] = option.get("american_price")
        prices[f"{side}_multiplier"] = multiplier
    return prices


def build_board(raw: dict) -> list[dict]:
    players = {p["id"]: p for p in raw.get("players", [])}
    appearances = {a["id"]: a for a in raw.get("appearances", [])}
    games = {g["id"]: g for g in raw.get("games", [])}

    board, skipped = [], 0
    for line in raw.get("over_under_lines", []):
        if line.get("line_type") != "balanced":
            continue
        over_under = line.get("over_under") or {}
        if over_under.get("boost") is not None:
            continue
        if over_under.get("category") != "player_prop":
            continue

        appearance_stat = over_under.get("appearance_stat") or {}
        appearance = appearances.get(appearance_stat.get("appearance_id"))
        if not appearance:
            continue
        player = players.get(appearance.get("player_id"))
        if not player or player.get("sport_id") != SPORT_ID:
            continue

        resolved = resolve_stat(appearance_stat.get("stat", ""))
        if not resolved:
            skipped += 1
            continue
        join_key, stat_label, mapped = resolved

        try:
            line_value = float(line.get("stat_value"))
        except (TypeError, ValueError):
            continue

        game = games.get(appearance.get("match_id")) or {}
        team, opponent = _matchup(game, appearance.get("team_id"))

        name = _full_name(player)
        board.append({
            "player": name,
            "normalized": _normalize(name),
            "team": team,
            "opponent": opponent,
            "position": player.get("position_display_name"),
            "image_url": player.get("image_url"),
            "join_key": join_key,
            "stat_label": stat_label,
            "mapped": mapped,
            "line": line_value,
            "commence_time": game.get("scheduled_at"),
            **_option_prices(line.get("options", [])),
        })

    return board, skipped


def _american(value) -> float | None:
    try:
        return float(str(value).replace("+", ""))
    except (TypeError, ValueError):
        return None


def build_sharp_board(board: list[dict]) -> list[dict]:
    """De-vig each mapped prop's two-sided price into a sharp-shaped record.

    Only props that carry an engine stat key (mapped) and both american prices
    can be priced; label-only stats (passes, goals+assists) have no model."""
    records = []
    for prop in board:
        if not prop.get("mapped"):
            continue
        higher, lower = _american(prop.get("higher_price")), _american(prop.get("lower_price"))
        if higher is None or lower is None:
            continue
        true_over, true_under = devig_power(higher, lower)
        records.append({
            "Player": prop["player"],
            "Game": f"{prop.get('opponent') or '?'} @ {prop.get('team') or '?'}",
            "Stat": prop["join_key"],
            "Line": prop["line"],
            "Bookmaker": "underdog",
            "Commence_Time": prop.get("commence_time"),
            "True_Over_Prob": round(true_over * 100, 2),
            "True_Under_Prob": round(true_under * 100, 2),
        })
    return records


def main():
    print("Fetching Underdog over/under lines...")
    raw = fetch_board()
    board, skipped = build_board(raw)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open("w") as file:
        json.dump(board, file, indent=4, ensure_ascii=False)

    sharp = build_sharp_board(board)
    with SHARP_FILE.open("w") as file:
        json.dump(sharp, file, indent=4, ensure_ascii=False)

    priced = sum(1 for prop in board if prop["mapped"])
    print(f"Kept {len(board)} FIFA props ({priced} priced, "
          f"{len(board) - priced} label-only); {skipped} unsupported stats skipped.")
    print(f"Saved Underdog board to {OUTPUT_FILE}")
    print(f"Saved {len(sharp)} de-vigged lines (for pricing) to {SHARP_FILE}")


if __name__ == "__main__":
    main()
