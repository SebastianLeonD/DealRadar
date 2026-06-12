"""NBA injury report from ESPN's public API (free, no key).

The matcher uses this to flag plays where a juicy-looking line gap is really
the sharp book pricing in news that PrizePicks hasn't reacted to yet.
Results are cached to disk so the matcher works offline.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.name_matcher import normalize_name

INJURIES_URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries'
CACHE_FILE = Path('data/processed/injuries.json')
CACHE_MAX_AGE_MINUTES = 30

# Statuses that should block or downgrade a play.
RISKY_STATUSES = {'out', 'doubtful', 'questionable', 'day-to-day'}


def fetch_injuries() -> dict[str, str]:
    """Return {normalized player name: status} from ESPN."""
    response = requests.get(INJURIES_URL, timeout=15)
    response.raise_for_status()
    payload = response.json()

    injuries: dict[str, str] = {}
    for team in payload.get('injuries', []):
        for entry in team.get('injuries', []):
            athlete = entry.get('athlete', {})
            name = athlete.get('displayName')
            status = (entry.get('status') or '').strip()
            if name and status:
                injuries[normalize_name(name)] = status
    return injuries


def _cache_is_fresh() -> bool:
    if not CACHE_FILE.exists():
        return False
    age_seconds = (
        datetime.now(timezone.utc)
        - datetime.fromtimestamp(CACHE_FILE.stat().st_mtime, tz=timezone.utc)
    ).total_seconds()
    return age_seconds <= CACHE_MAX_AGE_MINUTES * 60


def get_injury_map(force_refresh: bool = False) -> dict[str, str]:
    """Injury map with disk cache; returns whatever is available, never raises."""
    if not force_refresh and _cache_is_fresh():
        with CACHE_FILE.open('r') as file:
            return json.load(file)

    try:
        injuries = fetch_injuries()
    except Exception as error:
        print(f"Injury feed unavailable ({error}); using cache if present.")
        if CACHE_FILE.exists():
            with CACHE_FILE.open('r') as file:
                return json.load(file)
        return {}

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_FILE.open('w') as file:
        json.dump(injuries, file, indent=2)
    return injuries


def injury_status(player_name: str, injury_map: dict[str, str]) -> str | None:
    return injury_map.get(normalize_name(player_name))


def is_risky_status(status: str | None) -> bool:
    return bool(status) and status.lower() in RISKY_STATUSES


def main() -> None:
    injuries = get_injury_map(force_refresh=True)
    print(f"Fetched {len(injuries)} injury entries from ESPN.")
    risky = {name: status for name, status in injuries.items() if is_risky_status(status)}
    print(f"{len(risky)} players are Out/Doubtful/Questionable/Day-To-Day.")
    for name, status in sorted(risky.items())[:15]:
        print(f"  {name}: {status}")


if __name__ == '__main__':
    main()
