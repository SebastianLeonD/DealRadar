"""Sport configurations: one place that defines every market the engine trades.

Switch the active sport with ACTIVE_SPORT in .env ('nba' or 'world_cup').
Scrapers, matcher, and PP parser all read the active sport; settlement and
CLV infer the sport per edge from its stat_type, so mixed history grades fine.
"""

import os

from dotenv import load_dotenv

load_dotenv()

SPORTS = {
    'nba': {
        'label': 'NBA',
        'odds_api_key': 'basketball_nba',
        'espn_path': 'basketball/nba',
        'espn_box_format': 'labels',      # boxscore.players label/stat arrays
        'markets': [
            'player_points',
            'player_rebounds',
            'player_assists',
            'player_threes',
        ],
        'alternate_markets': {
            'player_points': 'player_points_alternate',
            'player_rebounds': 'player_rebounds_alternate',
            'player_assists': 'player_assists_alternate',
            'player_threes': 'player_threes_alternate',
        },
        'pp_stat_map': {
            'Points': 'player_points',
            'Rebounds': 'player_rebounds',
            'Assists': 'player_assists',
            '3-PT Made': 'player_threes',
        },
        # normal: high-count stats; poisson: low-count discrete stats
        'stat_models': {
            'player_points': 'normal',
            'player_rebounds': 'normal',
            'player_assists': 'normal',
            'player_threes': 'poisson',
        },
        'espn_stats': {
            'player_points': 'PTS',
            'player_rebounds': 'REB',
            'player_assists': 'AST',
            'player_threes': '3PT_made',   # made part of ESPN's "3-7" string
        },
        'max_hours_ahead': 48,
        'has_injury_feed': True,
        'integer_lines_are_milestones': False,
    },
    'world_cup': {
        'label': 'FIFA World Cup',
        'odds_api_key': 'soccer_fifa_world_cup',
        'espn_path': 'soccer/fifa.world',
        'espn_box_format': 'rosters',     # rosters[].roster[].stats named values
        'markets': [
            'player_shots',
            'player_shots_on_target',
            'player_assists',
            'player_goal_scorer_anytime',
            'player_goalie_saves',
        ],
        'alternate_markets': {},
        # Yes/No markets with no line: price = P(stat >= 1), i.e. over 0.5.
        # Scorer prices carry heavy margin; de-vig with a wider haircut.
        'binary_markets': {
            'player_goal_scorer_anytime': {'stat': 'player_goals', 'margin': 0.08},
        },
        'pp_stat_map': {
            'Shots': 'player_shots',
            'Shots On Target': 'player_shots_on_target',
            'Shots on Target': 'player_shots_on_target',
            'Shots On Goal': 'player_shots_on_target',
            'Assists': 'player_assists',
            'Goals': 'player_goals',
            'Goalie Saves': 'player_goalie_saves',
            # Model-priced stats (no book line) — projected from World Cup form.
            'Fouls': 'player_fouls',
            'Fouls Drawn': 'player_fouls_drawn',
            'Tackles': 'player_tackles',
            'Crosses': 'player_crosses',
            'Offsides': 'player_offsides',
            'Goals Allowed': 'player_goals_allowed',
        },
        'stat_models': {
            'player_shots': 'poisson',
            'player_shots_on_target': 'poisson',
            'player_assists': 'poisson',
            'player_goals': 'poisson',
            'player_goalie_saves': 'poisson',
            'player_shots_1h': 'poisson',
            'player_shots_on_target_1h': 'poisson',
            'player_goals_1h': 'poisson',
            'player_goalie_saves_1h': 'poisson',
            # Model-priced stats (FBref form, no book line)
            'player_fouls': 'poisson',
            'player_fouls_drawn': 'poisson',
            'player_tackles': 'poisson',
            'player_crosses': 'poisson',
            'player_offsides': 'poisson',
            'player_goals_allowed': 'poisson',
        },
        # PP posts its standard soccer board as FIRST-HALF props. No book
        # offers 1H player markets, so these are derived from full-match
        # ladders by Poisson thinning: ~45% of shots happen before the break.
        # Derived plays are capped at LEAN — the number is modeled, not
        # market-verified.
        'derived_stats': {
            'player_shots_1h': {'base': 'player_shots', 'rate_share': 0.45},
            'player_shots_on_target_1h': {'base': 'player_shots_on_target', 'rate_share': 0.45},
            'player_goals_1h': {'base': 'player_goals', 'rate_share': 0.44},
            'player_goalie_saves_1h': {'base': 'player_goalie_saves', 'rate_share': 0.45},
        },
        # 1H duration suffix on PP props maps to the derived stat types
        'pp_duration_suffixes': {'1H': '_1h'},
        'espn_stats': {
            'player_shots': 'totalShots',
            'player_shots_on_target': 'shotsOnTarget',
            'player_assists': 'goalAssists',
            'player_goals': 'totalGoals',
            'player_goalie_saves': 'saves',
            # 1H stats have no ESPN box-score source; settlement skips them
        },
        # 69 matches sit in the events feed; only fetch odds for near kickoffs
        'max_hours_ahead': 36,
        'has_injury_feed': False,
        # Books post soccer props as milestones: "Over 2.0" means 2+, i.e.
        # X > 1.5. Normalize integer lines to half-lines at flatten time.
        'integer_lines_are_milestones': True,
        # Per-sport source registry (council OBJ-19/20). FBref supplies realized
        # shots/SoT/goals/minutes for settlement and the cold-start rate prior;
        # the model it feeds is asserted and gated by the calibration loop.
        # Pre-match lineups (the start/minutes signal FBref lacks) come from a
        # separate feed (FotMob/Sofascore) that is not yet wired.
        'sources': {
            'settlement': ['fbref', 'espn'],   # fbref primary, espn fallback
            'rate_prior': 'fbref',
            'fbref_league': 'INT-World Cup',
            'lineup': None,                    # TODO: FotMob/Sofascore confirmed XI
        },
        'model': 'fbref_poisson_prior',        # asserted; must clear Phase 2
    },
}


def active_sport_key() -> str:
    key = os.getenv('ACTIVE_SPORT', 'nba').strip().lower()
    if key not in SPORTS:
        raise SystemExit(
            f"Unknown ACTIVE_SPORT '{key}'. Valid options: {', '.join(SPORTS)}"
        )
    return key


def get_sport(key: str | None = None) -> dict:
    return SPORTS[key or active_sport_key()]


def sport_for_stat(stat_type: str) -> str | None:
    """Which sport a stat belongs to — lets settlement grade mixed history."""
    for key, config in SPORTS.items():
        if stat_type in config['stat_models']:
            return key
    return None
