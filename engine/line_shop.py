"""Line-shop the PrizePicks board against Underdog.

Both apps are pick'em (Higher/Lower on a player stat). When they post different
lines on the SAME player + stat, the gap is free value: bet OVER on whichever
app has the lower line, UNDER on whichever has the higher line. This module
matches the two boards on a shared join key and reports that gap.

The join key carries the stat AND the duration (e.g. player_shots vs
player_shots_1h), so a first-half line never matches a full-match one — the
mismatch that would otherwise fabricate a phantom edge.

Honesty note: when the lines are EQUAL we expose Underdog's payout multiplier as
context but make no EV claim — PrizePicks posts no per-leg price (its payout
depends on entry size), so a head-to-head EV between the two would be invented.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from engine.name_matcher import match_player_name

UNDERDOG_FILE = Path("data/processed/underdog_data.json")


def normalize(name: str) -> str:
    """Accent-insensitive name key — must match scrapers/underdog_api.py."""
    stripped = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return " ".join(stripped.lower().split())


def load_underdog(path: Path = UNDERDOG_FILE) -> list[dict]:
    if not path.exists():
        return []
    with path.open() as file:
        return json.load(file)


def pp_join_key(mapped_stat: str | None, raw_stat_type: str) -> str:
    """The key a PrizePicks prop joins on — engine key, else 'label:<raw>'."""
    return mapped_stat if mapped_stat else f"label:{raw_stat_type}"


def build_index(underdog: list[dict]) -> dict[str, list[dict]]:
    """Group Underdog props by join key for O(1) per-prop lookup."""
    index: dict[str, list[dict]] = {}
    for prop in underdog:
        index.setdefault(prop["join_key"], []).append(prop)
    return index


def _find(name: str, normalized: str, bucket: list[dict]) -> dict | None:
    if not bucket:
        return None
    hit = next((p for p in bucket if p["normalized"] == normalized), None)
    if hit:
        return hit
    matched, _ = match_player_name(name, [p["player"] for p in bucket])
    if not matched:
        return None
    return next((p for p in bucket if p["player"] == matched), None)


def compare(pp_line: float, ud: dict) -> dict:
    """The PP-vs-UD comparison for one matched prop.

    over_app/under_app name the better app per side: the lower line is easier to
    clear on the OVER, the higher line easier to stay under. 'EVEN' when equal.
    """
    ud_line = ud["line"]
    delta = round(ud_line - pp_line, 2)
    if delta < 0:           # Underdog's line is lower
        over_app, under_app = "UD", "PP"
    elif delta > 0:         # Underdog's line is higher
        over_app, under_app = "PP", "UD"
    else:
        over_app = under_app = "EVEN"

    return {
        "ud_line": ud_line,
        "ud_delta": delta,
        "over_app": over_app,
        "under_app": under_app,
        "ud_higher_price": ud.get("higher_price"),
        "ud_lower_price": ud.get("lower_price"),
        "ud_higher_multiplier": ud.get("higher_multiplier"),
        "ud_lower_multiplier": ud.get("lower_multiplier"),
        "ud_matched_name": ud["player"],
    }


def match_prop(
    player: str,
    normalized: str,
    join_key: str,
    pp_line: float,
    index: dict[str, list[dict]],
) -> dict | None:
    """Find Underdog's line for one PP prop and compare. None if no match."""
    ud = _find(player, normalized, index.get(join_key, []))
    if ud is None:
        return None
    return compare(pp_line, ud)


def recommend_for_play(play: str, pp_line: float, ud: dict) -> dict:
    """Compare for a prop the engine has already picked a SIDE on.

    best_app is the app to bet the engine's side with (the app whose line is
    softer for that direction); bet_on_underdog is the actionable case.
    """
    cmp = compare(pp_line, ud)
    side = (play or "").upper()
    if side == "OVER":
        best, price, mult = cmp["over_app"], cmp["ud_higher_price"], cmp["ud_higher_multiplier"]
    elif side == "UNDER":
        best, price, mult = cmp["under_app"], cmp["ud_lower_price"], cmp["ud_lower_multiplier"]
    else:
        best, price, mult = "EVEN", None, None
    return {
        "ud_line": cmp["ud_line"],
        "ud_delta": cmp["ud_delta"],
        "best_app": best,
        "bet_on_underdog": best == "UD",
        "play_price": price,
        "play_multiplier": mult,
        "ud_matched_name": cmp["ud_matched_name"],
    }


def match_edge(
    play: str,
    player: str,
    normalized: str,
    join_key: str,
    pp_line: float,
    index: dict[str, list[dict]],
) -> dict | None:
    """Underdog recommendation for one engine edge. None if no UD match."""
    ud = _find(player, normalized, index.get(join_key, []))
    if ud is None:
        return None
    return recommend_for_play(play, pp_line, ud)
