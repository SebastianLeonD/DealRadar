"""Parse a pasted PrizePicks raw JSON dump into a flat board.

Reads data/raw/prizepicks_raw.json and keeps only the stat types the active
sport trades (see engine/sports.py). Unrecognized stat types are reported so
the sport's pp_stat_map can be extended from real board data.
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.sports import get_sport

RAW_FILE = Path('data/raw/prizepicks_raw.json')
OUTPUT_FILE = Path('data/processed/live.json')
BOARD_FILE = Path('data/processed/pp_board.json')
GAMES_FILE = Path('data/processed/pp_games.json')


def build_player_lookup(included):
    return {
        item['id']: item['attributes']
        for item in included
        if item.get('type') == 'new_player'
    }


def format_team_name(player_attrs):
    market = (player_attrs.get('market') or '').strip()
    team_name = (player_attrs.get('team_name') or '').strip()
    if market and team_name:
        return f"{market} {team_name}"
    return market or team_name or 'Unknown'


def detect_duration(attrs: dict) -> str | None:
    """PP marks partial-duration props in the description, e.g. 'Paraguay 1H'."""
    description = (attrs.get('description') or '')
    for marker in ('1H', '2H', 'H1', 'H2'):
        if description.endswith(marker) or f' {marker} ' in f' {description} ':
            return '1H' if marker in ('1H', 'H1') else '2H'
    return None


def parse_prizepicks_board(raw_data, sport: dict):
    stat_map = sport['pp_stat_map']
    duration_suffixes = sport.get('pp_duration_suffixes', {})
    valid_stats = set(sport['stat_models'])

    projections = raw_data.get('data', [])
    player_lookup = build_player_lookup(raw_data.get('included', []))
    clean_picks = []
    skipped_stats: Counter = Counter()

    for prop in projections:
        attrs = prop.get('attributes', {})
        # standard only: demons/goblins have different payouts and break EV math
        if attrs.get('odds_type') != 'standard':
            continue

        player_ref = prop.get('relationships', {}).get('new_player', {}).get('data')
        if not player_ref:
            continue

        player_attrs = player_lookup.get(player_ref['id'])
        if not player_attrs:
            continue

        line = attrs.get('line_score')
        stat_type = attrs.get('stat_type')
        if line is None or not stat_type:
            continue

        # Combo props ("Shots (Combo)", name "A + B") sum two players' stats.
        is_combo = stat_type.endswith(' (Combo)')
        if is_combo:
            stat_type = stat_type[: -len(' (Combo)')].strip()
            if ' + ' not in (player_attrs.get('name') or ''):
                skipped_stats[f"{stat_type} (Combo, unparseable name)"] += 1
                continue

        if stat_type not in stat_map:
            skipped_stats[stat_type + (' (Combo)' if is_combo else '')] += 1
            continue

        # Partial-duration props (1H/2H) must NEVER be priced against
        # full-match markets — that mismatch fabricates huge phantom edges.
        mapped_stat = stat_map[stat_type]
        duration = detect_duration(attrs)
        if duration is not None:
            suffix = duration_suffixes.get(duration)
            mapped_stat = f"{mapped_stat}{suffix}" if suffix else None
            if mapped_stat not in valid_stats:
                skipped_stats[f"{stat_type} [{duration}]"] += 1
                continue

        clean_picks.append({
            'name': player_attrs['name'],
            'team': format_team_name(player_attrs),
            'stat_type': mapped_stat,
            'line': line,
        })

    return clean_picks, skipped_stats


def build_full_board(raw_data, sport: dict):
    """Every standard PrizePicks prop, mapped or not — the full bet menu.

    Unlike parse_prizepicks_board (which drops stats the engine can't price),
    this keeps all stat types so the PrizePicks-only view can show them and the
    stats analyst can be asked about any of them. `mapped_stat` is the engine's
    player_* key when we have one, else None.
    """
    stat_map = sport['pp_stat_map']
    duration_suffixes = sport.get('pp_duration_suffixes', {})
    player_lookup = build_player_lookup(raw_data.get('included', []))
    board = []

    for prop in raw_data.get('data', []):
        attrs = prop.get('attributes', {})
        if attrs.get('odds_type') != 'standard':
            continue
        ref = prop.get('relationships', {}).get('new_player', {}).get('data')
        if not ref:
            continue
        player_attrs = player_lookup.get(ref['id'])
        if not player_attrs:
            continue
        line = attrs.get('line_score')
        stat_type = attrs.get('stat_type')
        if line is None or not stat_type:
            continue

        base = stat_type[:-len(' (Combo)')].strip() if stat_type.endswith(' (Combo)') else stat_type
        mapped = stat_map.get(base)
        duration = detect_duration(attrs)
        if mapped and duration:
            suffix = duration_suffixes.get(duration)
            mapped = f"{mapped}{suffix}" if suffix else None

        board.append({
            'name': player_attrs['name'],
            'team': format_team_name(player_attrs),
            'position': (player_attrs.get('position') or '').strip() or None,
            'image_url': (player_attrs.get('image_url') or '').strip() or None,
            'opponent': (attrs.get('description') or '').strip() or None,
            'game_id': attrs.get('game_id'),
            'start_time': attrs.get('start_time'),
            'stat_type': stat_type,      # raw PP display name
            'mapped_stat': mapped,       # engine key, or None when unpriced
            'line': line,
        })

    return board


def build_games(raw_data):
    """The matchups on the board: one entry per game with both team names.

    PrizePicks puts the full fixture in each `game` include's metadata. Its
    `game_id` string is what projections reference (attributes.game_id), so the
    board props join back to these by that key.
    """
    games = []
    for item in raw_data.get('included', []):
        if item.get('type') != 'game':
            continue
        attrs = item.get('attributes', {})
        meta = attrs.get('metadata') or {}
        game_id = meta.get('game_id')
        if not game_id:
            continue
        teams = (meta.get('game_info') or {}).get('teams') or {}

        def side_name(side):
            team = teams.get(side) or {}
            return team.get('name') or team.get('abbreviation') or 'TBD'

        games.append({
            'game_id': game_id,
            'home': side_name('home'),
            'away': side_name('away'),
            'start_time': attrs.get('start_time'),
            'status': meta.get('status') or attrs.get('status'),
        })
    return games


def main():
    if not RAW_FILE.exists():
        raise SystemExit(f"Missing raw file: {RAW_FILE}")

    sport = get_sport()
    with RAW_FILE.open('r') as file:
        raw_data = json.load(file)

    clean_picks, skipped_stats = parse_prizepicks_board(raw_data, sport)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open('w') as file:
        json.dump(clean_picks, file, indent=4)

    full_board = build_full_board(raw_data, sport)
    with BOARD_FILE.open('w') as file:
        json.dump(full_board, file, indent=4)
    print(f"Saved full PrizePicks board ({len(full_board)} props) to {BOARD_FILE}")

    games = build_games(raw_data)
    with GAMES_FILE.open('w') as file:
        json.dump(games, file, indent=4)
    print(f"Saved {len(games)} games to {GAMES_FILE}")

    kept = Counter(pick['stat_type'] for pick in clean_picks)
    print(f"[{sport['label']}] Mapped {len(clean_picks)} props: "
          + (', '.join(f"{stat}={count}" for stat, count in kept.items()) or 'none'))
    print(f"Saved board to {OUTPUT_FILE}")

    if skipped_stats:
        print("\nSkipped stat types on this board (extend pp_stat_map in "
              "engine/sports.py to trade them):")
        for stat, count in skipped_stats.most_common(12):
            print(f"  {stat}: {count} props")


if __name__ == '__main__':
    main()
