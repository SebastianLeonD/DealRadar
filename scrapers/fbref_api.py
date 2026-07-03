"""FBref soccer data connector — settlement + cold-start rate priors.

FBref lost its Opta advanced-stats feed in Jan 2026 (xG / progressive passes /
shot-creating actions are gone), but the BASIC per-player match data we
actually trade on — minutes, shots, shots on target, goals, assists, goalie
saves — is still published and updated live through the World Cup. This
connector pulls that for two jobs:

  1. SETTLEMENT — grade our soccer props (player_shots, player_shots_on_target,
     player_goals, player_assists, player_goalie_saves) and supply minutes for
     the participation/void rule. This is an identified-path use (grading
     reality), so it is firewall-safe.

  2. COLD-START RATE PRIORS — for a slate player we have no history on, backfill
     their last-N appearances so engine/rate_prior.py can seed a shots-per-90 /
     SoT-per-90 prior for the (asserted, gated) soccer model.

Access reality: FBref has NO API and a hard rate limit (~10 requests/min; abuse
jails the IP for up to a day). The `soccerdata` library wraps it politely and
caches locally; we go through it. The actual network call is injected
(`fetch_fn`) so every transform here is unit-testable without the library or a
live FBref (which this environment's outbound proxy blocks anyway).
"""

from __future__ import annotations

import re

# soccerdata's league id for the men's World Cup (sd.FBref.available_leagues()).
FBREF_WORLD_CUP_LEAGUE = "INT-World Cup"

# Be a good citizen well under the 10-req/min ceiling; soccerdata's local cache
# does most of the work, this is the floor between uncached page loads.
FBREF_MIN_REQUEST_GAP_SECONDS = 4.0

# FBref column name (lowercased) -> our canonical stat_type. Aliases cover the
# 'summary', 'shooting' and 'keepers' tables and the occasional header variant.
# soccerdata match tables carry a table-group prefix once flattened
# ('performance_sh', 'shot stopping_saves'); _canonical_stat() strips it.
_STAT_ALIASES: dict[str, str] = {
    "sh": "player_shots",
    "shots": "player_shots",
    "sot": "player_shots_on_target",
    "shots_on_target": "player_shots_on_target",
    "gls": "player_goals",
    "goals": "player_goals",
    "ast": "player_assists",
    "assists": "player_assists",
    "saves": "player_goalie_saves",
    "gk_saves": "player_goalie_saves",
    "tklw": "player_tackles",
    "crs": "player_crosses",
}
_CANONICAL_STAT_VALUES = set(_STAT_ALIASES.values())
_MINUTES_ALIASES = ("min", "minutes", "mp")
_PLAYER_ALIASES = ("player", "name")
_TEAM_ALIASES = ("team", "squad")
_OPP_ALIASES = ("opponent", "opp")
_DATE_ALIASES = ("date", "game_date")

# soccerdata's `game` index level: '2026-06-11 Korea Republic-Czechia'.
_GAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(.+)$")


def _canonical_stat(key: str) -> str | None:
    """Map a flattened FBref column to a canonical stat, tolerating the table
    prefix soccerdata's MultiIndex flatten leaves ('performance_sh' -> 'sh')."""
    if key in _STAT_ALIASES:
        return _STAT_ALIASES[key]
    for candidate in (key.split("_", 1)[-1], key.rsplit("_", 1)[-1]):
        if candidate in _STAT_ALIASES:
            return _STAT_ALIASES[candidate]
    return None


def _game_parts(game, team) -> tuple[str | None, str | None]:
    """(date, opponent) recovered from a soccerdata game string given the
    player's own team. Returns (None, None) when the format doesn't match."""
    if not isinstance(game, str):
        return None, None
    match = _GAME_RE.match(game.strip())
    if not match:
        return None, None
    date, fixture = match.groups()
    opponent = None
    if team:
        t = str(team)
        if fixture.startswith(t + "-"):
            opponent = fixture[len(t) + 1:]
        elif fixture.endswith("-" + t):
            opponent = fixture[: -(len(t) + 1)]
    return date, (opponent or None)

CANONICAL_SOCCER_STATS = (
    "player_shots",
    "player_shots_on_target",
    "player_goals",
    "player_assists",
    "player_goalie_saves",
)


def _first(row: dict, keys) -> object:
    """Case-insensitive lookup of the first present alias in a flat row dict."""
    lowered = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        if k in lowered and lowered[k] not in (None, ""):
            return lowered[k]
    return None


def _to_float(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN


def normalize_player_match_rows(raw_rows: list[dict]) -> list[dict]:
    """Flatten FBref/soccerdata player-match rows into our internal records.

    `raw_rows` are already-flattened dicts (the soccerdata adapter joins the
    DataFrame's MultiIndex columns to simple keys). Rows with no player or no
    minutes are dropped (unused subs). Returns records of the form:
        {player, team, opponent, date, minutes,
         stats: {canonical_stat: value, ...}}
    """
    records: list[dict] = []
    for row in raw_rows:
        player = _first(row, _PLAYER_ALIASES)
        minutes = _to_float(_first(row, _MINUTES_ALIASES))
        if not player or minutes is None:
            continue  # DNP / unused sub -> no usable row
        stats: dict[str, float] = {}
        lowered = {str(k).lower(): v for k, v in row.items()}
        for col, value in lowered.items():
            canon = _canonical_stat(col)
            if canon is None:
                continue
            f = _to_float(value)
            if f is not None:
                stats[canon] = f
        # Already-normalized cached records carry a nested stats dict; pass it
        # through so re-normalizing the JSON cache is lossless.
        nested = row.get("stats")
        if isinstance(nested, dict):
            for key, value in nested.items():
                if key in _CANONICAL_STAT_VALUES:
                    f = _to_float(value)
                    if f is not None:
                        stats[key] = f
        team = _first(row, _TEAM_ALIASES) or None
        opponent = _first(row, _OPP_ALIASES) or None
        date = _first(row, _DATE_ALIASES) or None
        if date is None or opponent is None:
            # soccerdata match frames bury date/opponent in the 'game' level.
            game_date, game_opp = _game_parts(lowered.get("game"), team)
            date = date or game_date
            opponent = opponent or game_opp
        records.append({
            "player": str(player),
            "team": team,
            "opponent": opponent,
            "date": date,
            "minutes": minutes,
            "stats": stats,
        })
    return records


def last_n_player_logs(
    records: list[dict],
    players: list[str] | None = None,
    n: int = 8,
) -> dict[str, list[dict]]:
    """Most-recent-n appearances per player (newest first), for cold-start priors.

    `records` are normalized match records (from normalize_player_match_rows).
    `players` limits the result to a slate's players; None returns all. Records
    are ordered by date descending (ISO date strings sort correctly). When dates
    are missing, ties break on input position descending — i.e. later input rows
    are treated as more recent, so a chronologically-ordered input still yields
    the most-recent-n.
    """
    wanted = {p for p in players} if players is not None else None
    by_player: dict[str, list[dict]] = {}
    for idx, rec in enumerate(records):
        if wanted is not None and rec["player"] not in wanted:
            continue
        by_player.setdefault(rec["player"], []).append((idx, rec))

    out: dict[str, list[dict]] = {}
    for player, indexed in by_player.items():
        # Sort by date desc; missing dates fall back to original order (stable).
        indexed.sort(key=lambda t: (t[1]["date"] or "", t[0]), reverse=True)
        out[player] = [rec for _, rec in indexed[:n]]
    return out


# ---------------------------------------------------------------------------
# Live fetch (thin lazy adapter — not exercised in tests / blocked by proxy)
# ---------------------------------------------------------------------------
def _flatten_soccerdata_df(df) -> list[dict]:  # pragma: no cover - needs pandas
    """Flatten a soccerdata DataFrame (often MultiIndex columns + index) to a
    list of plain dicts with simple, lowercased keys."""
    flat = df.reset_index()
    flat.columns = [
        "_".join(str(p) for p in col if str(p) != "").strip("_").lower()
        if isinstance(col, tuple) else str(col).lower()
        for col in flat.columns
    ]
    return flat.to_dict("records")


def fetch_player_match_stats(
    season: str,
    *,
    fetch_fn=None,
    league: str = FBREF_WORLD_CUP_LEAGUE,
    stat_type: str = "summary",
    no_cache: bool = False,
) -> list[dict]:
    """Normalized player-match records for a competition/season.

    `fetch_fn(season, league, stat_type) -> list[dict]` is injected in tests and
    by callers that want to control I/O. When omitted, a soccerdata FBref reader
    is built lazily (live path); soccerdata's cache provides the rate-limit
    safety, and no_cache forces a refresh of the current matchday.
    """
    if fetch_fn is not None:
        return normalize_player_match_rows(fetch_fn(season, league, stat_type))
    return normalize_player_match_rows(
        _live_fetch(season, league, stat_type, no_cache)
    )


def _live_fetch(season, league, stat_type, no_cache):  # pragma: no cover - live
    import soccerdata as sd

    reader = sd.FBref(leagues=league, seasons=season, no_cache=no_cache)
    df = reader.read_player_match_stats(stat_type=stat_type)
    return _flatten_soccerdata_df(df)
