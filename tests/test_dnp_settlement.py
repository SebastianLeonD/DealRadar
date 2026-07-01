"""World Cup DNP fix: a player entirely absent from the pitch must settle as
VOID, never as an UNDER win — both live (settle_edges) and retroactively
(scripts/audit_dnp.py) for edges settled before the participation gate
existed."""

import functools
from datetime import datetime, timedelta, timezone

import engine.settlement as settlement
from engine.config import PP_MIN_MINUTES
from engine.settlement import classify_settlement
from storage.db_manager import get_connection, get_unsettled_edges, init_db, log_edges


def _iso(dt):
    return dt.isoformat()


# ---- classify_settlement gates on the real world_cup floor -----------------
def test_world_cup_min_minutes_gates_dnp():
    floor = PP_MIN_MINUTES['world_cup']
    dnp = classify_settlement('UNDER', 2.5, 0, minutes=0.0, min_minutes=floor)
    assert dnp['status'] == 'VOID'
    played = classify_settlement('UNDER', 2.5, 0, minutes=90.0, min_minutes=floor)
    assert played['status'] == 'SCORED'  # actually played, 0 shots is a genuine UNDER win


# ---- fake ESPN box score: 'appearances' is the participation signal --------
def _box(shots_by_player: dict[str, float], appeared: dict[str, bool]) -> dict:
    return {
        name: {'totalShots': shots, 'appearances': 1.0 if appeared[name] else 0.0}
        for name, shots in shots_by_player.items()
    }


def _seed_edge(db, name, commence_hours_ago=6):
    commence = _iso(datetime.now(timezone.utc) - timedelta(hours=commence_hours_ago))
    log_edges([{
        'pp_player_name': name, 'dk_player_name': name, 'stat_type': 'player_shots',
        'play': 'UNDER', 'pp_line': 1.5, 'dk_line_at_flag': 1.5, 'edge_type': 'x',
        'commence_time': commence,
    }], db_path=db)


def test_settle_edges_voids_dnp_player(tmp_path, monkeypatch):
    db = tmp_path / 'dnp.db'
    init_db(db)
    monkeypatch.setattr(settlement, 'get_unsettled_edges',
                         functools.partial(get_unsettled_edges, db_path=db))
    monkeypatch.setattr(settlement, 'settle_edge',
                         lambda *a, **kw: _settle_edge_in(db, *a, **kw))
    monkeypatch.setattr(settlement, 'force_void_edge', lambda *a, **kw: None)

    box = _box(
        {'Benched Player': 0.0, 'Starter Player': 3.0},
        {'Benched Player': False, 'Starter Player': True},
    )
    monkeypatch.setattr(settlement, 'fetch_stats_for_date', lambda *a, **kw: box)

    _seed_edge(db, 'Benched Player')
    _seed_edge(db, 'Starter Player')

    settlement.settle_edges()

    with get_connection(db) as conn:
        rows = {row['pp_player_name']: dict(row) for row in conn.execute('SELECT * FROM edges')}

    benched = rows['Benched Player']
    assert benched['result'] == 'VOID'
    assert benched['settlement_status'] == 'VOID'
    assert benched['outcome_over'] is None

    starter = rows['Starter Player']
    # Starter took 3 shots on a 1.5 UNDER line -> genuine LOSS, not voided.
    assert starter['result'] == 'LOSS'
    assert starter['settlement_status'] == 'SCORED'


def _settle_edge_in(db, edge_id, result, actual_value, **kwargs):
    from storage.db_manager import settle_edge
    settle_edge(edge_id, result, actual_value, db_path=db, **kwargs)


# ---- retroactive audit: pre-gate settled row gets re-graded VOID -----------
def test_audit_dnp_regrades_settled_under_win(tmp_path, monkeypatch):
    from scripts import audit_dnp

    db = tmp_path / 'audit.db'
    init_db(db)
    _seed_edge(db, 'Benched Player')
    _seed_edge(db, 'Starter Player')

    with get_connection(db) as conn:
        # Simulate the OLD (pre-fix) settlement: benched player's 0 shots on a
        # 1.5 UNDER graded as a WIN, no participation gate applied.
        conn.execute(
            "UPDATE edges SET result='WIN', actual_value=0, settlement_status='SCORED', "
            "outcome_over=0 WHERE pp_player_name='Benched Player'"
        )
        conn.execute(
            "UPDATE edges SET result='LOSS', actual_value=3, settlement_status='SCORED', "
            "outcome_over=1 WHERE pp_player_name='Starter Player'"
        )
        conn.commit()

    box = {
        'Benched Player': {'totalShots': 0.0, 'appearances': 0.0},
        'Starter Player': {'totalShots': 3.0, 'appearances': 1.0},
    }
    monkeypatch.setattr(settlement, 'fetch_stats_for_date', lambda *a, **kw: box)

    with get_connection(db) as conn:
        n_settled, n_regraded, n_unchanged = audit_dnp._audit_table(conn, 'edges', dry_run=False)
        conn.commit()

    assert n_settled == 2
    assert n_regraded == 1
    assert n_unchanged == 1

    with get_connection(db) as conn:
        rows = {row['pp_player_name']: dict(row) for row in conn.execute('SELECT * FROM edges')}

    benched = rows['Benched Player']
    assert benched['result'] == 'VOID'
    assert benched['settlement_status'] == 'VOID'
    assert benched['pre_audit_result'] == 'WIN'  # old (wrong) result preserved

    starter = rows['Starter Player']
    assert starter['result'] == 'LOSS'
    assert starter['pre_audit_result'] is None  # untouched, no re-audit needed


def test_audit_dnp_idempotent(tmp_path, monkeypatch):
    from scripts import audit_dnp

    db = tmp_path / 'audit2.db'
    init_db(db)
    _seed_edge(db, 'Benched Player')
    with get_connection(db) as conn:
        conn.execute(
            "UPDATE edges SET result='WIN', actual_value=0, settlement_status='SCORED', "
            "outcome_over=0 WHERE pp_player_name='Benched Player'"
        )
        conn.commit()

    box = {'Benched Player': {'totalShots': 0.0, 'appearances': 0.0}}
    monkeypatch.setattr(settlement, 'fetch_stats_for_date', lambda *a, **kw: box)

    with get_connection(db) as conn:
        audit_dnp._audit_table(conn, 'edges', dry_run=False)
        conn.commit()
    # second pass: already has pre_audit_result set -> not reconsidered
    with get_connection(db) as conn:
        n_settled, n_regraded, n_unchanged = audit_dnp._audit_table(conn, 'edges', dry_run=False)

    assert n_settled == 0  # excluded by pre_audit_result IS NULL filter
    assert n_regraded == 0
