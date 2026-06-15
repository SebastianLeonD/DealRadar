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


def eligible_edges(edges: list[dict], provider: str) -> list[dict]:
    """Engine-liked picks the chosen provider actually offers."""
    out = []
    for edge in edges:
        if (edge.get("verdict") or "").upper() not in ENGINE_LIKES:
            continue
        if provider == "UD" and not edge.get("underdog"):
            continue  # not on Underdog -> can't put it on an Underdog slip
        out.append(edge)
    return out


def rank(edges: list[dict], metric: str) -> list[dict]:
    return sorted(edges, key=lambda e: _metric_value(e, metric), reverse=True)


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
        "team": edge.get("team"),
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

    ranked = rank(eligible_edges(edges, provider), metric)
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

    chosen = legs[:n]  # shortlist was ranked, so these are the strongest agreed legs
    return {
        "provider": provider,
        "metric": metric,
        "requested": n,
        "eligible": len(ranked),
        "considered": len(shortlist),
        "agreed": len(legs),
        "legs": chosen,
        "short": len(chosen) < n,
        "correlations": _correlations(chosen),
    }
