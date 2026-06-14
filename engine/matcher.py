"""Edge detection: price every PrizePicks line against sharp-book consensus.

For each PP prop, every sharp book's line ladder is converted into
P(over PP line). The consensus probability drives a simple verdict:

    YES  — true win probability >= 57% and no trap flags
    LEAN — beats the 54.25% flex break-even, or strong but flagged
    NO   — below break-even (not logged)

Trap flags catch the classic PrizePicks failure mode: a "great" line gap
that is actually the sharp books pricing in news PP hasn't reacted to.
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.name_matcher import match_player_name
from engine.probability import (
    BREAKEVEN_PROB,
    assign_verdict,
    best_slips,
    consensus_probability,
    ev_percent,
    fit_lambda_from_anchor,
    poisson_p_over_push_adjusted,
    prob_over_at_line,
)
from engine.projections import load_fbref_stats, model_stat_types, project_prop
from engine.sports import get_sport
from scrapers.injuries_api import get_injury_map, injury_status, is_risky_status
from storage.db_manager import (
    get_game_commence_map,
    get_latest_props,
    get_sharp_ladders,
    ingest_staging,
    log_edges,
)

STALE_GAP_MINUTES = 45      # PP capture older than sharp capture by this much
BOOK_DISAGREEMENT = 0.07    # max spread in P(over) between books
LARGE_LINE_GAP = 2.5        # PP vs closest sharp line, in points


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def build_trap_flags(
    pp_player: dict,
    sharp_captured_at: str | None,
    line_gap: float,
    spread: float,
    injury: str | None,
) -> list[str]:
    flags = []

    pp_ts = _parse_ts(pp_player.get('captured_at'))
    sharp_ts = _parse_ts(sharp_captured_at)
    if pp_ts and sharp_ts and (sharp_ts - pp_ts).total_seconds() > STALE_GAP_MINUTES * 60:
        flags.append('PP board may be stale vs sharp data — re-paste PP JSON')

    if spread > BOOK_DISAGREEMENT:
        flags.append(f'Books disagree by {spread * 100:.0f}% — market unsettled')

    if abs(line_gap) >= LARGE_LINE_GAP:
        flags.append(f'Line gap of {abs(line_gap):.1f} pts — check for breaking news')

    if is_risky_status(injury):
        flags.append(f'Injury report: {injury}')

    return flags


def evaluate_player(
    pp_player: dict,
    books: dict[str, dict],
    injury_map: dict,
    model: str = 'normal',
    rate_scale: float = 1.0,
    extra_flags: list[str] | None = None,
) -> dict | None:
    pp_line = pp_player['line']

    book_probs: dict[str, float] = {}
    latest_capture = None
    commence_time = None
    for book, entry in books.items():
        p_over = prob_over_at_line(entry['points'], pp_line, model, rate_scale)
        if p_over is None:
            continue
        book_probs[book] = p_over
        if latest_capture is None or entry['captured_at'] > latest_capture:
            latest_capture = entry['captured_at']
        commence_time = commence_time or entry.get('commence_time')

    if not book_probs:
        return None

    consensus_over, spread = consensus_probability(book_probs)
    play = 'OVER' if consensus_over >= 0.5 else 'UNDER'
    win_prob = consensus_over if play == 'OVER' else 1 - consensus_over

    # Anchor line for display/CLV: DraftKings' closest line, else first book's.
    anchor_book = 'draftkings' if 'draftkings' in books else next(iter(books))
    anchor_line = min(
        (line for line, _ in books[anchor_book]['points']),
        key=lambda line: abs(line - pp_line),
    )
    line_gap = anchor_line - pp_line
    if rate_scale != 1.0:
        edge_type = 'Duration Model'
        line_gap = 0.0  # anchor is a full-match line; gap flags don't apply
    else:
        edge_type = 'Line Discrepancy' if abs(line_gap) > 1e-9 else '+EV Odds Juice'

    injury = injury_status(pp_player['player_name'], injury_map)
    flags = build_trap_flags(pp_player, latest_capture, line_gap, spread, injury)
    if extra_flags:
        flags = extra_flags + flags
    verdict = assign_verdict(win_prob, flags)

    return {
        'play': play,
        'win_prob': round(win_prob, 4),
        'ev_percent': ev_percent(win_prob),
        'verdict': verdict,
        'flags': flags,
        'book_count': len(book_probs),
        'consensus_over': consensus_over,
        'spread': spread,
        'anchor_line': anchor_line,
        'edge_type': edge_type,
        'sharp_captured_at': latest_capture,
        'commence_time': commence_time,
    }


def evaluate_combo(
    pp_player: dict,
    ladders: dict[str, dict],
    rate_scale: float,
    extra_flags: list[str],
) -> tuple[dict, str, float] | None:
    """Price a combo prop ("A + B") as the sum of independent Poisson legs.

    Returns (evaluation, joined sharp names, worst match score) or None.
    """
    pp_line = pp_player['line']
    legs = [name.strip() for name in pp_player['player_name'].split(' + ')]
    sharp_names = list(ladders.keys())

    matched_legs = []
    worst_score = 1.0
    for leg in legs:
        sharp_name, score = match_player_name(leg, sharp_names)
        if not sharp_name:
            return None
        matched_legs.append(sharp_name)
        worst_score = min(worst_score, score)

    # A book can price the combo only if it quotes every leg.
    common_books = set(ladders[matched_legs[0]].keys())
    for leg_name in matched_legs[1:]:
        common_books &= set(ladders[leg_name].keys())
    if not common_books:
        return None

    per_leg_target = pp_line / len(legs)
    book_probs: dict[str, float] = {}
    latest_capture = None
    commence_time = None
    anchor_total = 0.0

    for book in common_books:
        lam_total = 0.0
        for leg_name in matched_legs:
            entry = ladders[leg_name][book]
            points = entry['points']
            anchor_line, anchor_prob = min(
                points, key=lambda pt: abs(pt[0] - per_leg_target)
            )
            lam_total += fit_lambda_from_anchor(anchor_line, anchor_prob)
            if latest_capture is None or entry['captured_at'] > latest_capture:
                latest_capture = entry['captured_at']
            commence_time = commence_time or entry.get('commence_time')
        book_probs[book] = poisson_p_over_push_adjusted(lam_total * rate_scale, pp_line)
        anchor_total = lam_total  # last book's rate as display anchor

    consensus_over, spread = consensus_probability(book_probs)
    play = 'OVER' if consensus_over >= 0.5 else 'UNDER'
    win_prob = consensus_over if play == 'OVER' else 1 - consensus_over

    flags = list(extra_flags)
    flags.append('Combo: correlation between legs not modeled')
    if spread > BOOK_DISAGREEMENT:
        flags.append(f'Books disagree by {spread * 100:.0f}% — market unsettled')

    evaluation = {
        'play': play,
        'win_prob': round(win_prob, 4),
        'ev_percent': ev_percent(win_prob),
        'verdict': assign_verdict(win_prob, flags),
        'flags': flags,
        'book_count': len(book_probs),
        'consensus_over': consensus_over,
        'spread': spread,
        'anchor_line': round(anchor_total * rate_scale, 2),  # modeled combined rate
        'edge_type': 'Combo Model',
        'sharp_captured_at': latest_capture,
        'commence_time': commence_time,
    }
    return evaluation, ' + '.join(matched_legs), worst_score


def _resolve_kickoff(team: str | None, games: list[dict]) -> tuple[str | None, str | None]:
    """Find the DK game whose 'Away @ Home' string names this team."""
    if not team:
        return None, None
    needle = team.strip().lower()
    for game in games:
        for side in game['game'].split('@'):
            side = side.strip().lower()
            if side and (side in needle or needle in side):
                return game['commence_time'], game['game']
    return None, None


def price_model_edges(sport: dict, flagged_bets: list[dict]) -> bool:
    """Price PP stats the books don't post against each player's World Cup form.

    Appends qualifying plays to flagged_bets. Returns True if any model stat had
    PP props to price (so the caller knows pricing happened).
    """
    model_stats = [s for s in model_stat_types() if s in sport['stat_models']]
    players = load_fbref_stats() if model_stats else []
    if not players:
        return False

    games = get_game_commence_map()
    priced = False

    for stat_type in model_stats:
        pp_data = get_latest_props('PP', stat_type)
        if not pp_data:
            continue
        priced = True
        modeled = 0

        for pp_player in pp_data:
            pp_name = pp_player['player_name']
            if ' + ' in pp_name:
                continue  # combos not modeled for form-based stats yet
            proj = project_prop(pp_name, stat_type, pp_player['line'], players)
            if not proj or proj['win_prob'] < BREAKEVEN_PROB:
                continue

            kickoff, _ = _resolve_kickoff(pp_player.get('team') or proj.get('team'), games)
            flagged_bets.append({
                'Player': pp_name,
                'DK_Player': proj['matched_name'],
                'Match_Score': proj['match_score'],
                'Team': pp_player['team'],
                'Stat': stat_type,
                'Play': proj['play'],
                'PP_Line': pp_player['line'],
                'DK_Line': proj['expected'],
                'Probability': f"{proj['win_prob'] * 100:.1f}% true win",
                'Edge_Type': 'Form Model',
                'pp_player_name': pp_name,
                'dk_player_name': proj['matched_name'],
                'team': pp_player['team'],
                'stat_type': stat_type,
                'play': proj['play'],
                'pp_line': pp_player['line'],
                'dk_line_at_flag': proj['expected'],
                'edge_type': 'Form Model',
                'dk_over_prob': round(proj['win_prob'] * 100, 2)
                if proj['play'] == 'OVER' else round((1 - proj['win_prob']) * 100, 2),
                'dk_under_prob': round((1 - proj['win_prob']) * 100, 2)
                if proj['play'] == 'OVER' else round(proj['win_prob'] * 100, 2),
                'probability_text': (
                    f"{proj['win_prob'] * 100:.1f}% true "
                    f"(modeled from {proj['games']} game(s))"
                ),
                'win_prob': proj['win_prob'],
                'ev_percent': proj['ev_percent'],
                'verdict': proj['verdict'],
                'flags': ' | '.join(proj['flags']) or None,
                'book_count': None,
                'commence_time': kickoff,
                'pp_captured_at': pp_player.get('captured_at'),
                'dk_captured_at': None,
            })
            modeled += 1

        if modeled:
            print(f"Modeled {modeled} {stat_type.replace('player_', '')} play(s) "
                  "from World Cup form.")

    return priced


def find_edges(sync_staging: bool = True):
    if sync_staging:
        try:
            ingest_results = ingest_staging()
            if ingest_results:
                print(f"Synced staging JSON to SQLite: {ingest_results}")
        except FileNotFoundError as error:
            print(f"Warning: {error}")

    sport = get_sport()
    injury_map = get_injury_map() if sport['has_injury_feed'] else {}
    flagged_bets = []
    unmatched = []
    priced_any = False

    derived_stats = sport.get('derived_stats', {})

    for stat_type, model in sport['stat_models'].items():
        pp_data = get_latest_props('PP', stat_type)
        if not pp_data:
            continue

        # Derived stats (e.g. 1H shots) price against the BASE stat's
        # full-match ladder with a thinned Poisson rate, and are always
        # flagged so the verdict caps at LEAN.
        derived = derived_stats.get(stat_type)
        rate_scale = 1.0
        extra_flags: list[str] = []
        ladder_stat = stat_type
        if derived:
            ladder_stat = derived['base']
            rate_scale = derived['rate_share']
            extra_flags = [
                f"Modeled from full-match prices (rate x {rate_scale}) — no 1H market exists"
            ]

        ladders = get_sharp_ladders(ladder_stat)
        if not ladders:
            continue
        priced_any = True

        sharp_names = list(ladders.keys())
        print(f"Pricing {len(pp_data)} PrizePicks {stat_type} lines against "
              f"{len(sharp_names)} players of sharp consensus ({model} model"
              + (f", rate x {rate_scale}" if derived else "") + ")...")

        for pp_player in pp_data:
            pp_name = pp_player['player_name']
            pp_line = pp_player['line']

            if ' + ' in pp_name:
                if model != 'poisson':
                    continue  # combo summing implemented for count stats only
                combo = evaluate_combo(pp_player, ladders, rate_scale, extra_flags)
                if not combo:
                    unmatched.append(pp_name)
                    continue
                evaluation, sharp_name, match_score = combo
            else:
                sharp_name, match_score = match_player_name(pp_name, sharp_names)
                if not sharp_name:
                    unmatched.append(pp_name)
                    continue
                evaluation = evaluate_player(
                    pp_player, ladders[sharp_name], injury_map, model,
                    rate_scale, extra_flags,
                )

            if not evaluation or evaluation['win_prob'] < BREAKEVEN_PROB:
                continue

            flagged_bets.append({
                # Display keys (dashboard/CSV compatibility)
                'Player': pp_name,
                'DK_Player': sharp_name,
                'Match_Score': match_score,
                'Team': pp_player['team'],
                'Stat': pp_player['stat_type'],
                'Play': evaluation['play'],
                'PP_Line': pp_line,
                'DK_Line': evaluation['anchor_line'],
                'Probability': f"{evaluation['win_prob'] * 100:.1f}% true win",
                'Edge_Type': evaluation['edge_type'],
                # Storage keys
                'pp_player_name': pp_name,
                'dk_player_name': sharp_name,
                'team': pp_player['team'],
                'stat_type': pp_player['stat_type'],
                'play': evaluation['play'],
                'pp_line': pp_line,
                'dk_line_at_flag': evaluation['anchor_line'],
                'edge_type': evaluation['edge_type'],
                'dk_over_prob': round(evaluation['consensus_over'] * 100, 2),
                'dk_under_prob': round((1 - evaluation['consensus_over']) * 100, 2),
                'probability_text': (
                    f"{evaluation['win_prob'] * 100:.1f}% true "
                    f"({evaluation['book_count']} book(s))"
                ),
                'win_prob': evaluation['win_prob'],
                'ev_percent': evaluation['ev_percent'],
                'verdict': evaluation['verdict'],
                'flags': ' | '.join(evaluation['flags']) or None,
                'book_count': evaluation['book_count'],
                'commence_time': evaluation['commence_time'],
                'pp_captured_at': pp_player.get('captured_at'),
                'dk_captured_at': evaluation['sharp_captured_at'],
            })

    # --- Model-priced stats (no book market): project from World Cup form ---
    if price_model_edges(sport, flagged_bets):
        priced_any = True

    if not priced_any:
        print("Make sure both sharp and PP props exist in the database.")
        print("Run scrapers, then: python3 storage/db_manager.py ingest")
        return []
    print()

    if unmatched:
        print(f"Skipped {len(unmatched)} PP players with no sharp-book match.")

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
        print("No plays beat the 54.25% break-even tonight. Best action is no action.")
        return []

    flagged_bets.sort(key=lambda bet: bet['win_prob'], reverse=True)

    logged = log_edges(flagged_bets)
    print(f"Logged {logged} edge(s) to SQLite.\n")

    print_verdict_board(flagged_bets)
    print_slip_suggestions(flagged_bets)

    return flagged_bets


def print_verdict_board(flagged_bets: list[dict]) -> None:
    print(f"Verdict Board — {len(flagged_bets)} play(s) above break-even:")
    print("-" * 132)
    print(
        f"{'VERDICT'.ljust(7)} | {'PLAYER'.ljust(24)} | {'STAT'.ljust(22)} | "
        f"{'PLAY'.ljust(5)} | {'PP'.ljust(5)} | {'SHARP'.ljust(5)} | "
        f"{'WIN%'.ljust(5)} | {'EV'.ljust(6)} | {'BOOKS'.ljust(5)} | FLAGS"
    )
    print("-" * 132)
    for bet in flagged_bets:
        print(
            f"{bet['verdict'].ljust(7)} | {bet['Player'].ljust(24)} | "
            f"{bet['stat_type'].replace('player_', '').ljust(22)} | "
            f"{bet['Play'].ljust(5)} | {str(bet['PP_Line']).ljust(5)} | "
            f"{str(bet['DK_Line']).ljust(5)} | {bet['win_prob'] * 100:5.1f} | "
            f"{bet['ev_percent']:+5.1f}% | {str(bet['book_count']).ljust(5)} | "
            f"{bet['flags'] or '-'}"
        )
    print("-" * 132)


def print_slip_suggestions(flagged_bets: list[dict]) -> None:
    # One leg per player (PP disallows duplicate players on a slip);
    # keep each player's strongest stat.
    seen_players = set()
    yes_picks = []
    for bet in flagged_bets:
        if bet['verdict'] != 'YES' or bet['Player'] in seen_players:
            continue
        seen_players.add(bet['Player'])
        stat_label = bet['stat_type'].replace('player_', '')
        yes_picks.append({
            'player': f"{bet['Player']} {bet['Play'].lower()} {bet['PP_Line']} {stat_label}",
            'team': bet['Team'],
            'win_prob': bet['win_prob'],
        })
    if len(yes_picks) < 2:
        print("\nFewer than 2 YES plays — no slip recommendation tonight.")
        return

    suggestions = best_slips(yes_picks)
    if not suggestions:
        return

    print("\nBest slips (independence assumed; correlated = same-team legs):")
    for suggestion in suggestions[:3]:
        corr = '  [same-team legs!]' if suggestion['correlated_teams'] else ''
        print(
            f"  {suggestion['structure'].ljust(13)} EV {suggestion['ev_percent']:+.1f}%  "
            f"stake {suggestion.get('kelly_pct', 0):.1f}% bankroll  "
            f"{', '.join(suggestion['players'])}{corr}"
        )


if __name__ == '__main__':
    find_edges()
