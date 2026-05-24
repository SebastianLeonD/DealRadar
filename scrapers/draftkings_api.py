
import requests
import time
import json

API_KEY = '474da336ad8ac132c8a791c2ba23b1db'
SPORT = 'basketball_nba' 
MARKET = 'player_points' 
BOOKMAKER = 'draftkings' 

# 1. The De-Vigging Math Formula
def calculate_true_probability(over_odds, under_odds):
    def implied_prob(odds):
        if odds < 0:
            return abs(odds) / (abs(odds) + 100)
        else:
            return 100 / (odds + 100)
            
    ip_over = implied_prob(over_odds)
    ip_under = implied_prob(under_odds)
    
    total_implied = ip_over + ip_under
    tp_over = ip_over / total_implied
    tp_under = ip_under / total_implied
    
    return tp_over, tp_under

# 2. Step One: Get Today's Games (Costs 0 API Credits)
def fetch_events():
    print(f"Fetching today's {SPORT} games...")
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events"
    params = {'apiKey': API_KEY}
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch events: {response.text}")
        return []
    return response.json()

# 3. Step Two: Get Player Props for a Specific Game (Costs 1 API Credit per game)
def fetch_event_odds(event_id):
    url = f"https://api.the-odds-api.com/v4/sports/{SPORT}/events/{event_id}/odds"
    params = {
        'apiKey': API_KEY,
        'regions': 'us',
        'markets': MARKET,
        'bookmakers': BOOKMAKER,
        'oddsFormat': 'american'
    }
    
    response = requests.get(url, params=params)
    if response.status_code != 200:
        print(f"Failed to fetch odds for event {event_id}: {response.text}")
        return None

    return response.json()

# 4. Run the Pipeline
if __name__ == "__main__":
    games = fetch_events()
    print(f"Found {len(games)} upcoming games.\n")
    
    all_true_odds = []
    
    for game in games:
        print(f"Fetching player points for: {game['home_team']} vs {game['away_team']}...")
        game_odds = fetch_event_odds(game['id'])
        
        if not game_odds or 'bookmakers' not in game_odds:
            continue
            
        for bookmaker in game_odds['bookmakers']:
            for market in bookmaker.get('markets', []):
                
                player_lines = {}
                for outcome in market.get('outcomes', []):
                    name = outcome.get('description', 'Unknown')
                    prop_type = outcome['name'] 
                    odds = outcome['price']
                    line = outcome.get('point')
                    
                    if name not in player_lines:
                        player_lines[name] = {'line': line}
                    player_lines[name][prop_type] = odds

                for player, data in player_lines.items():
                    if 'Over' in data and 'Under' in data:
                        tp_over, tp_under = calculate_true_probability(data['Over'], data['Under'])
                        
                        all_true_odds.append({
                            'Player': player,
                            'Game': f"{game['away_team']} @ {game['home_team']}",
                            'Stat': market['key'], 
                            'Line': data['line'],
                            'True_Over_Prob': round(tp_over * 100, 2),
                            'True_Under_Prob': round(tp_under * 100, 2)
                        })
        
        # Sleep for a fraction of a second to avoid rate-limiting
        time.sleep(0.5)
        
    print(f"\nSuccessfully mapped {len(all_true_odds)} sharp lines.")
    
    # 🌟 Save the complete data to your local file
    with open("data/processed/draftkings_data.json", "w") as file:
        json.dump(all_true_odds, file, indent=4)
    print("Saved all combined games to data/processed/draftkings_data.json!")
    
    # Sort to show the highest probability props first
    sorted_odds = sorted(all_true_odds, key=lambda x: max(x['True_Over_Prob'], x['True_Under_Prob']), reverse=True)
    
    print("\nTop 5 Highest Probability Props Tonight:")
    for line in sorted_odds[:5]:
        print(line)