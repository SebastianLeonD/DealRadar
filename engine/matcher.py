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
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.ai_analyst import analyze_play
from engine.calibration import line_band as calc_line_band
from engine.calibration import select_sharpest_book
from engine.consensus import line_matched_consensus
from engine.exposure import apply_exposure_caps
from engine.name_matcher import match_player_name
from engine.portfolio import construct_slips
from engine.probability import (
    BREAKEVEN_PROB,
    assign_verdict,
    ev_percent,
    fit_lambda_from_anchor,
    poisson_p_over_push_adjusted,
    prob_over_at_line,
    tiered_consensus,
)
from engine.config import snapshot_bucket as _snapshot_bucket
from engine.projections import load_fbref_stats, model_stat_types, project_prop
from engine.shadow_model import NULL_FIELDS, load_fbref_logs, model_eligible, model_fields
from engine.sports import active_sport_key, get_sport
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

# Pick'em apps, not sharp sportsbooks: usable to price stats the books ignore,
# but a play sourced ONLY from these is soft — flag it so the verdict caps at
# LEAN (no soft-only play is ever a confident YES).
SOFT_BOOKS = {"underdog"}
SOFT_ONLY_FLAG = "Priced off Underdog (a pick'em app, not a sharp book) — soft line"

# How much a soft pick'em line is allowed to pull the TRUTH estimate when a
# sharp book also prices the prop. 0 = sharp books decide the probability and
# Underdog is a venue/line-shop signal only. Bump this (e.g. 0.25) only with
# settled-bet evidence that the soft line adds predictive signal.
SOFT_BOOK_WEIGHT = 0.0


def _split_books(book_probs: dict[str, float]) -> tuple[dict, dict]:
    """Partition de-vigged book probabilities into sharp and soft tiers."""
    sharp = {b: p for b, p in book_probs.items() if b not in SOFT_BOOKS}
    soft = {b: p for b, p in book_probs.items() if b in SOFT_BOOKS}
    return sharp, soft


def _venue_comparison(play: str, pp_line: float, books: dict[str, dict]) -> tuple[str, str]:
    """Compare PP's line vs Underdog's for the same prop/side (Feature A).

    OVER: the lower line is softer. UNDER: the higher line is softer. Falls
    back to 'prizepicks' when Underdog doesn't quote this prop.
    """
    ud = books.get('underdog')
    if not ud or not ud.get('points'):
        return 'prizepicks', 'Only on PrizePicks'

    ud_line = min(ud['points'], key=lambda pt: abs(pt[0] - pp_line))[0]
    if ud_line == pp_line:
        return 'prizepicks', 'Same line both apps'

    underdog_softer = (ud_line < pp_line) if play == 'OVER' else (ud_line > pp_line)
    if underdog_softer:
        return 'underdog', f'Underdog line {ud_line} is softer than PP {pp_line} for the {play}'
    return 'prizepicks', f'PrizePicks line {pp_line} is softer than Underdog {ud_line} for the {play}'


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def _edge_game_date(commence_time: str | None, captured_at: str | None) -> str | None:
    """US game date (YYYY-MM-DD) for the cluster key, from kickoff or capture."""
    ts = _parse_ts(commence_time) or _parse_ts(captured_at)
    return ts.date().isoformat() if ts else None


def _edge_bucket(captured_at: str | None) -> str | None:
    """Snapshot bucket for OBJ-30 dedup; None when no capture timestamp exists."""
    if not captured_at:
        return None
    try:
        return _snapshot_bucket(captured_at)
    except (ValueError, TypeError):
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


def _drop_stale_books(books: dict[str, dict]) -> dict[str, dict]:
    """Drop a book's ladder if it's older than STALE_MAX_MINUTES vs the newest
    book for this player — contemporaneity between books, not wall-clock
    freshness (a matcher run an hour after fetching is normal usage)."""
    from engine.config import STALE_MAX_MINUTES

    timestamps = {book: _parse_ts(entry.get('captured_at')) for book, entry in books.items()}
    known = [ts for ts in timestamps.values() if ts is not None]
    if not known:
        return books
    newest = max(known)
    cutoff = newest - timedelta(minutes=STALE_MAX_MINUTES)
    return {
        book: entry for book, entry in books.items()
        if timestamps[book] is None or timestamps[book] >= cutoff
    }


def _drop_dead_books(books: dict[str, dict]) -> dict[str, dict]:
    """Drop a book's ladder if its game has already started.

    A stale player, absent from today's book fetch, keeps its last-known
    ladder rows in storage from a finished match — all equally "fresh"
    against each other, so _drop_stale_books (relative freshness) can't catch
    it. This checks wall-clock: commence_time in the past means the game is
    over/live and the ladder is dead, regardless of every book agreeing on it.
    """
    now = datetime.now(timezone.utc)
    kept = {}
    for book, entry in books.items():
        commence = _parse_ts(entry.get('commence_time'))
        # Intentional fail-open: a missing/unparseable commence_time keeps the
        # book rather than dropping it — we'd rather risk a stale ladder than
        # silently starve every player of coverage when the odds API omits
        # commence_time.
        if commence is not None and commence <= now:
            continue
        kept[book] = entry
    return kept


def evaluate_player(
    pp_player: dict,
    books: dict[str, dict],
    injury_map: dict,
    model: str = 'normal',
    rate_scale: float = 1.0,
    extra_flags: list[str] | None = None,
) -> dict | None:
    pp_line = pp_player['line']
    books = _drop_dead_books(books)
    books = _drop_stale_books(books)

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

    sharp_probs, soft_probs = _split_books(book_probs)
    consensus_over, spread = tiered_consensus(sharp_probs, soft_probs, SOFT_BOOK_WEIGHT)
    play = 'OVER' if consensus_over >= 0.5 else 'UNDER'
    win_prob = consensus_over if play == 'OVER' else 1 - consensus_over

    # IDENTIFIED line-matched consensus (council OBJ-1/3): only SHARP books
    # quoting the EXACT PP line contribute — a soft pick'em app (SOFT_BOOKS)
    # or a prizepicks row must never satisfy the >=2 count. The interpolated
    # win_prob above is shape-contingent; consensus_tag records whether an
    # identified (>=2 same-line sharp books) ground truth backs this edge or
    # it rests on the asserted shape.
    exact_line_probs = {
        book: p_over
        for book, entry in books.items()
        if book not in SOFT_BOOKS and book != 'prizepicks'
        for line, p_over in entry['points']
        if abs(line - pp_line) < 1e-9
    }
    # An incomplete DK/Odds-API fetch (budget cutoff or per-game failure —
    # scrapers/draftkings_api.py's fetch_complete flag, threaded through
    # storage.get_sharp_ladders as each book entry's 'fetch_complete') must
    # withhold the 'identified' tag even if 2+ books happen to be present: we
    # can't claim consensus over a slate we didn't fully fetch.
    budget_truncated = any(not entry.get('fetch_complete', True) for entry in books.values())
    cons = line_matched_consensus(exact_line_probs, budget_truncated=budget_truncated) if exact_line_probs else {
        'consensus_n': 0, 'consensus_tag': 'degraded',
    }

    # Cross-book line shopping (council Pillar 3): the book whose de-vigged prob
    # most favours the side we are playing becomes the comparison anchor.
    best_book = (max if play == 'OVER' else min)(book_probs, key=book_probs.get)

    # Phase-2 baseline (council OBJ-31): the single sharpest book's raw P(over)
    # at the exact PP line is the null the consensus must out-Brier OOS.
    sharp = select_sharpest_book(exact_line_probs) if exact_line_probs else None
    baseline_book, baseline_p = sharp if sharp else (None, None)

    # Books actually backing the probability: sharp tier when present (soft only
    # joins if it's weighted in), else the soft tier we fell back on.
    if sharp_probs:
        truth_books = {**sharp_probs, **soft_probs} if SOFT_BOOK_WEIGHT > 0 else sharp_probs
    else:
        truth_books = soft_probs

    # Anchor line for display/CLV: DraftKings', else any sharp book's, else
    # whatever we have — a soft line only when no sharp book quotes this prop.
    if 'draftkings' in books:
        anchor_book = 'draftkings'
    else:
        sharp_in_books = [b for b in books if b not in SOFT_BOOKS]
        anchor_book = sharp_in_books[0] if sharp_in_books else next(iter(books))
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
    if not sharp_probs:
        flags = [SOFT_ONLY_FLAG] + flags
    verdict = assign_verdict(win_prob, flags)

    # A YES must be earned by evidence, not just a high number (council
    # ratified): one sharp book at this exact line is a pricing artifact, not
    # a confirmed edge. Only >=2 sharp books quoting the exact PP line
    # ('identified') may back a YES; everything else caps at LEAN.
    if verdict == 'YES' and cons['consensus_tag'] != 'identified':
        verdict = 'LEAN'
        flags = flags + ['Only one sharp book at this line — need 2+ to confirm a YES']

    best_venue, venue_note = _venue_comparison(play, pp_line, books)

    return {
        'play': play,
        'win_prob': round(win_prob, 4),
        'ev_percent': ev_percent(win_prob),
        'verdict': verdict,
        'flags': flags,
        'book_count': len(truth_books),
        'consensus_over': consensus_over,
        'consensus_n': cons['consensus_n'],
        'consensus_tag': cons['consensus_tag'],
        'best_book': best_book,
        'best_venue': best_venue,
        'venue_note': venue_note,
        # Phase-2 canonical-event fields persisted at flag time.
        'consensus_p': round(consensus_over, 4),     # un-folded P(over)
        'win_prob_raw': round(win_prob, 4),          # asserted shape P(side)
        'baseline_p': round(baseline_p, 4) if baseline_p is not None else None,
        'baseline_book': baseline_book,
        'line_band': calc_line_band(pp_player['stat_type'], pp_line),
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

    # Same dead/stale-ladder hygiene as evaluate_player, applied per leg —
    # combos priced off a finished-game or stale book quote were slipping
    # through since these drops previously only ran in evaluate_player.
    leg_books = {
        leg_name: _drop_stale_books(_drop_dead_books(ladders[leg_name]))
        for leg_name in matched_legs
    }

    # A book can price the combo only if it quotes every leg.
    common_books = set(leg_books[matched_legs[0]])
    for leg_name in matched_legs[1:]:
        common_books &= set(leg_books[leg_name])
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
            entry = leg_books[leg_name][book]
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

    sharp_probs, soft_probs = _split_books(book_probs)
    consensus_over, spread = tiered_consensus(sharp_probs, soft_probs, SOFT_BOOK_WEIGHT)
    play = 'OVER' if consensus_over >= 0.5 else 'UNDER'
    win_prob = consensus_over if play == 'OVER' else 1 - consensus_over

    if sharp_probs:
        truth_books = {**sharp_probs, **soft_probs} if SOFT_BOOK_WEIGHT > 0 else sharp_probs
    else:
        truth_books = soft_probs

    flags = list(extra_flags)
    flags.append('Combo: correlation between legs not modeled')
    if spread > BOOK_DISAGREEMENT:
        flags.append(f'Books disagree by {spread * 100:.0f}% — market unsettled')
    if not sharp_probs:
        flags.append(SOFT_ONLY_FLAG)

    evaluation = {
        'play': play,
        'win_prob': round(win_prob, 4),
        'ev_percent': ev_percent(win_prob),
        'verdict': assign_verdict(win_prob, flags),
        'flags': flags,
        'book_count': len(truth_books),
        'consensus_over': consensus_over,
        'spread': spread,
        'anchor_line': round(anchor_total * rate_scale, 2),  # modeled combined rate
        'edge_type': 'Combo Model',
        'sharp_captured_at': latest_capture,
        'commence_time': commence_time,
    }
    return evaluation, ' + '.join(matched_legs), worst_score


def _resolve_kickoff(team: str | None, games: list[dict]) -> tuple[str | None, str | None]:
    """Find the DK game whose 'Away @ Home' string names this team.

    A team can appear in several games across a tournament, so every match is
    collected first (exact normalized side match preferred over substring),
    then the one most relevant to "now" is picked: the earliest game that is
    upcoming or in progress (commence_time >= now - 2.75h — MATCH_OVER_HOURS's
    2.5h plus a small buffer, not the old 6h), else the latest past game. This
    stops a stale group-stage fixture's kickoff leaking onto a later game for
    the same team. A match with no parseable commence_time at all is not a
    good enough guess to fall back to matches[0] on — return (None, None).
    """
    if not team:
        return None, None
    needle = team.strip().lower()

    exact_matches = []
    loose_matches = []
    for game in games:
        for side in game['game'].split('@'):
            side = side.strip().lower()
            if not side:
                continue
            if side == needle:
                exact_matches.append(game)
                break
            if side in needle or needle in side:
                loose_matches.append(game)
                break

    matches = exact_matches or loose_matches
    if not matches:
        return None, None

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=2.75)

    upcoming = []
    past = []
    for game in matches:
        ts = _parse_ts(game.get('commence_time'))
        if ts is None:
            continue
        if ts >= cutoff:
            upcoming.append((ts, game))
        else:
            past.append((ts, game))

    if upcoming:
        upcoming.sort(key=lambda pair: pair[0])
        chosen = upcoming[0][1]
    elif past:
        past.sort(key=lambda pair: pair[0])
        chosen = past[-1][1]
    else:
        # Every match had an unparseable commence_time — no basis to guess
        # which one is "now"; matches[0] here was the original bug.
        return None, None

    return chosen['commence_time'], chosen['game']


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
        # If a market now prices this stat (e.g. Underdog), use it — don't
        # double-log a weaker form-model play for the same prop.
        if get_sharp_ladders(stat_type):
            continue
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


AI_GATE_TIMEOUT_SECONDS = 90  # shorter than analyze_play's own internal timeout


def _apply_ai_gate_result(bet: dict, rec: dict | None) -> None:
    """Apply an AI gate outcome to a bet in place. rec=None means AI-unavailable
    (backend down, timeout, parse error) — verdict stays YES with a flag.

    A parsed-but-malformed response (valid JSON, no usable 'pick') is also
    treated as AI-unavailable rather than an explicit PASS — the model didn't
    actually weigh in, so it must not be read as disagreement."""
    if rec is None or rec.get('malformed'):
        bet['flags'] = ' | '.join(f for f in [bet.get('flags'), 'AI check unavailable'] if f)
        return

    bet['ai_pick'] = rec.get('pick')
    bet['ai_confidence'] = rec.get('confidence')

    disagrees = rec.get('pick') == 'PASS' or rec.get('agrees_with_engine') is False
    if disagrees:
        bet['verdict'] = 'LEAN'
        reasoning = (rec.get('reasoning') or '')[:120]
        bet['flags'] = ' | '.join(
            f for f in [bet.get('flags'), f'AI matchup analysis: {reasoning}'] if f
        )


def _apply_ai_gate(bet: dict) -> None:
    """Best-effort second opinion on a single YES verdict (Feature B).

    Never raises and never blocks the pipeline: any failure (backend
    unavailable, timeout, parse error) leaves the verdict at YES with a flag
    saying the check couldn't run. A model PASS, or an explicit disagreement,
    downgrades the verdict to LEAN.
    """
    try:
        rec = analyze_play(bet)
    except Exception:
        rec = None
    _apply_ai_gate_result(bet, rec)


def _apply_ai_gate_batch(bets: list[dict]) -> None:
    """Run the AI gate for every YES bet concurrently (Feature B latency fix).

    Mirrors api/main.py's build_slip_endpoint: a small thread pool so N slow
    AI calls run in parallel instead of serially blocking find_edges. Each
    call gets AI_GATE_TIMEOUT_SECONDS, shorter than analyze_play's own
    internal subprocess timeout, so one slow/hung call doesn't dominate the
    batch; on timeout it's treated exactly like any other AI-unavailable
    failure (YES kept, flagged).
    """
    if not bets:
        return
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(analyze_play, bet): bet for bet in bets}
        for future, bet in futures.items():
            try:
                rec = future.result(timeout=AI_GATE_TIMEOUT_SECONDS)
            except Exception:
                rec = None
            _apply_ai_gate_result(bet, rec)


def find_edges(sync_staging: bool = True):
    if sync_staging:
        try:
            ingest_results = ingest_staging()
            if ingest_results:
                print(f"Synced staging JSON to SQLite: {ingest_results}")
        except FileNotFoundError as error:
            print(f"Warning: {error}")

    sport = get_sport()
    active_sport = active_sport_key()
    injury_map = get_injury_map() if sport['has_injury_feed'] else {}
    flagged_bets = []
    unmatched = []
    priced_any = False

    derived_stats = sport.get('derived_stats', {})

    # Shadow model (council Phase-2): load FBref logs once, best-effort. Soccer
    # only; any failure -> {} so every model_* field logs NULL and the market
    # path is untouched. Player names are resolved through the same fuzzy matcher.
    logs_by_player = (
        load_fbref_logs(season=sport.get('fbref_season', '2026'))
        if sport.get('sources', {}).get('rate_prior') == 'fbref' else {}
    )
    _log_names = list(logs_by_player)
    _log_match_cache: dict[str, str | None] = {}

    def _logs_for(name: str) -> list[dict]:
        if not logs_by_player:
            return []
        if name not in _log_match_cache:
            matched, _ = match_player_name(name, _log_names)
            _log_match_cache[name] = matched
        matched = _log_match_cache[name]
        return logs_by_player.get(matched, []) if matched else []

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

        eligible = model_eligible(stat_type, derived=bool(derived))

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

            # Shadow column: the model's P(over) beside the market number. Base
            # soccer stats only, never combos; missing logs -> NULL. Flags nothing.
            if eligible and ' + ' not in pp_name:
                mf = model_fields(_logs_for(sharp_name), stat_type, pp_line,
                                  evaluation['play'])
            else:
                mf = dict(NULL_FIELDS)

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
                'consensus_n': evaluation.get('consensus_n'),
                'consensus_tag': evaluation.get('consensus_tag'),
                'best_book': evaluation.get('best_book'),
                'best_venue': evaluation.get('best_venue'),
                'venue_note': evaluation.get('venue_note'),
                # Phase-2 canonical-event triple + cluster/stratum keys.
                'consensus_p': evaluation.get('consensus_p'),
                'win_prob_raw': evaluation.get('win_prob_raw'),
                'baseline_p': evaluation.get('baseline_p'),
                'baseline_book': evaluation.get('baseline_book'),
                'line_band': evaluation.get('line_band'),
                'sport': active_sport,
                'game_date': _edge_game_date(evaluation['commence_time'],
                                             pp_player.get('captured_at')),
                'snapshot_bucket': _edge_bucket(pp_player.get('captured_at')),
                'commence_time': evaluation['commence_time'],
                'pp_captured_at': pp_player.get('captured_at'),
                'dk_captured_at': evaluation['sharp_captured_at'],
                **mf,
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

    # AI matchup gate (Feature B): a YES is rare by design, so it earns one
    # more best-effort check before it's logged. LEAN/NO never go through it.
    # Run concurrently (council fix) — serial per-YES calls were the pipeline's
    # main latency sink on a slate with several YES plays.
    yes_bets = [bet for bet in flagged_bets if bet['verdict'] == 'YES']
    _apply_ai_gate_batch(yes_bets)

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
            'game_id': bet.get('game_id') or bet.get('Team'),
            'win_prob': bet['win_prob'],
        })
    if len(yes_picks) < 2:
        print("\nFewer than 2 YES plays — no slip recommendation tonight.")
        return

    # Binding exposure caps (council Pillar 3): same-game/same-player legs are
    # capped before slips are built, so an independence-assuming break-even is
    # never applied to a silently correlated slip.
    kept, dropped = apply_exposure_caps(yes_picks)
    if dropped:
        print(f"\nExposure caps dropped {len(dropped)} leg(s): "
              + "; ".join(f"{d['player']} ({d['drop_reason']})" for d in dropped))
    if len(kept) < 2:
        print("Fewer than 2 legs survive exposure caps — no slip recommendation.")
        return

    # Correlation-aware slip construction (council OBJ-12/35/39): FLEX EV and
    # variance come from a Gaussian-copula simulation under the same-game
    # correlation prior, never from per-leg-separable independence.
    suggestions = construct_slips(kept)
    if not suggestions:
        print("\nNo positive-EV slip within the variance cap tonight.")
        return

    print("\nBest slips (correlation-aware EV/variance/Kelly; same-game legs correlated):")
    for s in suggestions:
        corr = '  [correlated legs]' if s['correlated_legs'] else ''
        print(
            f"  {s['structure'].ljust(13)} EV {s['ev_percent']:+.1f}%  "
            f"std {s['std']:.2f}  stake {s['kelly_pct']:.1f}% bankroll  "
            f"P(all)={s['p_all_hit']:.1%}  {', '.join(s['players'])}{corr}"
        )


if __name__ == '__main__':
    find_edges()
