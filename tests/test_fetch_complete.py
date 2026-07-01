"""fetch_complete wiring (council finding: a budget-truncated or partially
failed DK fetch could still earn the 'identified' consensus tag).

scrapers/draftkings_api.py writes {'fetch_complete': bool, 'records': [...]}
to draftkings_data.json. storage.db_manager.ingest_draftkings threads that
into each row's fetch_status, and get_sharp_ladders surfaces it as each book
entry's 'fetch_complete' flag for engine.matcher to read.
"""

import json

from storage.db_manager import get_sharp_ladders, ingest_draftkings, init_db


def _record(player="X", line=1.5, book="draftkings"):
    return {
        "Player": player, "Line": line, "Stat": "player_shots",
        "Bookmaker": book, "True_Over_Prob": 55.0, "True_Under_Prob": 45.0,
        "Game": "A @ B", "Commence_Time": "2026-07-05T18:00:00Z",
    }


def test_legacy_list_shape_is_still_complete(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    staging = tmp_path / "dk.json"
    staging.write_text(json.dumps([_record()]))

    ingest_draftkings(staging, db_path=db)
    ladders = get_sharp_ladders("player_shots", db_path=db)
    assert ladders["X"]["draftkings"]["fetch_complete"] is True


def test_fetch_complete_false_marks_books_incomplete(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    staging = tmp_path / "dk.json"
    staging.write_text(json.dumps({
        "fetch_complete": False,
        "records": [_record()],
    }))

    ingest_draftkings(staging, db_path=db)
    ladders = get_sharp_ladders("player_shots", db_path=db)
    assert ladders["X"]["draftkings"]["fetch_complete"] is False


def test_fetch_complete_true_marks_books_complete(tmp_path):
    db = tmp_path / "t.db"
    init_db(db)
    staging = tmp_path / "dk.json"
    staging.write_text(json.dumps({
        "fetch_complete": True,
        "records": [_record()],
    }))

    ingest_draftkings(staging, db_path=db)
    ladders = get_sharp_ladders("player_shots", db_path=db)
    assert ladders["X"]["draftkings"]["fetch_complete"] is True
