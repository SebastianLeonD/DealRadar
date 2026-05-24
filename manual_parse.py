import json

# 1. Load the JSON file you saved
with open('data/raw/prizepicks_raw.json', 'r') as file:
    raw_data = json.load(file)

projections = raw_data.get('data', [])
included = raw_data.get('included', [])

# 2. Build a lookup dictionary for players
player_dict = {}
for item in included:
    if item.get('type') == 'new_player':
        player_dict[item['id']] = item['attributes']['name']

# 3. Map the props to the players
clean_picks = []
for prop in projections:
    attrs = prop['attributes']
    
    # Safely extract the player ID
    try:
        player_id = prop['relationships']['new_player']['data']['id']
    except KeyError:
        continue
        
    pick = {
        "Player": player_dict.get(player_id, "Unknown"),
        "Stat": attrs.get('stat_type'),
        "Line": attrs.get('line_score'),
        "Type": attrs.get('odds_type') # standard, demon, or goblin
    }
    clean_picks.append(pick)

# 4. Output the results
print(f"Successfully mapped {len(clean_picks)} props.")
for pick in clean_picks[:100]:
    print(pick)