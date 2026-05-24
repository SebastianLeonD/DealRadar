import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db_manager import get_latest_props, ingest_staging

TARGET_STAT = 'player_points'
EV_THRESHOLD = 54.25  # The PrizePicks break-even point for a 5/6-slip


def build_sharp_map(sharp_data):
    sharp_map = {}
    for player in sharp_data:
        sharp_map.setdefault(player['player_name'], []).append(player)
    return sharp_map


def pick_closest_line(player_lines, pp_line):
    return min(player_lines, key=lambda player: abs(player['line'] - pp_line))


def find_edges(sync_staging: bool = True):
    if sync_staging:
        try:
            ingest_results = ingest_staging()
            if ingest_results:
                print(f"Synced staging JSON to SQLite: {ingest_results}")
        except FileNotFoundError as error:
            print(f"Warning: {error}")

    pp_data = get_latest_props('PP', TARGET_STAT)
    sharp_data = get_latest_props('DK', TARGET_STAT)

    if not pp_data or not sharp_data:
        print("Make sure both DK and PP props exist in the database.")
        print("Run scrapers, then: python3 storage/db_manager.py ingest")
        return

    sharp_map = build_sharp_map(sharp_data)

    if not pp_data:
        print(f"No PrizePicks lines found for stat type '{TARGET_STAT}'.")
        return

    flagged_bets = []

    print(f"Scanning {len(pp_data)} PrizePicks {TARGET_STAT} lines against sharp lines...\n")

    for pp_player in pp_data:
        name = pp_player['player_name']
        pp_line = pp_player['line']
        pp_stat = pp_player['stat_type']
        pp_team = pp_player['team']

        if name not in sharp_map:
            continue

        sharp_player = pick_closest_line(sharp_map[name], pp_line)
        dk_line = sharp_player['line']
        dk_over_prob = sharp_player['true_over_prob']
        dk_under_prob = sharp_player['true_under_prob']

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
