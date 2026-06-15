"""Build a slip: the engine proposes, the AI disposes.

The engine ranks every pick it likes (verdict YES/LEAN) by EV or win%, hands the
top candidates to the AI analyst, and only legs BOTH agree on make the cut. No
padding — if fewer than N legs survive the agree-test, the slip comes back short
with a note rather than stuffed with weak picks. Same-game legs are flagged so a
parlay isn't quietly built on correlated outcomes.

The AI step is injected (`analyze_shortlist`) so this stays pure and testable;
the API layer supplies a parallel, real-Claude implementation.
"""

from __future__ import annotations

from collections import defaultdict

ENGINE_LIKES = {"YES", "LEAN"}
DEFAULT_SHORTLIST_CAP = 12  # most Claude calls one slip will ever make


def _metric_value(edge: dict, metric: str) -> float:
    value = edge.get("ev_percent" if metric == "ev" else "win_prob")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _is_combo(edge: dict) -> bool:
    """Combo props bundle two players (and sometimes two teams), which tangles
    the one-player / two-team lineup rules. We show them on the board but never
    auto-pick them, so a built slip is always a clean, valid lineup."""
    return " + " in (edge.get("player") or "")


def _clean_team(team: str | None) -> str | None:
    """PP doubles the team string ('Uruguay Uruguay', 'IR Iran IR Iran')."""
    if not team:
        return team
    words = team.split()
    half = len(words) // 2
    if half and len(words) % 2 == 0 and words[:half] == words[half:]:
        return " ".join(words[:half])
    return team


def eligible_edges(edges: list[dict], provider: str) -> list[dict]:
    """Engine-liked, single-player picks the chosen provider actually offers."""
    out = []
    for edge in edges:
        if (edge.get("verdict") or "").upper() not in ENGINE_LIKES:
            continue
        if _is_combo(edge):
            continue  # combos can't be auto-built into a valid lineup
        if provider == "UD" and not edge.get("underdog"):
            continue  # not on Underdog -> can't put it on an Underdog slip
        out.append(edge)
    return out


def rank(edges: list[dict], metric: str) -> list[dict]:
    return sorted(edges, key=lambda e: _metric_value(e, metric), reverse=True)


def _dedupe_players(edges: list[dict]) -> list[dict]:
    """One prop per player — keep the best (list is already rank-ordered). PP
    forbids the same player twice in a lineup."""
    seen: set[str] = set()
    out = []
    for edge in edges:
        player = edge.get("player") or ""
        if player in seen:
            continue
        seen.add(player)
        out.append(edge)
    return out


def select_valid_lineup(legs: list[dict], n: int) -> list[dict]:
    """The top N legs that form a legal PrizePicks lineup: unique players (the
    input is already player-deduped) spanning at least two different teams."""
    chosen = legs[:n]
    teams = {leg.get("team") for leg in chosen if leg.get("team")}
    # PP requires >=2 distinct teams. If our top N are all one team, swap the
    # weakest leg for the best available leg from a different team.
    if len(chosen) >= 2 and len(teams) < 2:
        alt = next(
            (leg for leg in legs[n:] if leg.get("team") and leg["team"] not in teams),
            None,
        )
        if alt:
            chosen[-1] = alt
    return chosen


def _ai_side(rec: dict, provider: str) -> str:
    """The AI's call for the line we'd actually bet on this provider."""
    if provider == "UD" and rec.get("underdog_pick"):
        return str(rec["underdog_pick"]).upper()
    return str(rec.get("pick") or "PASS").upper()


def _provider_line(edge: dict, provider: str):
    if provider == "UD" and edge.get("underdog"):
        return edge["underdog"].get("ud_line")
    return edge.get("pp_line")


def _leg(edge: dict, rec: dict, provider: str) -> dict:
    ud = edge.get("underdog") or {}
    return {
        "player": edge.get("player") or edge.get("dk_player_name"),
        "team": _clean_team(edge.get("team")),
        "opponent": edge.get("opponent"),
        "game": edge.get("game"),
        "stat_type": edge.get("stat_type"),
        "side": (edge.get("play") or "").upper(),
        "provider": provider,
        "line": _provider_line(edge, provider),
        "pp_line": edge.get("pp_line"),
        "ud_line": ud.get("ud_line"),
        "win_prob": edge.get("win_prob"),
        "ev_percent": edge.get("ev_percent"),
        "verdict": edge.get("verdict"),
        "edge_type": edge.get("edge_type"),
        "ai": {
            "pick": _ai_side(rec, provider),
            "confidence": rec.get("confidence"),
            "reasoning": rec.get("reasoning"),
            "key_factors": rec.get("key_factors") or [],
        },
    }


def _correlations(legs: list[dict]) -> list[dict]:
    """Legs sharing a game — correlated outcomes for a parlay."""
    by_game: dict[str, list[str]] = defaultdict(list)
    for leg in legs:
        key = leg.get("game")
        if key:
            by_game[key].append(leg["player"])
    return [
        {"game": game, "players": players}
        for game, players in by_game.items()
        if len(players) > 1
    ]


def build_slip(
    edges: list[dict],
    n: int,
    provider: str = "PP",
    metric: str = "ev",
    analyze_shortlist=None,
    shortlist_cap: int = DEFAULT_SHORTLIST_CAP,
) -> dict:
    """Return the best N legs the engine and AI agree on, or fewer with a note."""
    provider = (provider or "PP").upper()
    metric = (metric or "ev").lower()
    n = max(1, int(n))

    # Rank, then one prop per player BEFORE the AI step, so the shortlist spends
    # its Claude calls on distinct players (not three lines of one player).
    ranked = _dedupe_players(rank(eligible_edges(edges, provider), metric))
    shortlist = ranked[:shortlist_cap]

    if analyze_shortlist is None:
        from engine.ai_analyst import analyze_play

        def analyze_shortlist(items):
            out = []
            for edge in items:
                try:
                    out.append(analyze_play(edge, mode="full"))
                except Exception:
                    out.append(None)
            return out

    recs = analyze_shortlist(shortlist) if shortlist else []

    legs = []
    for edge, rec in zip(shortlist, recs):
        if not rec:
            continue
        side = _ai_side(rec, provider)
        if side == "PASS" or side != (edge.get("play") or "").upper():
            continue  # AI disagrees with the engine -> out
        legs.append(_leg(edge, rec, provider))

    # The strongest agreed legs that form a legal lineup (unique players, >=2 teams).
    chosen = select_valid_lineup(legs, n)
    teams = {leg.get("team") for leg in chosen if leg.get("team")}
    valid = len(chosen) >= 2 and len(teams) >= 2
    return {
        "provider": provider,
        "metric": metric,
        "requested": n,
        "eligible": len(ranked),
        "considered": len(shortlist),
        "agreed": len(legs),
        "legs": chosen,
        "short": len(chosen) < n,
        "team_count": len(teams),
        "valid": valid,
        "correlations": _correlations(chosen),
    }
