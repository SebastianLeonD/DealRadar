"""Grade logged edges against real box scores (ESPN, free).

Closes the feedback loop: CLV tells you if you beat the market, settlement
tells you if the model's probabilities are honest. Run any time after games
finish; already-settled edges are skipped.
"""

import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import (
    POST_FIX_CUTOFF,
    PP_MIN_MINUTES,
    PP_PARTIAL_FLOOR,
    STALE_SETTLE_MAX_HOURS,
)
from engine.name_matcher import match_player_name
from engine.sports import get_sport, sport_for_stat
from scrapers.results_api import fetch_stats_for_date
from storage.db_manager import (
    force_void_edge,
    get_record_summary,
    get_unsettled_bets,
    get_unsettled_edges,
    settle_bet,
    settle_edge,
)

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
    anchor = _parse_ts(edge.get('commence_time')) or _parse_ts(
        edge.get('flagged_at') or edge.get('created_at')
    )
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
    anchor = _parse_ts(edge.get('flagged_at') or edge.get('created_at'))
    return anchor is not None and now >= anchor + timedelta(hours=SETTLE_AFTER_HOURS)


def _participation_minutes(sport: dict, box: dict, matched_names: list[str]) -> float | None:
    """Synthetic 0.0/90.0 'minutes' from ESPN's binary participation stat
    (e.g. soccer 'appearances'). None if the sport has no such stat, or the
    matched player's box-score row doesn't carry it. Combo plays take the
    minimum across legs so any DNP leg drags the whole play to VOID."""
    participation_stat = sport.get('espn_participation_stat')
    if participation_stat is None:
        return None
    minutes = None
    for name in matched_names:
        value = box[name].get(participation_stat)
        if value is None:
            continue
        leg_minutes = 90.0 if value >= 1.0 else 0.0
        minutes = leg_minutes if minutes is None else min(minutes, leg_minutes)
    return minutes


def resolve_actual(row: dict, stats_cache: dict) -> tuple[float | None, str, float | None]:
    """Look up a play's actual stat from box scores. Returns (value, status,
    minutes) where status is 'ok', 'missing' (no box-score match) or 'unknown'
    (stat has no box-score source, e.g. a 1H prop). minutes is the real/synthetic
    participation figure for the settlement floor, or None if unavailable."""
    sport_key = sport_for_stat(row['stat_type'])
    if sport_key is None:
        return None, 'unknown', None
    sport = get_sport(sport_key)
    espn_stat = sport['espn_stats'].get(row['stat_type'])
    if espn_stat is None:
        return None, 'unknown', None

    legs = [name.strip() for name in row['dk_player_name'].split(' + ')]
    for date in candidate_dates(row):
        cache_key = (sport['espn_path'], date)
        if cache_key not in stats_cache:
            stats_cache[cache_key] = fetch_stats_for_date(
                sport['espn_path'], sport['espn_box_format'], date,
            )
        box = stats_cache[cache_key]
        leg_values = []
        matched_names = []
        for leg in legs:  # combo plays sum every leg's actual
            matched, _ = match_player_name(leg, list(box.keys()))
            if matched is None or espn_stat not in box[matched]:
                break
            leg_values.append(box[matched][espn_stat])
            matched_names.append(matched)
        if len(leg_values) == len(legs):
            minutes = _participation_minutes(sport, box, matched_names)
            return sum(leg_values), 'ok', minutes
    return None, 'missing', None


def _box_score_exists_without_match(edge: dict, stats_cache: dict) -> bool:
    """True when a box score WAS fetched (non-empty) for one of the edge's
    candidate dates but its player name(s) didn't match anyone in it — as
    opposed to no box score existing at all for that date. Used by the
    force-void path to tell "name-match miss" (fixable with an alias) apart
    from "game never got box-scored" (genuinely stale)."""
    sport_key = sport_for_stat(edge['stat_type'])
    if sport_key is None:
        return False
    sport = get_sport(sport_key)
    legs = [name.strip() for name in edge['dk_player_name'].split(' + ')]
    for date in candidate_dates(edge):
        cache_key = (sport['espn_path'], date)
        if cache_key not in stats_cache:
            stats_cache[cache_key] = fetch_stats_for_date(
                sport['espn_path'], sport['espn_box_format'], date,
            )
        box = stats_cache[cache_key]
        if not box:
            continue
        for leg in legs:
            matched, _ = match_player_name(leg, list(box.keys()))
            if matched is None:
                return True
    return False


def grade(play: str, pp_line: float, actual: float) -> str:
    if actual == pp_line:
        return 'PUSH'
    if play == 'OVER':
        return 'WIN' if actual > pp_line else 'LOSS'
    return 'WIN' if actual < pp_line else 'LOSS'


def classify_settlement(
    play: str,
    pp_line: float,
    actual: float | None,
    *,
    minutes: float | None = None,
    min_minutes: float = 0.0,
    partial_floor: float | None = None,
) -> dict:
    """Phase-2 settlement partition (spec §3.1/§3.2). Participation is checked
    BEFORE the over/under decision, so a benched/partial player is never graded
    as a win on a low line.

    Returns {status, outcome_over, void_reason, partial_game} where status is
    one of SCORED / PUSH / VOID / NO_DATA (None). The canonical outcome is FIXED
    OVER: outcome_over = 1 if actual > pp_line else 0 (side-agnostic), NULL on
    PUSH/VOID. Invariant: status=='SCORED' iff outcome_over is not None.
    """
    if not math.isfinite(pp_line):
        raise AssertionError(f"classify_settlement: non-finite pp_line {pp_line!r}")
    if actual is None:
        return {'status': None, 'outcome_over': None,
                'void_reason': None, 'partial_game': 0}
    assert math.isfinite(actual), f"non-finite actual {actual!r}"

    # Participation gate first (strict minutes floor: minutes < floor -> VOID).
    if minutes is not None:
        if minutes < min_minutes:
            return {'status': 'VOID', 'outcome_over': None,
                    'void_reason': 'below_minutes_threshold', 'partial_game': 0}
        if partial_floor is not None and minutes < partial_floor:
            return {'status': 'VOID', 'outcome_over': None,
                    'void_reason': 'partial_game', 'partial_game': 1}

    if actual == pp_line:
        return {'status': 'PUSH', 'outcome_over': None,
                'void_reason': None, 'partial_game': 0}
    return {'status': 'SCORED', 'outcome_over': 1 if actual > pp_line else 0,
            'void_reason': None, 'partial_game': 0}


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
        actual, status, minutes = resolve_actual(edge, stats_cache)
        if status == 'unknown':
            unknown_stat += 1
            continue
        if actual is None:
            missing += 1
            continue

        result = grade(edge['play'], edge['pp_line'], actual)
        # Phase-2 partition: participation gate runs on real/synthetic minutes
        # when the sport's box score exposes them (see resolve_actual), so a
        # DNP player is VOIDed instead of graded as an UNDER win.
        sport_key = sport_for_stat(edge['stat_type'])
        part = classify_settlement(
            edge['play'], edge['pp_line'], actual,
            minutes=minutes,
            min_minutes=PP_MIN_MINUTES.get(sport_key, 0.0),
            partial_floor=PP_PARTIAL_FLOOR.get(sport_key),
        )
        if part['status'] == 'VOID':
            result = 'VOID'
        settle_edge(
            edge['id'], result, actual,
            settlement_status=part['status'], outcome_over=part['outcome_over'],
            void_reason=part['void_reason'], partial_game=part['partial_game'],
        )
        settled += 1
        stat_label = edge['stat_type'].replace('player_', '')
        lines.append(
            f"  {result.ljust(5)} {edge['pp_player_name'].ljust(24)} "
            f"{edge['play'].ljust(5)} {edge['pp_line']} {stat_label} -> actual {actual:.0f}"
        )

    if unknown_stat:
        lines.append(f"  ({unknown_stat} edge(s) skipped: stat not in any sport config)")

    # Force-void anything that's been unsettled too long (STALE_SETTLE_MAX_HOURS)
    # so a bad match/box-score gap doesn't sit open forever and starve the
    # calibration gate's SCORED pool.
    stale_voided = 0
    name_match_misses = 0
    for edge in get_unsettled_edges():
        anchor = _parse_ts(edge.get('commence_time')) or _parse_ts(
            edge.get('flagged_at') or edge.get('created_at')
        )
        if anchor and now - anchor > timedelta(hours=STALE_SETTLE_MAX_HOURS):
            if _box_score_exists_without_match(edge, stats_cache):
                force_void_edge(edge['id'], 'no_name_match')
                name_match_misses += 1
                date = candidate_dates(edge)[-1] if candidate_dates(edge) else '?'
                print(
                    f"WARNING: possible name-match miss: {edge['pp_player_name']} "
                    f"not found in {date} box score"
                )
            else:
                force_void_edge(edge['id'], 'stale_unsettled')
            stale_voided += 1
    if stale_voided:
        lines.append(
            f"Force-voided {stale_voided} stale unsettled edge(s) "
            f"(>{STALE_SETTLE_MAX_HOURS}h)"
            + (f", {name_match_misses} flagged as possible name-match misses."
               if name_match_misses else '.')
        )

    lines.insert(0, f"Settled {settled} edge(s); {missing} had no box score match.")
    return settled, lines


def settle_bets() -> tuple[int, list[str]]:
    """Grade the bets the user actually placed, same box-score path as edges."""
    now = datetime.now(timezone.utc)
    pending = [bet for bet in get_unsettled_bets() if game_finished(bet, now)]
    lines: list[str] = []
    if not pending:
        lines.append("No bets ready to settle (none past game time).")
        return 0, lines

    stats_cache: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    settled = missing = unknown_stat = 0

    for bet in pending:
        actual, status, minutes = resolve_actual(bet, stats_cache)
        if status == 'unknown':
            unknown_stat += 1
            continue
        if actual is None:
            missing += 1
            continue
        result = grade(bet['play'], bet['pp_line'], actual)
        # Bets have no settlement_status column, so a DNP just gets result
        # overwritten to VOID (same participation gate as edges).
        sport_key = sport_for_stat(bet['stat_type'])
        part = classify_settlement(
            bet['play'], bet['pp_line'], actual,
            minutes=minutes,
            min_minutes=PP_MIN_MINUTES.get(sport_key, 0.0),
            partial_floor=PP_PARTIAL_FLOOR.get(sport_key),
        )
        if part['status'] == 'VOID':
            result = 'VOID'
        settle_bet(bet['id'], result, actual)
        settled += 1
        stat_label = bet['stat_type'].replace('player_', '')
        lines.append(
            f"  {result.ljust(5)} {bet['pp_player_name'].ljust(24)} "
            f"{bet['play'].ljust(5)} {bet['pp_line']} {stat_label} -> actual {actual:.0f}"
        )

    if unknown_stat:
        lines.append(f"  ({unknown_stat} bet(s) can't be graded yet — no box-score source)")
    lines.insert(0, f"Settled {settled} bet(s); {missing} had no box score match.")
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

    # Evidence-gated verdicts shipped 2026-07-01 — track separately whether
    # the repaired pipeline's own calls actually hit.
    post_fix = get_record_summary(since=POST_FIX_CUTOFF)
    lines.append('')
    lines.append('Post-fix record (since 2026-07-01):')
    if not post_fix['settled']:
        lines.append('  Nothing settled yet.')
    else:
        lines.append(
            f"  Overall: {post_fix['wins']}W - {post_fix['losses']}L - {post_fix['pushes']}P"
            + (f"  ({post_fix['hit_rate']}% hit rate)" if post_fix['hit_rate'] is not None else '')
        )
        for verdict, bucket in sorted(post_fix['by_verdict'].items()):
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
