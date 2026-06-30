"""Shadow prediction: the ASSERTED FBref Poisson model logged beside the market.

The market path (multi-book de-vig consensus) and this model path (FBref minutes-
weighted rate prior -> Poisson) are two independent estimates of the same
P(over). This module computes the model number for a flagged edge and folds it to
the bet side so it sits next to `win_prob` in the edges table.

It FLAGS NOTHING. Per the council Phase-2 firewall, an asserted number may not
move a verdict until engine/calibration.py proves it out-Briers the market
baseline out-of-sample. Logging it now is the prerequisite: the 158 settled games
are useless to the model until each carries the prediction the model WOULD have
made. See engine/soccer_model.py for the firewall note.

FBref data is best-effort: if neither a local cache nor a live soccerdata fetch
is available, the loader returns {} and every model_* field stays NULL. A missing
model number must NEVER drop a market edge.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.soccer_model import model_prediction
from scrapers.fbref_api import (
    CANONICAL_SOCCER_STATS,
    fetch_player_match_stats,
    last_n_player_logs,
    normalize_player_match_rows,
)

# Default cache of normalized FBref match records (a JSON list of the dicts
# normalize_player_match_rows produces). Drop one here to run the model without
# soccerdata / a live FBref reachable.
DEFAULT_LOG_CACHE = Path("data/processed/fbref_logs.json")

NULL_FIELDS = {
    "model_p": None,
    "model_p_side": None,
    "model_lambda": None,
    "model_credibility": None,
    "model_n_matches": None,
    "model_source": None,
}


def model_eligible(stat_type: str, *, derived: bool) -> bool:
    """Only base (non-derived) soccer count stats have an FBref-seeded model.

    1H / combo / duration-scaled stats price off the full-match ladder on the
    market side and have no direct FBref column, so they stay shadow-NULL.
    """
    return (not derived) and stat_type in CANONICAL_SOCCER_STATS


def model_fields(logs: list[dict], stat_type: str, line: float, play: str) -> dict:
    """model_* fields for one prop from a player's recent logs.

    Folds the model's P(over) to the bet side so model_p_side is directly
    comparable to the edge's win_prob. Returns NULL_FIELDS if logs are empty.
    """
    if not logs:
        return dict(NULL_FIELDS)
    pred = model_prediction(logs, stat_type, line)
    p_over = pred["p_over"]
    p_side = p_over if play == "OVER" else round(1.0 - p_over, 4)
    return {
        "model_p": p_over,
        "model_p_side": p_side,
        "model_lambda": pred["lambda"],
        "model_credibility": pred["credibility"],
        "model_n_matches": pred["n_matches"],
        "model_source": pred["sigma_source"],
    }


def load_fbref_logs(
    players: list[str] | None = None,
    *,
    season: str = "2026",
    n: int = 8,
    cache_path: Path = DEFAULT_LOG_CACHE,
) -> dict[str, list[dict]]:
    """{player -> last-n logs}, best-effort. Cache first, then live soccerdata.

    Never raises: any failure (no cache, soccerdata missing, FBref blocked,
    empty feed) returns {} so the matcher logs model_* = NULL and moves on.
    """
    records: list[dict] = []
    if cache_path.exists():
        try:
            records = normalize_player_match_rows(json.loads(cache_path.read_text()))
        except Exception as error:  # noqa: BLE001 - shadow path must not break
            print(f"  shadow model: cache unreadable ({error}); trying live FBref")

    if not records:
        try:
            records = fetch_player_match_stats(season)
            if records:  # persist for next run so we hit FBref at most once
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(records))
        except Exception as error:  # noqa: BLE001 - soccerdata absent / blocked
            print(f"  shadow model: FBref logs unavailable ({error}); model_p=NULL this run")
            return {}

    if not records:
        print("  shadow model: no FBref logs found; model_p=NULL this run")
        return {}
    return last_n_player_logs(records, players, n=n)


def _demo() -> None:
    """Self-check: a striker averaging ~3 shots/90 over full matches should price
    over 1.5 shots high and over 4.5 low, and folding to UNDER complements OVER."""
    logs = [{"minutes": 90, "stats": {"player_shots": 3}} for _ in range(5)]
    over = model_fields(logs, "player_shots", 1.5, "OVER")
    high = model_fields(logs, "player_shots", 4.5, "OVER")
    assert over["model_source"] == "fbref_poisson_prior"
    assert over["model_p"] > 0.6, over
    assert high["model_p"] < over["model_p"], (high, over)
    under = model_fields(logs, "player_shots", 1.5, "UNDER")
    assert abs(under["model_p_side"] - (1 - over["model_p"])) < 1e-9, under
    # No logs -> all NULL, never an exception.
    assert model_fields([], "player_shots", 1.5, "OVER") == NULL_FIELDS
    # Derived / non-soccer stats are not model-eligible.
    assert model_eligible("player_shots", derived=False)
    assert not model_eligible("player_shots", derived=True)
    assert not model_eligible("player_points", derived=False)
    print("shadow_model self-check passed")


if __name__ == "__main__":
    _demo()
