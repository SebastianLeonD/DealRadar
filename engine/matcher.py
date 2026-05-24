import json

PRIZEPICKS_FILE = 'data/processed/prizepicks_mock.json'
SHARP_FILE = 'data/processed/draftkings_data.json'
TARGET_STAT = 'player_points'
EV_THRESHOLD = 54.25  # The PrizePicks break-even point for a 5/6-slip

def load_json_file(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Could not find {filename}")
        return None

def is_target_stat(record, stat_key, target_stat):
    stat_value = record.get(stat_key, target_stat)
    return stat_value == target_stat

def build_sharp_map(sharp_data):
    sharp_map = {}
    for player in sharp_data:
        if not is_target_stat(player, 'Stat', TARGET_STAT):
            continue
        sharp_map.setdefault(player['Player'], []).append(player)
    return sharp_map

def pick_closest_line(player_lines, pp_line):
    return min(player_lines, key=lambda player: abs(player['Line'] - pp_line))

def find_edges():
    pp_data = load_json_file(PRIZEPICKS_FILE)
    sharp_data = load_json_file(SHARP_FILE)
    
    if not pp_data or not sharp_data:
        print("Make sure both JSON files exist and have data.")
        return

    pp_data = [p for p in pp_data if is_target_stat(p, 'stat_type', TARGET_STAT)]
    sharp_map = build_sharp_map(sharp_data)

    if not pp_data:
        print(f"No PrizePicks lines found for stat type '{TARGET_STAT}'.")
        return
    
    flagged_bets = []

    print(f"Scanning {len(pp_data)} PrizePicks {TARGET_STAT} lines against sharp lines...\n")

    for pp_player in pp_data:
        name = pp_player['name']
        pp_line = pp_player['line']
        pp_stat = pp_player['stat_type']
        pp_team = pp_player['team']

        # 1. Check if the player exists in our DraftKings data
        if name not in sharp_map:
            continue
            
        sharp_player = pick_closest_line(sharp_map[name], pp_line)
        dk_line = sharp_player['Line']
        dk_over_prob = sharp_player['True_Over_Prob']
        dk_under_prob = sharp_player['True_Under_Prob']

        # 2. Logic Tier A: Check for Line Discrepancies (Free Value)
        if pp_line < dk_line:
            flagged_bets.append({
                'Player': name,
                'Team': pp_team,
                'Stat': pp_stat,
                'Play': 'OVER',
                'PP_Line': pp_line,
                'DK_Line': dk_line,
                'Probability': f"Line Value (DK Line is {dk_line})",
                'Edge_Type': 'Line Discrepancy'
            })
        elif pp_line > dk_line:
            flagged_bets.append({
                'Player': name,
                'Team': pp_team,
                'Stat': pp_stat,
                'Play': 'UNDER',
                'PP_Line': pp_line,
                'DK_Line': dk_line,
                'Probability': f"Line Value (DK Line is {dk_line})",
                'Edge_Type': 'Line Discrepancy'
            })
            
        # 3. Logic Tier B: Identical Lines, Check Odds Juice (+EV)
        elif pp_line == dk_line:
            if dk_over_prob >= EV_THRESHOLD:
                flagged_bets.append({
                    'Player': name,
                    'Team': pp_team,
                    'Stat': pp_stat,
                    'Play': 'OVER',
                    'PP_Line': pp_line,
                    'DK_Line': dk_line,
                    'Probability': f"{dk_over_prob}%",
                    'Edge_Type': '+EV Odds Juice'
                })
            elif dk_under_prob >= EV_THRESHOLD:
                flagged_bets.append({
                    'Player': name,
                    'Team': pp_team,
                    'Stat': pp_stat,
                    'Play': 'UNDER',
                    'PP_Line': pp_line,
                    'DK_Line': dk_line,
                    'Probability': f"{dk_under_prob}%",
                    'Edge_Type': '+EV Odds Juice'
                })

    # Display the results
    if not flagged_bets:
        print("No profitable mathematical edges found on the board.")
        return

    print(f"Found {len(flagged_bets)} Advantageous Plays:")
    print("-" * 110)
    print(f"{'PLAYER'.ljust(25)} | {'PLAY'.ljust(6)} | {'PP LINE'.ljust(7)} | {'DK LINE'.ljust(7)} | {'PROBABILITY/EDGE'.ljust(22)} | {'TYPE'} | {'TEAM'.ljust(18)}")
    print("-" * 110)
    
    for bet in flagged_bets:
        print(f"{bet['Player'].ljust(25)} | {bet['Play'].ljust(6)} | {str(bet['PP_Line']).ljust(7)} | {str(bet['DK_Line']).ljust(7)} | {bet['Probability'].ljust(22)} | {bet['Edge_Type']} | {bet['Team'].ljust(18)} ")

if __name__ == "__main__":
    find_edges()