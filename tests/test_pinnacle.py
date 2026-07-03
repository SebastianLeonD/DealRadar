"""Pinnacle anytime-goalscorer connector (scrapers/pinnacle_api.py).

Canned payloads only — no network. Covers the record shape the DK loader
expects (Bookmaker='pinnacle', player_goals over 0.5, percent-scaled probs),
one-sided de-vig with the scorer margin, started-game exclusion, and the
payoff: a Pinnacle record beside a DK record at the same line earns the
'identified' consensus tag.
"""

import json
from datetime import datetime, timezone

from engine.consensus import line_matched_consensus
from engine.probability import devig_one_sided
from scrapers.pinnacle_api import AGS_CONFIG, build_sharp_board
from storage.db_manager import get_sharp_ladders, ingest_draftkings, init_db

NOW = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)


def _special(matchup_id=1632190570, start="2026-07-03T22:00:00Z"):
    return {
        "id": matchup_id,
        "type": "special",
        "special": {"category": "Player Props", "description": "Anytime Goalscorer"},
        "parentId": 1632165855,
        "parent": {
            "id": 1632165855,
            "participants": [
                {"alignment": "home", "name": "Argentina"},
                {"alignment": "away", "name": "Cape Verde"},
            ],
            "startTime": start,
        },
        "participants": [
            {"id": 1, "name": "Lionel Messi", "alignment": "neutral"},
            {"id": 2, "name": "Lautaro Martinez", "alignment": "neutral"},
        ],
    }


def _market(matchup_id=1632190570):
    return {
        "matchupId": matchup_id,
        "key": "s;0;m",
        "type": "moneyline",
        "period": 0,
        "prices": [
            {"participantId": 1, "price": -200},
            {"participantId": 2, "price": 106},
        ],
    }


def test_record_shape_and_devig():
    records = build_sharp_board([_special()], [_market()], now=NOW)
    assert len(records) == 2

    messi = next(r for r in records if r["Player"] == "Lionel Messi")
    assert messi["Bookmaker"] == "pinnacle"
    assert messi["Stat"] == "player_goals"
    assert messi["Line"] == 0.5
    assert messi["Game"] == "Cape Verde @ Argentina"
    assert messi["Commence_Time"] == "2026-07-03T22:00:00Z"
    assert messi["Price_Over"] == -200 and messi["Price_Under"] is None

    expected = devig_one_sided(-200.0, AGS_CONFIG["margin"])
    assert messi["True_Over_Prob"] == round(expected * 100, 2)
    assert abs(messi["True_Over_Prob"] + messi["True_Under_Prob"] - 100) < 0.02
    # Percent scale, plausible favourite probability.
    assert 50 < messi["True_Over_Prob"] < 70


def test_started_and_untimed_games_are_excluded():
    started = _special(matchup_id=99, start="2026-07-02T10:00:00Z")
    untimed = _special(matchup_id=98, start=None)
    records = build_sharp_board(
        [started, untimed, _special()],
        [_market(99), _market(98), _market()],
        now=NOW,
    )
    assert {r["Game"] for r in records} == {"Cape Verde @ Argentina"}
    assert len(records) == 2


def test_non_ags_specials_and_unjoined_markets_are_ignored():
    other = _special(matchup_id=77)
    other["special"]["description"] = "First Goalscorer"
    records = build_sharp_board([other, _special()], [_market(77), _market(12345)], now=NOW)
    assert records == []  # AGS special has no market; FG special is filtered


def test_pinnacle_plus_dk_earn_identified_consensus(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)

    records = build_sharp_board([_special()], [_market()], now=NOW)
    staging = tmp_path / "pinnacle_sharp.json"
    staging.write_text(json.dumps({"fetch_complete": True, "records": records}))
    ingest_draftkings(staging, db_path=db)

    dk = tmp_path / "dk.json"
    dk.write_text(json.dumps([{
        "Player": "Lionel Messi", "Line": 0.5, "Stat": "player_goals",
        "Bookmaker": "draftkings", "True_Over_Prob": 60.0, "True_Under_Prob": 40.0,
        "Game": "Cape Verde @ Argentina", "Commence_Time": "2026-07-03T22:00:00Z",
    }]))
    ingest_draftkings(dk, db_path=db)

    ladders = get_sharp_ladders("player_goals", db_path=db)["Lionel Messi"]
    book_probs = {
        book: p_over
        for book, data in ladders.items()
        for line, p_over in data["points"]
        if abs(line - 0.5) < 1e-9
    }
    c = line_matched_consensus(book_probs)
    assert c["consensus_n"] == 2
    assert c["consensus_tag"] == "identified"
    assert set(c["consensus_book_set"]) == {"draftkings", "pinnacle"}


def test_payload_fetched_at_becomes_captured_at(tmp_path):
    """A stale staging file re-ingested later must keep its fetch-time stamp
    so the matcher's cross-book staleness guard can drop it."""
    db = tmp_path / "t.db"
    init_db(db)

    records = build_sharp_board([_special()], [_market()], now=NOW)
    staging = tmp_path / "pinnacle_sharp.json"
    staging.write_text(json.dumps({
        "fetch_complete": True,
        "fetched_at": "2026-06-30T08:00:00+00:00",
        "records": records,
    }))
    ingest_draftkings(staging, db_path=db)

    ladders = get_sharp_ladders("player_goals", db_path=db)
    entry = ladders["Lionel Messi"]["pinnacle"]
    assert entry["captured_at"] == "2026-06-30T08:00:00+00:00"


def test_scraper_stamps_fetched_at(tmp_path, monkeypatch):
    import scrapers.pinnacle_api as pin

    monkeypatch.setattr(pin, "_fetch", lambda path: [])
    monkeypatch.setattr(pin, "SHARP_FILE", tmp_path / "pinnacle_sharp.json")
    pin.main()

    payload = json.loads((tmp_path / "pinnacle_sharp.json").read_text())
    assert payload["fetch_complete"] is True
    # Parseable, tz-aware ISO timestamp of roughly now.
    stamped = datetime.fromisoformat(payload["fetched_at"])
    assert abs((datetime.now(timezone.utc) - stamped).total_seconds()) < 60


def test_ladders_merge_cross_book_name_variants(tmp_path):
    """Pinnacle spellings ('Anis Hadj-Moussa', 'Riyhad Mahrez') must join the
    DK ladder key instead of forking into pinnacle-only entries."""
    db = tmp_path / "t.db"
    init_db(db)

    dk = tmp_path / "dk.json"
    dk.write_text(json.dumps([
        {"Player": "Anis Hadj Moussa", "Line": 0.5, "Stat": "player_goals",
         "Bookmaker": "draftkings", "True_Over_Prob": 30.0, "True_Under_Prob": 70.0},
        {"Player": "Riyad Mahrez", "Line": 0.5, "Stat": "player_goals",
         "Bookmaker": "draftkings", "True_Over_Prob": 40.0, "True_Under_Prob": 60.0},
    ]))
    ingest_draftkings(dk, db_path=db)

    pin = tmp_path / "pin.json"
    pin.write_text(json.dumps([
        {"Player": "Anis Hadj-Moussa", "Line": 0.5, "Stat": "player_goals",
         "Bookmaker": "pinnacle", "True_Over_Prob": 31.0, "True_Under_Prob": 69.0},
        {"Player": "Riyhad Mahrez", "Line": 0.5, "Stat": "player_goals",
         "Bookmaker": "pinnacle", "True_Over_Prob": 41.0, "True_Under_Prob": 59.0},
    ]))
    ingest_draftkings(pin, db_path=db)

    ladders = get_sharp_ladders("player_goals", db_path=db)
    assert len(ladders) == 2  # no pinnacle-only forks
    for player in ladders:
        assert set(ladders[player]) == {"draftkings", "pinnacle"}
