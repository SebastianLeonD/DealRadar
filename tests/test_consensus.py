"""Line-matched no-vig consensus (council OBJ-1/3)."""

from engine.consensus import consensus_over_ladder, line_matched_consensus


def test_equal_weight_mean_in_probability_space():
    c = line_matched_consensus({'dk': 0.60, 'fd': 0.50})
    assert abs(c['consensus_p_over'] - 0.55) < 1e-9
    assert abs(c['consensus_p_under'] - 0.45) < 1e-9
    assert c['consensus_n'] == 2
    assert c['consensus_tag'] == 'identified'
    assert c['consensus_book_set'] == ['dk', 'fd']


def test_single_book_does_not_earn_identified_tag():
    c = line_matched_consensus({'dk': 0.58})
    assert c['consensus_n'] == 1
    assert c['consensus_tag'] == 'single_book'


def test_high_hold_book_is_dropped():
    c = line_matched_consensus(
        {'dk': 0.60, 'fd': 0.50, 'shady': 0.90},
        book_holds={'dk': 1.04, 'fd': 1.05, 'shady': 1.20},
    )
    assert 'shady' not in c['consensus_book_set']
    assert c['consensus_n'] == 2
    assert abs(c['consensus_p_over'] - 0.55) < 1e-9


def test_budget_truncation_withholds_identified_tag():
    c = line_matched_consensus({'dk': 0.60, 'fd': 0.50}, budget_truncated=True)
    assert c['consensus_n'] == 2
    assert c['consensus_tag'] == 'degraded'  # cannot claim consensus over a partial set


def test_fetch_failure_withholds_identified_tag():
    c = line_matched_consensus({'dk': 0.60, 'fd': 0.50}, failed_books=1)
    assert c['consensus_tag'] == 'degraded'


def test_different_lines_are_never_averaged_together():
    # DK quotes 25.5, FD quotes 24.5 — they are different events. Each line
    # gets its own consensus; neither reaches 2 books, so neither is identified.
    ladders = {
        'dk': [(25.5, 0.52)],
        'fd': [(24.5, 0.61)],
    }
    out = consensus_over_ladder(ladders)
    assert set(out) == {25.5, 24.5}
    assert out[25.5]['consensus_n'] == 1
    assert out[24.5]['consensus_n'] == 1
    assert out[25.5]['consensus_tag'] == 'single_book'


def test_same_line_across_books_is_identified():
    ladders = {
        'dk': [(25.5, 0.52)],
        'fd': [(25.5, 0.56)],
        'betmgm': [(25.5, 0.54)],
    }
    out = consensus_over_ladder(ladders)
    assert out[25.5]['consensus_n'] == 3
    assert out[25.5]['consensus_tag'] == 'identified'
    assert abs(out[25.5]['consensus_p_over'] - 0.54) < 1e-9
