"""Grade logged edges against real box scores (ESPN, free).

Closes the feedback loop: CLV tells you if you beat the market, settlement
tells you if the model's probabilities are honest. Run any time after games
finish; already-settled edges are skipped.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.name_matcher import match_player_name
from engine.sports import get_sport, sport_for_stat
from scrapers.results_api import fetch_stats_for_date
from storage.db_manager import get_record_summary, get_unsettled_edges, settle_edge

# Don't try to settle an edge until the game has plausibly finished.
SETTLE_AFTER_HOURS = 4


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def candidate_dates(edge: dict) -> list[str]:
    """US game dates (YYYYMMDD) an edge's game may fall on.

    Prefers commence_time; falls back to flagged_at. Includes the previous
    day because late UTC timestamps roll past midnight on US evening games.
    """
    anchor = _parse_ts(edge.get('commence_time')) or _parse_ts(edge['flagged_at'])
    if anchor is None:
        return []
    dates = {
        (anchor - timedelta(days=1)).strftime('%Y%m%d'),
        anchor.strftime('%Y%m%d'),
    }
    return sorted(dates)


def game_finished(edge: dict, now: datetime) -> bool:
    start = _parse_ts(edge.get('commence_time'))
    if start is not None:
        return now >= start + timedelta(hours=SETTLE_AFTER_HOURS)
    flagged = _parse_ts(edge['flagged_at'])
    return flagged is not None and now >= flagged + timedelta(hours=SETTLE_AFTER_HOURS)


def grade(play: str, pp_line: float, actual: float) -> str:
    if actual == pp_line:
        return 'PUSH'
    if play == 'OVER':
        return 'WIN' if actual > pp_line else 'LOSS'
    return 'WIN' if actual < pp_line else 'LOSS'


def settle_edges() -> tuple[int, list[str]]:
    """Settle every gradeable edge. Returns (settled count, report lines)."""
    now = datetime.now(timezone.utc)
    edges = get_unsettled_edges()
    pending = [edge for edge in edges if game_finished(edge, now)]
    lines: list[str] = []

    if not pending:
        lines.append(f"No edges ready to settle ({len(edges)} unsettled, none past game time).")
        return 0, lines

    stats_cache: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    settled = 0
    missing = 0
    unknown_stat = 0

    for edge in pending:
        sport_key = sport_for_stat(edge['stat_type'])
        if sport_key is None:
            unknown_stat += 1
            continue
        sport = get_sport(sport_key)
        espn_stat = sport['espn_stats'].get(edge['stat_type'])
        if espn_stat is None:
            unknown_stat += 1  # e.g. 1H stats — no box-score source to grade
            continue

        legs = [name.strip() for name in edge['dk_player_name'].split(' + ')]
        actual = None
        for date in candidate_dates(edge):
            cache_key = (sport['espn_path'], date)
            if cache_key not in stats_cache:
                stats_cache[cache_key] = fetch_stats_for_date(
                    sport['espn_path'], sport['espn_box_format'], date,
                )
            box = stats_cache[cache_key]
            leg_values = []
            for leg in legs:  # combo edges sum every leg's actual
                matched, _ = match_player_name(leg, list(box.keys()))
                if matched is None or espn_stat not in box[matched]:
                    break
                leg_values.append(box[matched][espn_stat])
            if len(leg_values) == len(legs):
                actual = sum(leg_values)
                break

        if actual is None:
            missing += 1
            continue

        result = grade(edge['play'], edge['pp_line'], actual)
        settle_edge(edge['id'], result, actual)
        settled += 1
        stat_label = edge['stat_type'].replace('player_', '')
        lines.append(
            f"  {result.ljust(5)} {edge['pp_player_name'].ljust(24)} "
            f"{edge['play'].ljust(5)} {edge['pp_line']} {stat_label} -> actual {actual:.0f}"
        )

    if unknown_stat:
        lines.append(f"  ({unknown_stat} edge(s) skipped: stat not in any sport config)")

    lines.insert(0, f"Settled {settled} edge(s); {missing} had no box score match.")
    return settled, lines


def build_record_report() -> list[str]:
    summary = get_record_summary()
    lines = ['', 'Lifetime Record (settled edges):']

    if not summary['settled']:
        lines.append('  Nothing settled yet. Run settlement after games finish.')
        return lines

    lines.append(
        f"  Overall: {summary['wins']}W - {summary['losses']}L - {summary['pushes']}P"
        + (f"  ({summary['hit_rate']}% hit rate)" if summary['hit_rate'] is not None else '')
    )
    if summary['avg_predicted_prob'] is not None and summary['hit_rate'] is not None:
        gap = round(summary['hit_rate'] - summary['avg_predicted_prob'], 1)
        lines.append(
            f"  Model said {summary['avg_predicted_prob']}% on average — "
            f"actual {summary['hit_rate']}% ({gap:+.1f} calibration gap)"
        )
    for verdict, bucket in sorted(summary['by_verdict'].items()):
        lines.append(
            f"  {verdict.ljust(8)}: {bucket['wins']}W - {bucket['losses']}L - {bucket['pushes']}P"
        )
    return lines


def main() -> None:
    _, report = settle_edges()
    report.extend(build_record_report())
    print('\n'.join(report))


if __name__ == '__main__':
    main()
