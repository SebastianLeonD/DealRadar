import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db_manager import get_edges, get_latest_dk_line, ingest_staging


def calculate_clv_prob(play: str, flag_true_p_over: float, close_true_p_over: float) -> float:
    """Headline CLV in no-vig PROBABILITY units (council OBJ-2).

    CLV = close_true_p(side) - flag_true_p(side), signed to the bet side.
    Positive = the market moved toward your side in probability between flag
    and close. This captures asymmetric-vig movement that a line-only delta
    discards — half the price in a retail prop book lives in the juice.

    Probabilities are passed as 0..1 (true P(over)); the result is in the same
    units (probability points as a fraction).
    """
    if play == 'OVER':
        delta = close_true_p_over - flag_true_p_over
    else:
        # P(under) = 1 - P(over); the (1-)s cancel, flipping the sign.
        delta = flag_true_p_over - close_true_p_over
    return round(delta, 4)


def calculate_clv_line(play: str, pp_line: float, closing_dk_line: float) -> float:
    """SECONDARY diagnostic only: CLV in line points (the 'MOVE' column)."""
    if play == 'OVER':
        return round(closing_dk_line - pp_line, 2)
    return round(pp_line - closing_dk_line, 2)


# Back-compat alias. The line delta is now a diagnostic, not the headline.
calculate_clv = calculate_clv_line


def build_clv_rows(sync_staging: bool = True) -> list[dict]:
    if sync_staging:
        try:
            ingest_results = ingest_staging()
            if ingest_results:
                print(f"Synced staging JSON to SQLite: {ingest_results}\n")
        except FileNotFoundError as error:
            print(f"Warning: {error}\n")

    edges = get_edges()
    if not edges:
        print("No logged edges found. Run python3 engine/matcher.py first.")
        return []

    rows = []
    for edge in edges:
        latest_dk = get_latest_dk_line(
            edge['dk_player_name'],
            edge['stat_type'],
            reference_line=edge['dk_line_at_flag'],
        )
        closing_line = latest_dk['line'] if latest_dk else edge['dk_line_at_flag']
        clv_line = calculate_clv_line(edge['play'], edge['pp_line'], closing_line)
        dk_move = round(closing_line - edge['dk_line_at_flag'], 2)

        # Headline CLV in no-vig probability units (OBJ-2). flag prob is the
        # consensus over-prob captured on the edge; close prob is the latest
        # sharp true over-prob. Both stored as percent (0..100).
        flag_p = edge.get('dk_over_prob')
        close_p = latest_dk.get('true_over_prob') if latest_dk else None
        clv_prob = None
        if flag_p is not None and close_p is not None:
            clv_prob = calculate_clv_prob(edge['play'], flag_p / 100.0, close_p / 100.0)

        rows.append({
            'flagged_at': edge['flagged_at'],
            'pp_player_name': edge['pp_player_name'],
            'dk_player_name': edge['dk_player_name'],
            'play': edge['play'],
            'pp_line': edge['pp_line'],
            'dk_line_at_flag': edge['dk_line_at_flag'],
            'closing_dk_line': closing_line,
            'dk_move': dk_move,
            'clv_prob': clv_prob,   # headline (probability units)
            'clv': clv_line,        # secondary diagnostic (line points)
            'edge_type': edge['edge_type'],
            'stat_type': edge['stat_type'],
            'team': edge.get('team') or '',
        })

    return rows


def print_clv_report(rows: list[dict]) -> None:
    if not rows:
        return

    print("Closing Line Value Report")
    print("=" * 130)
    print(
        f"{'FLAGGED AT'.ljust(20)} | {'PLAYER'.ljust(22)} | {'PLAY'.ljust(6)} | "
        f"{'PP'.ljust(5)} | {'DK@FLAG'.ljust(7)} | {'DK NOW'.ljust(7)} | "
        f"{'MOVE'.ljust(5)} | {'CLV%'.ljust(6)} | {'TYPE'}"
    )
    print("-" * 130)

    # Headline = probability CLV; fall back to the line diagnostic only when the
    # close probability is unavailable.
    def headline(row):
        return row['clv_prob'] if row['clv_prob'] is not None else None

    positive_clv = 0
    measurable = 0
    for row in rows:
        h = headline(row)
        clv_pct = '   n/a' if h is None else f"{h * 100:+5.1f}"
        if h is not None:
            measurable += 1
            if h > 0:
                positive_clv += 1
        print(
            f"{row['flagged_at'][:19].ljust(20)} | "
            f"{row['pp_player_name'].ljust(22)} | {row['play'].ljust(6)} | "
            f"{str(row['pp_line']).ljust(5)} | {str(row['dk_line_at_flag']).ljust(7)} | "
            f"{str(row['closing_dk_line']).ljust(7)} | {str(row['dk_move']).ljust(5)} | "
            f"{clv_pct.ljust(6)} | {row['edge_type']}"
        )

    print("-" * 130)
    print(f"Edges tracked: {len(rows)} ({measurable} with a measurable closing probability)")
    if measurable:
        probs = [r['clv_prob'] for r in rows if r['clv_prob'] is not None]
        avg_clv = round(sum(probs) / len(probs) * 100, 2)
        print(f"Positive CLV: {positive_clv}/{measurable} ({positive_clv / measurable:.0%})")
        print(f"Average CLV: {avg_clv:+.2f} probability points")
    print()
    print("CLV meaning (headline is in no-vig probability units, council OBJ-2):")
    print("  Positive CLV = the market's true probability moved toward your side after you flagged it.")
    print("  Re-scrape sharp books before tip-off, then re-run for best closing-line accuracy.")


def main() -> None:
    rows = build_clv_rows()
    print_clv_report(rows)


if __name__ == '__main__':
    main()
