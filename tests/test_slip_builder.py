"""The slip builder: engine ranks, AI vets, only mutual picks survive, no padding."""

from engine import slip_builder
from engine.slip_builder import build_slip, eligible_edges, rank


def _edge(player, play="OVER", verdict="YES", ev=10.0, win=0.60, pp_line=2.5,
          underdog=None, game="Aland @ Brava"):
    edge = {
        "player": player, "play": play, "verdict": verdict,
        "ev_percent": ev, "win_prob": win, "pp_line": pp_line,
        "stat_type": "player_shots", "team": "Aland", "game": game,
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
    edges = [_edge("A", ev=5), _edge("B", ev=30), _edge("C", ev=15)]
    recs = {p: _rec("OVER") for p in ("A", "B", "C")}
    slip = build_slip(edges, 2, metric="ev", analyze_shortlist=_analyzer(recs))
    assert [leg["player"] for leg in slip["legs"]] == ["B", "C"]  # best two
    assert slip["short"] is False


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
