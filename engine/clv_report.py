import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from storage.db_manager import get_edges, get_latest_dk_line, ingest_staging

TARGET_STAT = 'player_points'


def calculate_clv(play: str, pp_line: float, closing_dk_line: float) -> float:
    if play == 'OVER':
        return round(closing_dk_line - pp_line, 2)
    return round(pp_line - closing_dk_line, 2)


def build_clv_rows(sync_staging: bool = True) -> list[dict]:
    if sync_staging:
        try:
            ingest_results = ingest_staging()
            if ingest_results:
                print(f"Synced staging JSON to SQLite: {ingest_results}\n")
        except FileNotFoundError as error:
            print(f"Warning: {error}\n")

    edges = get_edges(TARGET_STAT)
    if not edges:
        print("No logged edges found. Run python3 engine/matcher.py first.")
        return []

    rows = []
    for edge in edges:
        latest_dk = get_latest_dk_line(
            edge['dk_player_name'],
            TARGET_STAT,
            reference_line=edge['dk_line_at_flag'],
        )
        closing_line = latest_dk['line'] if latest_dk else edge['dk_line_at_flag']
        clv = calculate_clv(edge['play'], edge['pp_line'], closing_line)
        dk_move = round(closing_line - edge['dk_line_at_flag'], 2)

        rows.append({
            'flagged_at': edge['flagged_at'],
            'pp_player_name': edge['pp_player_name'],
            'dk_player_name': edge['dk_player_name'],
            'play': edge['play'],
            'pp_line': edge['pp_line'],
            'dk_line_at_flag': edge['dk_line_at_flag'],
            'closing_dk_line': closing_line,
            'dk_move': dk_move,
            'clv': clv,
            'edge_type': edge['edge_type'],
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
        f"{'MOVE'.ljust(5)} | {'CLV'.ljust(5)} | {'TYPE'}"
    )
    print("-" * 130)

    positive_clv = 0
    for row in rows:
        if row['clv'] > 0:
            positive_clv += 1
        print(
            f"{row['flagged_at'][:19].ljust(20)} | "
            f"{row['pp_player_name'].ljust(22)} | {row['play'].ljust(6)} | "
            f"{str(row['pp_line']).ljust(5)} | {str(row['dk_line_at_flag']).ljust(7)} | "
            f"{str(row['closing_dk_line']).ljust(7)} | {str(row['dk_move']).ljust(5)} | "
            f"{str(row['clv']).ljust(5)} | {row['edge_type']}"
        )

    avg_clv = round(sum(row['clv'] for row in rows) / len(rows), 2)
    print("-" * 130)
    print(f"Edges tracked: {len(rows)}")
    print(f"Positive CLV: {positive_clv}/{len(rows)} ({positive_clv / len(rows):.0%})")
    print(f"Average CLV: {avg_clv}")
    print()
    print("CLV meaning:")
    print("  Positive CLV = you had a better number than the latest DK line.")
    print("  Re-scrape DK before tip-off, then re-run this report for best closing-line accuracy.")


def main() -> None:
    rows = build_clv_rows()
    print_clv_report(rows)


if __name__ == '__main__':
    main()
