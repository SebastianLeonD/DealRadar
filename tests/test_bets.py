"""Tests for the My Bets log (tracking + grading the user's placed bets)."""

from storage import db_manager as db

BET = {
    "pp_player_name": "Mehdi Taremi",
    "dk_player_name": "Mehdi Taremi",
    "team": "Iran",
    "opponent": "New Zealand",
    "stat_type": "player_shots",
    "play": "OVER",
    "pp_line": 2.0,
    "dk_line": 1.5,
    "win_prob": 0.676,
    "verdict": "LEAN",
    "stake": 10.0,
}


def _db(tmp_path):
    return tmp_path / "bets.db"


def test_add_and_list_bet(tmp_path):
    path = _db(tmp_path)
    bet_id = db.add_bet(BET, db_path=path)
    assert bet_id is not None
    bets = db.get_bets(db_path=path)
    assert len(bets) == 1 and bets[0]["pp_player_name"] == "Mehdi Taremi"


def test_duplicate_open_bet_is_rejected(tmp_path):
    path = _db(tmp_path)
    assert db.add_bet(BET, db_path=path) is not None
    assert db.add_bet(BET, db_path=path) is None  # same open play -> no dupe


def test_summary_counts_stake_and_record(tmp_path):
    path = _db(tmp_path)
    bet_id = db.add_bet(BET, db_path=path)
    summary = db.get_bet_record_summary(db_path=path)
    assert summary["total"] == 1 and summary["total_staked"] == 10.0
    assert summary["settled"] == 0 and summary["hit_rate"] is None

    db.settle_bet(bet_id, "WIN", 3.0, db_path=path)
    summary = db.get_bet_record_summary(db_path=path)
    assert summary["settled"] == 1 and summary["wins"] == 1
    assert summary["hit_rate"] == 100.0
    assert summary["by_verdict"]["LEAN"]["wins"] == 1


def test_delete_bet(tmp_path):
    path = _db(tmp_path)
    bet_id = db.add_bet(BET, db_path=path)
    assert db.delete_bet(bet_id, db_path=path) is True
    assert db.get_bets(db_path=path) == []


def test_settled_play_can_be_retracked(tmp_path):
    # Dedupe only blocks OPEN duplicates; a graded one shouldn't block a re-bet.
    path = _db(tmp_path)
    first = db.add_bet(BET, db_path=path)
    db.settle_bet(first, "LOSS", 1.0, db_path=path)
    assert db.add_bet(BET, db_path=path) is not None
