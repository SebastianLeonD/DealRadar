"""Player box-score stats from ESPN's public API (free, no key) — any sport.

Two box-score formats exist:
  'labels'  — NBA style: boxscore.players[].statistics[].labels + stats arrays
  'rosters' — soccer style: rosters[].roster[].stats with named values

Both normalize to {player display name: {stat key: value}} so settlement can
grade any stat the sport config maps (PTS, totalShots, shotsOnTarget, ...).
"""

import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ESPN_BASE = 'https://site.api.espn.com/apis/site/v2/sports'


def fetch_completed_event_ids(espn_path: str, date_yyyymmdd: str) -> list[str]:
    """Event IDs for finished games on a given US date (YYYYMMDD)."""
    url = f"{ESPN_BASE}/{espn_path}/scoreboard"
    response = requests.get(url, params={'dates': date_yyyymmdd}, timeout=15)
    response.raise_for_status()

    event_ids = []
    for event in response.json().get('events', []):
        status = event.get('status', {}).get('type', {})
        if status.get('completed'):
            event_ids.append(event['id'])
    return event_ids


def _parse_labels_format(payload: dict) -> dict[str, dict[str, float]]:
    stats_by_player: dict[str, dict[str, float]] = {}
    for team in payload.get('boxscore', {}).get('players', []):
        for stat_group in team.get('statistics', []):
            labels = stat_group.get('labels') or stat_group.get('names') or []
            for athlete in stat_group.get('athletes', []):
                values = athlete.get('stats') or []
                name = athlete.get('athlete', {}).get('displayName')
                if not name or not values:
                    continue  # DNP rows have empty stats
                entry = stats_by_player.setdefault(name, {})
                for label, value in zip(labels, values):
                    try:
                        entry[label] = float(value)
                    except (TypeError, ValueError):
                        # "made-attempted" strings like 3PT "3-7" → 3PT_made = 3
                        if isinstance(value, str) and '-' in value:
                            made = value.split('-')[0]
                            try:
                                entry[f"{label}_made"] = float(made)
                            except ValueError:
                                pass
    return stats_by_player


def _parse_rosters_format(payload: dict) -> dict[str, dict[str, float]]:
    stats_by_player: dict[str, dict[str, float]] = {}
    for team in payload.get('rosters', []):
        for entry in team.get('roster', []):
            name = entry.get('athlete', {}).get('displayName')
            stats = entry.get('stats') or []
            if not name or not stats:
                continue  # unused subs have no stats
            player_stats = stats_by_player.setdefault(name, {})
            for stat in stats:
                value = stat.get('value')
                if stat.get('name') and value is not None:
                    player_stats[stat['name']] = float(value)
    return stats_by_player


def fetch_player_stats(
    espn_path: str,
    event_id: str,
    box_format: str,
) -> dict[str, dict[str, float]]:
    url = f"{ESPN_BASE}/{espn_path}/summary"
    response = requests.get(url, params={'event': event_id}, timeout=15)
    response.raise_for_status()
    payload = response.json()

    if box_format == 'rosters':
        return _parse_rosters_format(payload)
    return _parse_labels_format(payload)


def fetch_stats_for_date(
    espn_path: str,
    box_format: str,
    date_yyyymmdd: str,
) -> dict[str, dict[str, float]]:
    """Merged {player: {stat: value}} across every completed game on a date."""
    merged: dict[str, dict[str, float]] = {}
    try:
        event_ids = fetch_completed_event_ids(espn_path, date_yyyymmdd)
    except Exception as error:
        print(f"Scoreboard unavailable for {espn_path} {date_yyyymmdd}: {error}")
        return merged

    for event_id in event_ids:
        try:
            merged.update(fetch_player_stats(espn_path, event_id, box_format))
        except Exception as error:
            print(f"Box score unavailable for event {event_id}: {error}")
    return merged


def main() -> None:
    import argparse

    from engine.sports import get_sport

    parser = argparse.ArgumentParser(description='Fetch box-score stats for a date')
    parser.add_argument('date', help='US game date as YYYYMMDD, e.g. 20260612')
    args = parser.parse_args()

    sport = get_sport()
    stats = fetch_stats_for_date(sport['espn_path'], sport['espn_box_format'], args.date)
    print(f"[{sport['label']}] Found stats for {len(stats)} players on {args.date}.")
    wanted = list(sport['espn_stats'].values())
    for name, values in sorted(stats.items())[:8]:
        shown = {key: values.get(key) for key in wanted if key in values}
        print(f"  {name}: {shown}")


if __name__ == '__main__':
    main()
