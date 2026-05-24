import json

# 1. Load the flat clean list from your local file
try:
    with open('game_data.json', 'r') as f:
        clean_picks = json.load(f)
except FileNotFoundError:
    print("Error: Could not find game_data.json. Run math_engine.py first to create it.")
    exit()

# 2. Sort to show the highest probability props first (Over or Under)
sorted_odds = sorted(clean_picks, key=lambda x: max(x['True_Over_Prob'], x['True_Under_Prob']), reverse=True)

# 3. Print the results out beautifully
print("--- DRAFTKINGS TRUE PROBABILITIES (ALL GAMES COMBINED) ---")
for line in sorted_odds:
    # Use fallback .get() for 'Stat' in case you haven't rerun math_engine yet
    stat_name = line.get('Stat', 'player_points') 
    
    print(f"{line['Player'].ljust(25)} | Stat: {stat_name.ljust(15)} | Line: {str(line['Line']).ljust(4)} | Over: {str(line['True_Over_Prob']).ljust(5)}% | Under: {str(line['True_Under_Prob']).ljust(5)}% |    Team: {line['Game'].ljust(25)}" )