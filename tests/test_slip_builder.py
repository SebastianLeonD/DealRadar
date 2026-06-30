"""The slip builder: engine ranks, AI vets, only mutual picks survive, no padding."""

from engine import slip_builder
from engine.slip_builder import build_slip, eligible_edges, rank


def _edge(player, play="OVER", verdict="YES", ev=10.0, win=0.60, pp_line=2.5,
          underdog=None, game="Aland @ Brava", team="Aland", stat="player_shots"):
    edge = {
        "player": player, "play": play, "verdict": verdict,
        "ev_percent": ev, "win_prob": win, "pp_line": pp_line,
        "stat_type": stat, "team": team, "game": game,
    }
    if underdog is not None:
        edge["underdog"] = underdog
    return edge


def _rec(pick="OVER", underdog_pick=None, confidence=70):
    return {"pick": pick, "underdog_pick": underdog_pick, "confidence": confidence,
            "reasoning": "r", "key_factors": ["a"]}


def _analyzer(rec_by_player):
    """Fake AI: returns a rec per shortlisted edge, aligned by order."""
    return lambda items: [rec_by_player.get(e["player"]) for e in items]


# --- eligibility + ranking ---

def test_eligible_drops_no_verdicts_and_off_provider():
    edges = [
        _edge("Yes"), _edge("Lean", verdict="LEAN"), _edge("No", verdict="NO"),
        _edge("UdOnly", underdog={"ud_line": 1.5}),
    ]
    assert {e["player"] for e in eligible_edges(edges, "PP")} == {"Yes", "Lean", "UdOnly"}
    # Underdog slip: only picks Underdog actually offers
    assert {e["player"] for e in eligible_edges(edges, "UD")} == {"UdOnly"}


def test_rank_by_metric():
    edges = [_edge("Low", ev=2, win=0.9), _edge("High", ev=20, win=0.55)]
    assert [e["player"] for e in rank(edges, "ev")] == ["High", "Low"]
    assert [e["player"] for e in rank(edges, "win")] == ["Low", "High"]


# --- the agree-test ---

def test_only_ai_agreed_legs_survive():
    edges = [_edge("Agree"), _edge("Flip"), _edge("Pass")]
    recs = {"Agree": _rec("OVER"), "Flip": _rec("UNDER"), "Pass": _rec("PASS")}
    slip = build_slip(edges, 3, analyze_shortlist=_analyzer(recs))
    assert [leg["player"] for leg in slip["legs"]] == ["Agree"]
    assert slip["agreed"] == 1


def test_no_padding_returns_short_slip():
    edges = [_edge("Agree"), _edge("Flip")]
    slip = build_slip(edges, 3, analyze_shortlist=_analyzer({"Agree": _rec("OVER"),
                                                             "Flip": _rec("UNDER")}))
    assert len(slip["legs"]) == 1
    assert slip["short"] is True
    assert slip["requested"] == 3


def test_takes_top_n_by_rank():
    edges = [_edge("A", ev=5, team="T1"), _edge("B", ev=30, team="T2"),
             _edge("C", ev=15, team="T1")]
    recs = {p: _rec("OVER") for p in ("A", "B", "C")}
    slip = build_slip(edges, 2, metric="ev", analyze_shortlist=_analyzer(recs))
    assert [leg["player"] for leg in slip["legs"]] == ["B", "C"]  # best two
    assert slip["short"] is False
    assert slip["valid"] is True  # two players, two teams


# --- PrizePicks lineup validity ---

def test_same_player_never_appears_twice():
    # One player with two strong props, plus a second player. A valid lineup
    # keeps the player's best prop once and fills the rest with others.
    edges = [
        _edge("Star", ev=40, team="T1", stat="player_shots"),
        _edge("Star", ev=35, team="T1", stat="player_shots_on_target"),
        _edge("Other", ev=20, team="T2"),
    ]
    recs = {"Star": _rec("OVER"), "Other": _rec("OVER")}
    slip = build_slip(edges, 2, analyze_shortlist=_analyzer(recs))
    players = [leg["player"] for leg in slip["legs"]]
    assert players == ["Star", "Other"]  # Star appears exactly once
    assert len(set(players)) == len(players)


def test_lineup_must_span_two_teams():
    # Top two by EV are the same team; the builder swaps in a different team.
    edges = [
        _edge("A", ev=40, team="Belgium"),
        _edge("B", ev=30, team="Belgium"),
        _edge("C", ev=10, team="Spain"),
    ]
    recs = {p: _rec("OVER") for p in ("A", "B", "C")}
    slip = build_slip(edges, 2, analyze_shortlist=_analyzer(recs))
    teams = {leg["team"] for leg in slip["legs"]}
    assert len(teams) == 2 and slip["valid"] is True
    assert "A" in [leg["player"] for leg in slip["legs"]]  # best leg kept


def test_one_team_only_is_flagged_invalid():
    edges = [_edge("A", ev=40, team="Belgium"), _edge("B", ev=30, team="Belgium")]
    slip = build_slip(edges, 2, analyze_shortlist=_analyzer({"A": _rec("OVER"),
                                                             "B": _rec("OVER")}))
    assert slip["team_count"] == 1 and slip["valid"] is False


def test_combos_are_never_picked():
    edges = [
        _edge("Solo", ev=10, team="T1"),
        _edge("Aaron + Bo", ev=99, team="T1/T2"),  # combo: highest EV but excluded
    ]
    assert [e["player"] for e in eligible_edges(edges, "PP")] == ["Solo"]
    slip = build_slip(edges, 2, analyze_shortlist=_analyzer({"Solo": _rec("OVER")}))
    assert [leg["player"] for leg in slip["legs"]] == ["Solo"]


def test_messy_team_string_is_cleaned():
    edge = _edge("X", team="Uruguay Uruguay")
    slip = build_slip([edge], 1, analyze_shortlist=_analyzer({"X": _rec("OVER")}))
    assert slip["legs"][0]["team"] == "Uruguay"


def test_failed_ai_call_is_dropped_not_crashed():
    edges = [_edge("Ok"), _edge("Broke")]
    slip = build_slip(edges, 2, analyze_shortlist=_analyzer({"Ok": _rec("OVER"),
                                                             "Broke": None}))
    assert [leg["player"] for leg in slip["legs"]] == ["Ok"]


# --- correlations + provider ---

def test_same_game_legs_are_flagged():
    edges = [
        _edge("A", ev=20, game="Aland @ Brava"),
        _edge("B", ev=15, game="Aland @ Brava"),
        _edge("C", ev=10, game="Cira @ Duna"),
    ]
    recs = {p: _rec("OVER") for p in ("A", "B", "C")}
    slip = build_slip(edges, 3, analyze_shortlist=_analyzer(recs))
    assert slip["correlations"] == [{"game": "Aland @ Brava", "players": ["A", "B"]}]


def test_underdog_slip_uses_ud_line_and_ud_pick():
    edge = _edge("U", pp_line=2.5, underdog={"ud_line": 1.5})
    # On PrizePicks the AI passes, but on the Underdog line it's an OVER.
    slip = build_slip([edge], 1, provider="UD",
                      analyze_shortlist=_analyzer({"U": _rec("PASS", underdog_pick="OVER")}))
    assert len(slip["legs"]) == 1
    leg = slip["legs"][0]
    assert leg["line"] == 1.5 and leg["provider"] == "UD"
    assert leg["ai"]["pick"] == "OVER"


def test_default_analyzer_is_wired_to_ai(monkeypatch):
    # build_slip with no injected analyzer should call engine.ai_analyst.analyze_play.
    calls = []
    monkeypatch.setattr("engine.ai_analyst.analyze_play",
                        lambda edge, mode="full": calls.append(edge["player"]) or _rec("OVER"))
    slip = build_slip([_edge("Solo")], 1)
    assert calls == ["Solo"] and len(slip["legs"]) == 1
