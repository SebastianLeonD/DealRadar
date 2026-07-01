"""Shadow-model Brier scorer (council: does FBref beat the market?).

Standalone readout, separate from engine/calibration.py's Phase-2 gate (which
only reads consensus_p and decides whether a probability source EARNS the
right to flag a bet). This module doesn't gate anything — it just measures,
on settled edges, whether the shadow model's logged model_p is closer to
reality than the market's consensus_p / baseline_p.

Pure stdlib (sqlite3, statistics). Run directly: `python engine/shadow_score.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db_manager import DB_PATH, get_connection, init_db

ALWAYS_50_BRIER = 0.25

CREDIBILITY_BUCKETS = [
    ("<0.3", lambda c: c < 0.3),
    ("0.3-0.5", lambda c: 0.3 <= c <= 0.5),
    (">0.5", lambda c: c > 0.5),
]

MIN_BUCKET_N = 5


def _brier(p: float, outcome: int) -> float:
    return (p - outcome) ** 2


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _fetch_rows(db_path: Path = DB_PATH) -> list[dict]:
    init_db(db_path)
    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT model_p, consensus_p, baseline_p, outcome_over,
                   model_credibility, stat_type, game_date
            FROM edges
            WHERE settlement_status = 'SCORED'
              AND model_p IS NOT NULL
              AND outcome_over IS NOT NULL
            """
        ).fetchall()
    return [dict(row) for row in rows]


def score(rows: list[dict]) -> dict:
    """Compute the headline numbers from already-fetched scored rows."""
    n_model = len(rows)
    model_brier_all = _mean([_brier(r['model_p'], r['outcome_over']) for r in rows])

    paired = [
        r for r in rows
        if r['consensus_p'] is not None and r['baseline_p'] is not None
    ]
    n_paired = len(paired)
    model_brier_paired = _mean([_brier(r['model_p'], r['outcome_over']) for r in paired])
    consensus_brier = _mean([_brier(r['consensus_p'], r['outcome_over']) for r in paired])
    baseline_brier = _mean([_brier(r['baseline_p'], r['outcome_over']) for r in paired])
    diff_vs_consensus = _mean([
        _brier(r['model_p'], r['outcome_over']) - _brier(r['consensus_p'], r['outcome_over'])
        for r in paired
    ])
    diff_vs_baseline = _mean([
        _brier(r['model_p'], r['outcome_over']) - _brier(r['baseline_p'], r['outcome_over'])
        for r in paired
    ])

    by_stat: dict[str, dict] = {}
    stat_groups: dict[str, list[dict]] = {}
    for r in rows:
        stat_groups.setdefault(r['stat_type'], []).append(r)
    for stat, group in stat_groups.items():
        if len(group) < MIN_BUCKET_N:
            continue
        by_stat[stat] = {
            'n': len(group),
            'model_brier': _mean([_brier(r['model_p'], r['outcome_over']) for r in group]),
        }

    by_credibility: dict[str, dict] = {}
    for label, predicate in CREDIBILITY_BUCKETS:
        group = [r for r in rows if r['model_credibility'] is not None and predicate(r['model_credibility'])]
        if len(group) < MIN_BUCKET_N:
            continue
        by_credibility[label] = {
            'n': len(group),
            'model_brier': _mean([_brier(r['model_p'], r['outcome_over']) for r in group]),
        }

    return {
        'n_model': n_model,
        'model_brier_all': model_brier_all,
        'n_paired': n_paired,
        'model_brier_paired': model_brier_paired,
        'consensus_brier': consensus_brier,
        'baseline_brier': baseline_brier,
        'diff_vs_consensus': diff_vs_consensus,
        'diff_vs_baseline': diff_vs_baseline,
        'by_stat': by_stat,
        'by_credibility': by_credibility,
    }


def _fmt(x: float | None, digits: int = 4) -> str:
    return f"{x:.{digits}f}" if x is not None else "n/a"


def report(db_path: Path = DB_PATH) -> str:
    rows = _fetch_rows(db_path)
    result = score(rows)

    lines = ['Shadow-Model Brier Scorer (FBref model vs market, settled edges)', '']
    lines.append(f"Reference: Brier {ALWAYS_50_BRIER} = always saying 50%")
    lines.append('')
    lines.append(f"n scored w/ model_p: {result['n_model']}")
    lines.append(f"  model Brier (all): {_fmt(result['model_brier_all'])}")
    lines.append('')
    lines.append(f"Paired subset (model_p & consensus_p & baseline_p all present): n={result['n_paired']}")
    if result['n_paired']:
        lines.append(f"  model Brier:      {_fmt(result['model_brier_paired'])}")
        lines.append(f"  consensus Brier:  {_fmt(result['consensus_brier'])}")
        lines.append(f"  baseline Brier:   {_fmt(result['baseline_brier'])}")
        lines.append(
            f"  mean paired diff model-consensus: {_fmt(result['diff_vs_consensus'])} "
            "(negative = model better)"
        )
        lines.append(
            f"  mean paired diff model-baseline:  {_fmt(result['diff_vs_baseline'])} "
            "(negative = model better)"
        )
    else:
        lines.append('  (no rows with both consensus_p and baseline_p present)')

    lines.append('')
    lines.append(f"By stat_type (n >= {MIN_BUCKET_N}):")
    if result['by_stat']:
        for stat, bucket in sorted(result['by_stat'].items()):
            lines.append(f"  {stat.ljust(28)} n={bucket['n']:<4} model Brier={_fmt(bucket['model_brier'])}")
    else:
        lines.append('  (no stat_type has n >= %d)' % MIN_BUCKET_N)

    lines.append('')
    lines.append(f"By model_credibility bucket (n >= {MIN_BUCKET_N}):")
    if result['by_credibility']:
        for label, bucket in result['by_credibility'].items():
            lines.append(f"  {label.ljust(8)} n={bucket['n']:<4} model Brier={_fmt(bucket['model_brier'])}")
    else:
        lines.append('  (no credibility bucket has n >= %d)' % MIN_BUCKET_N)

    return '\n'.join(lines)


def main() -> None:
    print(report())


if __name__ == '__main__':
    main()
