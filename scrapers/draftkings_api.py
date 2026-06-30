"""Fetch sharp player-prop lines from The-Odds-API for the active sport.

Set ACTIVE_SPORT in .env ('nba' or 'world_cup'). Pulls every market the
sport config defines (plus alternate ladders where they exist) from multiple
US books in one request per game.

Credit control: only games starting within the sport's kickoff window are
fetched (the World Cup feed lists ~70 future matches; fetching them all
would burn hundreds of credits).

Env overrides (.env):
    ACTIVE_SPORT=world_cup
    SHARP_BOOKMAKERS=draftkings,fanduel,betmgm,williamhill_us
    INCLUDE_ALTERNATE_LINES=1
    MAX_HOURS_AHEAD=36
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.config import DEFAULT_DEVIG_METHOD
from engine.devig import devig_two_sided
from engine.probability import devig_one_sided, implied_prob
from engine.sports import get_sport

load_dotenv()
API_KEY = os.getenv('ODDS_API_KEY')

DEFAULT_BOOKMAKERS = 'draftkings,fanduel,betmgm,williamhill_us'
BOOKMAKERS = os.getenv('SHARP_BOOKMAKERS', DEFAULT_BOOKMAKERS)
INCLUDE_ALTERNATES = os.getenv('INCLUDE_ALTERNATE_LINES', '1') == '1'

OUTPUT_FILE = Path('data/processed/draftkings_data.json')


def market_list(sport: dict) -> list[str]:
    markets = list(sport['markets'])
    if INCLUDE_ALTERNATES:
        markets += [
            sport['alternate_markets'][m]
            for m in sport['markets']
            if m in sport['alternate_markets']
        ]
    return markets


def base_stat_for_market(market_key: str, sport: dict) -> str:
    binary = sport.get('binary_markets', {}).get(market_key)
    if binary:
        return binary['stat']
    for base, alternate in sport['alternate_markets'].items():
        if market_key == alternate:
            return base
    return market_key


def flatten_binary_market(market, binary_config, game_label, commence_time, book_key):
    """Yes/No markets (e.g. anytime scorer) become a 0.5-line ladder point:
    P(Yes) = P(stat >= 1) = P(over 0.5)."""
    records = []
    prices: dict[str, dict[str, float]] = {}
    for outcome in market.get('outcomes', []):
        player = outcome.get('description', 'Unknown')
        prices.setdefault(player, {})[outcome['name']] = outcome['price']

    for player, sides in prices.items():
        price_over = price_under = None
        method = shin_z = hold = None
        if 'Yes' in sides and 'No' in sides:
            dv = devig_two_sided(sides['Yes'], sides['No'], DEFAULT_DEVIG_METHOD)
            tp_over, tp_under = dv['p_over'], dv['p_under']
            price_over, price_under = sides['Yes'], sides['No']
            method, shin_z, hold = dv['devig_method'], dv['z'], dv['hold']
        elif 'Yes' in sides:
            tp_over = devig_one_sided(sides['Yes'], binary_config['margin'])
            tp_under = 1 - tp_over
            price_over = sides['Yes']
            method = 'one_sided'
        else:
            continue
        records.append({
            'Player': player,
            'Game': game_label,
            'Stat': binary_config['stat'],
            'Line': 0.5,
            'Bookmaker': book_key,
            'Commence_Time': commence_time,
            'True_Over_Prob': round(tp_over * 100, 2),
            'True_Under_Prob': round(tp_under * 100, 2),
            'Price_Over': price_over,
            'Price_Under': price_under,
            'Devig_Method': method,
            'Shin_Z': round(shin_z, 4) if shin_z is not None else None,
            'Hold': round(hold, 4) if hold is not None else None,
        })
    return records


def fetch_events(sport: dict):
    print(f"Fetching upcoming {sport['label']} games...")
    url = f"https://api.the-odds-api.com/v4/sports/{sport['odds_api_key']}/events"
    response = requests.get(url, params={'apiKey': API_KEY})
    if response.status_code != 200:
        print(f"Failed to fetch events: {response.text}")
        return []
    return response.json()


def filter_upcoming(events: list[dict], sport: dict) -> list[dict]:
    """Keep games starting soon (or in progress) — the only ones worth credits."""
    hours_ahead = float(os.getenv('MAX_HOURS_AHEAD', sport['max_hours_ahead']))
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(hours=3)
    window_end = now + timedelta(hours=hours_ahead)

    upcoming = []
    for event in events:
        try:
            start = datetime.fromisoformat(event['commence_time'].replace('Z', '+00:00'))
        except (KeyError, ValueError):
            continue
        if window_start <= start <= window_end:
            upcoming.append(event)
    return upcoming


def fetch_event_odds(event_id: str, sport: dict):
    url = f"https://api.the-odds-api.com/v4/sports/{sport['odds_api_key']}/events/{event_id}/odds"
    params = {
        'apiKey': API_KEY,
        'markets': ','.join(market_list(sport)),
        'bookmakers': BOOKMAKERS,
        'oddsFormat': 'american',
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch odds for event {event_id}: {response.text}")
        return None, {}

    usage = {
        'used': response.headers.get('x-requests-used'),
        'remaining': response.headers.get('x-requests-remaining'),
    }
    return response.json(), usage


def collect_player_lines(market):
    """Group a market's outcomes into {player: {line: {'Over': odds, 'Under': odds}}}."""
    players = {}
    for outcome in market.get('outcomes', []):
        name = outcome.get('description', 'Unknown')
        line = outcome.get('point')
        if line is None:
            continue
        players.setdefault(name, {}).setdefault(line, {})[outcome['name']] = outcome['price']
    return players


def book_margin_for_player(main_lines):
    """Two-way vig measured from a book's main line, used to de-vig one-sided alternates."""
    for prices in main_lines.values():
        if 'Over' in prices and 'Under' in prices:
            return implied_prob(prices['Over']) + implied_prob(prices['Under']) - 1
    return 0.045


def flatten_game(game, game_odds, sport: dict):
    records = []
    game_label = f"{game['away_team']} @ {game['home_team']}"
    commence_time = game.get('commence_time')

    for bookmaker in game_odds.get('bookmakers', []):
        book_key = bookmaker['key']

        # Merge each base stat's main + alternate markets into one ladder.
        by_stat: dict[str, dict] = {}
        for market in bookmaker.get('markets', []):
            binary_config = sport.get('binary_markets', {}).get(market['key'])
            if binary_config:
                records.extend(flatten_binary_market(
                    market, binary_config, game_label, commence_time, book_key,
                ))
                continue
            stat = base_stat_for_market(market['key'], sport)
            grouped = collect_player_lines(market)
            stat_players = by_stat.setdefault(stat, {})
            for player, lines in grouped.items():
                merged = stat_players.setdefault(player, {})
                for line, prices in lines.items():
                    merged.setdefault(line, {}).update(prices)

        milestones = sport.get('integer_lines_are_milestones', False)
        for stat, players in by_stat.items():
            for player, lines in players.items():
                margin = book_margin_for_player(lines)
                for line, prices in lines.items():
                    if milestones and float(line) == int(line):
                        line = float(line) - 0.5  # "Over 2" means 2+, i.e. X > 1.5
                    price_over = prices.get('Over')
                    price_under = prices.get('Under')
                    method = shin_z = hold = None
                    if 'Over' in prices and 'Under' in prices:
                        dv = devig_two_sided(prices['Over'], prices['Under'], DEFAULT_DEVIG_METHOD)
                        tp_over, tp_under = dv['p_over'], dv['p_under']
                        method, shin_z, hold = dv['devig_method'], dv['z'], dv['hold']
                    elif 'Over' in prices:
                        tp_over = devig_one_sided(prices['Over'], margin)
                        tp_under = 1 - tp_over
                        method = 'one_sided'
                    elif 'Under' in prices:
                        tp_under = devig_one_sided(prices['Under'], margin)
                        tp_over = 1 - tp_under
                        method = 'one_sided'
                    else:
                        continue

                    records.append({
                        'Player': player,
                        'Game': game_label,
                        'Stat': stat,
                        'Line': line,
                        'Bookmaker': book_key,
                        'Commence_Time': commence_time,
                        'True_Over_Prob': round(tp_over * 100, 2),
                        'True_Under_Prob': round(tp_under * 100, 2),
                        'Price_Over': price_over,
                        'Price_Under': price_under,
                        'Devig_Method': method,
                        'Shin_Z': round(shin_z, 4) if shin_z is not None else None,
                        'Hold': round(hold, 4) if hold is not None else None,
                    })

    return records


def main():
    if not API_KEY:
        raise SystemExit("Missing ODDS_API_KEY. Add it to your .env file.")

    sport = get_sport()
    events = fetch_events(sport)
    upcoming = filter_upcoming(events, sport)
    print(f"{len(events)} games on the feed; {len(upcoming)} inside the kickoff window.")
    print(f"Markets: {', '.join(market_list(sport))}")
    print(f"Books: {BOOKMAKERS}\n")

    all_records = []
    usage = {}

    for game in upcoming:
        print(f"Fetching props: {game['away_team']} @ {game['home_team']} ({game['commence_time']})...")
        game_odds, usage = fetch_event_odds(game['id'], sport)
        if not game_odds:
            continue
        all_records.extend(flatten_game(game, game_odds, sport))
        time.sleep(0.5)

    books_seen = sorted({record['Bookmaker'] for record in all_records})
    players_seen = {record['Player'] for record in all_records}
    print(f"\nMapped {len(all_records)} lines across {len(players_seen)} players "
          f"from {len(books_seen)} book(s): {', '.join(books_seen) or 'none'}")
    if usage.get('remaining') is not None:
        print(f"Odds-API credits — used: {usage['used']}, remaining: {usage['remaining']}")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_FILE.open('w') as file:
        json.dump(all_records, file, indent=4)
    print(f"Saved sharp board to {OUTPUT_FILE}")


if __name__ == '__main__':
    main()
