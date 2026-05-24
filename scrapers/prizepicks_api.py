import json
from pathlib import Path

RAW_FILE = Path('data/raw/prizepicks_raw.json')
OUTPUT_FILE = Path('data/processed/live.json')

# Only ingest single-stat "Points" props. Excludes Fantasy Score, PRA,
# Pts+Rebs, and "Points (Combo)" multi-player slips.
ALLOWED_RAW_STAT_TYPES = {'Points'}

STAT_TYPE_MAP = {
    'Points': 'player_points',
}


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


def normalize_stat_type(stat_type):
    return STAT_TYPE_MAP.get(stat_type, stat_type)


def parse_prizepicks_board(raw_data):
    projections = raw_data.get('data', [])
    player_lookup = build_player_lookup(raw_data.get('included', []))
    clean_picks = []

    for prop in projections:
        attrs = prop.get('attributes', {})
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
        if stat_type not in ALLOWED_RAW_STAT_TYPES:
            continue

        clean_picks.append({
            'name': player_attrs['name'],
            'team': format_team_name(player_attrs),
            'stat_type': normalize_stat_type(stat_type),
            'line': line,
        })

    return clean_picks


def main():
    if not RAW_FILE.exists():
        raise SystemExit(f"Missing raw file: {RAW_FILE}")

    with RAW_FILE.open('r') as file:
        raw_data = json.load(file)

    clean_picks = parse_prizepicks_board(raw_data)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open('w') as file:
        json.dump(clean_picks, file, indent=4)

    print(f"Successfully mapped {len(clean_picks)} player_points props.")
    print(f"Saved points-only board to {OUTPUT_FILE}")
    for pick in clean_picks[:5]:
        print(pick)


if __name__ == '__main__':
    main()
