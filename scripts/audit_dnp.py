"""Retroactive DNP audit — re-grade already-settled edges/bets where the
player never took part in the match.

Live settlement (engine/settlement.settle_edges/settle_bets) now gates on a
participation signal before grading, so a benched player VOIDs instead of
scoring an UNDER win. This script re-runs that same gate against rows that
were settled BEFORE the gate existed, re-fetching the relevant box score to
re-derive participation.

Idempotent: a row is only considered if pre_audit_result IS NULL, and once
audited pre_audit_result is set, so a second run is a no-op for it.

NOT run automatically — invoke by hand after reviewing what it would change:

    python scripts/audit_dnp.py --dry-run   # report only, writes nothing
    python scripts/audit_dnp.py             # re-grade DNP rows to VOID
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import PP_MIN_MINUTES, PP_PARTIAL_FLOOR
from engine.settlement import classify_settlement, resolve_actual
from engine.sports import sport_for_stat
from storage.db_manager import DB_PATH, get_connection, init_db, utc_now


def _audit_table(connection, table: str, dry_run: bool) -> tuple[int, int, int]:
    """Re-grade one table's already-settled, not-yet-audited rows. Returns
    (n_settled, n_regraded_to_void, n_unchanged)."""
    rows = connection.execute(
        f"SELECT * FROM {table} WHERE result IS NOT NULL AND pre_audit_result IS NULL"
    ).fetchall()

    n_settled = len(rows)
    n_regraded = 0
    stats_cache: dict = {}

    for row in rows:
        record = dict(row)
        sport_key = sport_for_stat(record['stat_type'])
        if sport_key is None:
            continue

        actual, status, minutes = resolve_actual(record, stats_cache)
        if status != 'ok':
            continue  # can't re-derive participation without a fresh box-score match

        part = classify_settlement(
            record['play'], record['pp_line'], actual,
            minutes=minutes,
            min_minutes=PP_MIN_MINUTES.get(sport_key, 0.0),
            partial_floor=PP_PARTIAL_FLOOR.get(sport_key),
        )
        if part['status'] != 'VOID' or record['result'] == 'VOID':
            continue

        n_regraded += 1
        if dry_run:
            continue

        if table == 'edges':
            connection.execute(
                """
                UPDATE edges
                SET pre_audit_result = ?, result = 'VOID', settlement_status = 'VOID',
                    outcome_over = NULL, void_reason = ?, settled_at = ?
                WHERE id = ?
                """,
                (record['result'], part['void_reason'], utc_now(), record['id']),
            )
        else:
            connection.execute(
                """
                UPDATE bets SET pre_audit_result = ?, result = 'VOID', settled_at = ?
                WHERE id = ?
                """,
                (record['result'], utc_now(), record['id']),
            )

    return n_settled, n_regraded, n_settled - n_regraded


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='report only, write nothing')
    args = parser.parse_args()

    init_db(DB_PATH)
    with get_connection(DB_PATH) as connection:
        for table in ('edges', 'bets'):
            n_settled, n_regraded, n_unchanged = _audit_table(connection, table, args.dry_run)
            suffix = '  [dry-run, nothing written]' if args.dry_run else ''
            print(
                f"{table}: {n_settled} settled, {n_regraded} re-graded to VOID, "
                f"{n_unchanged} unchanged{suffix}"
            )
        if not args.dry_run:
            connection.commit()


if __name__ == '__main__':
    main()
