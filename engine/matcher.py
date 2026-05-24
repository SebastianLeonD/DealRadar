import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.name_matcher import match_player_name
from storage.db_manager import get_latest_props, ingest_staging, log_edges

TARGET_STAT = 'player_points'
EV_THRESHOLD = 54.25  # The PrizePicks break-even point for a 5/6-slip


def build_sharp_map(sharp_data):
    sharp_map = {}
    for player in sharp_data:
        sharp_map.setdefault(player['player_name'], []).append(player)
    return sharp_map


def pick_closest_line(player_lines, pp_line):
    return min(player_lines, key=lambda player: abs(player['line'] - pp_line))


def evaluate_edge(pp_line, dk_line, dk_over_prob, dk_under_prob):
    if pp_line < dk_line:
        return {
            'Play': 'OVER',
            'Probability': f"Line Value (DK Line is {dk_line})",
            'Edge_Type': 'Line Discrepancy',
        }
    if pp_line > dk_line:
        return {
            'Play': 'UNDER',
            'Probability': f"Line Value (DK Line is {dk_line})",
            'Edge_Type': 'Line Discrepancy',
        }
    if dk_over_prob >= EV_THRESHOLD:
        return {
            'Play': 'OVER',
            'Probability': f"{dk_over_prob}%",
            'Edge_Type': '+EV Odds Juice',
        }
    if dk_under_prob >= EV_THRESHOLD:
        return {
            'Play': 'UNDER',
            'Probability': f"{dk_under_prob}%",
            'Edge_Type': '+EV Odds Juice',
        }
    return None


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
        return []

    sharp_map = build_sharp_map(sharp_data)
    dk_names = list(sharp_map.keys())
    flagged_bets = []
    unmatched = []

    print(f"Scanning {len(pp_data)} PrizePicks {TARGET_STAT} lines against sharp lines...\n")

    for pp_player in pp_data:
        pp_name = pp_player['player_name']
        pp_line = pp_player['line']
        pp_stat = pp_player['stat_type']
        pp_team = pp_player['team']

        dk_name, match_score = match_player_name(pp_name, dk_names)
        if not dk_name:
            unmatched.append(pp_name)
            continue

        sharp_player = pick_closest_line(sharp_map[dk_name], pp_line)
        dk_line = sharp_player['line']
        dk_over_prob = sharp_player['true_over_prob']
        dk_under_prob = sharp_player['true_under_prob']

        edge = evaluate_edge(pp_line, dk_line, dk_over_prob, dk_under_prob)
        if not edge:
            continue

        flagged_bets.append({
            'Player': pp_name,
            'DK_Player': dk_name,
            'Match_Score': match_score,
            'Team': pp_team,
            'Stat': pp_stat,
            'Play': edge['Play'],
            'PP_Line': pp_line,
            'DK_Line': dk_line,
            'Probability': edge['Probability'],
            'Edge_Type': edge['Edge_Type'],
            'pp_player_name': pp_name,
            'dk_player_name': dk_name,
            'stat_type': pp_stat,
            'play': edge['Play'],
            'pp_line': pp_line,
            'dk_line_at_flag': dk_line,
            'edge_type': edge['Edge_Type'],
            'dk_over_prob': dk_over_prob,
            'dk_under_prob': dk_under_prob,
            'probability_text': edge['Probability'],
            'pp_captured_at': pp_player.get('captured_at'),
            'dk_captured_at': sharp_player.get('captured_at'),
        })

    if unmatched:
        print(f"Skipped {len(unmatched)} PP players with no DK name match.")

    fuzzy_matches = [
        bet for bet in flagged_bets
        if bet['pp_player_name'] != bet['dk_player_name']
    ]
    if fuzzy_matches:
        print(f"Fuzzy matched {len(fuzzy_matches)} player name(s):")
        for bet in fuzzy_matches:
            print(
                f"  {bet['pp_player_name']} -> {bet['dk_player_name']} "
                f"({bet['Match_Score']:.0%})"
            )
        print()

    if not flagged_bets:
        print("No profitable mathematical edges found on the board.")
        return []

    logged = log_edges(flagged_bets)
    print(f"Logged {logged} edge(s) to SQLite.\n")

    print(f"Found {len(flagged_bets)} Advantageous Plays:")
    print("-" * 110)
    print(f"{'PLAYER'.ljust(25)} | {'PLAY'.ljust(6)} | {'PP LINE'.ljust(7)} | {'DK LINE'.ljust(7)} | {'PROBABILITY/EDGE'.ljust(22)} | {'TYPE'} | {'TEAM'.ljust(18)}")
    print("-" * 110)

    for bet in flagged_bets:
        print(
            f"{bet['Player'].ljust(25)} | {bet['Play'].ljust(6)} | "
            f"{str(bet['PP_Line']).ljust(7)} | {str(bet['DK_Line']).ljust(7)} | "
            f"{bet['Probability'].ljust(22)} | {bet['Edge_Type']} | {bet['Team'].ljust(18)} "
        )

    return flagged_bets


if __name__ == '__main__':
    find_edges()
