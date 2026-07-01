"""AI matchup gate (Feature B): a YES verdict gets one best-effort second
opinion before it's logged; LEAN/NO never go through it."""

from engine import matcher
from engine.matcher import _apply_ai_gate


def _yes_bet() -> dict:
    return {
        "pp_player_name": "Kylian Mbappe",
        "player": "Kylian Mbappe",
        "team": "France",
        "stat_type": "player_shots_on_target",
        "play": "OVER",
        "pp_line": 0.5,
        "verdict": "YES",
        "win_prob": 0.72,
        "ev_percent": 17.75,
        "flags": None,
    }


def test_ai_disagreement_downgrades_yes_to_lean(monkeypatch):
    bet = _yes_bet()

    def fake_analyze(edge, **kwargs):
        return {
            "pick": "PASS",
            "confidence": 40,
            "agrees_with_engine": False,
            "reasoning": "The opponent's defense has been elite all tournament, discount this.",
            "key_factors": [],
        }

    monkeypatch.setattr(matcher, "analyze_play", fake_analyze)
    _apply_ai_gate(bet)

    assert bet["verdict"] == "LEAN"
    assert bet["ai_pick"] == "PASS"
    assert bet["ai_confidence"] == 40
    assert "AI matchup analysis:" in bet["flags"]
    assert "elite all tournament" in bet["flags"]


def test_ai_agreement_keeps_yes(monkeypatch):
    bet = _yes_bet()

    def fake_analyze(edge, **kwargs):
        return {
            "pick": "OVER",
            "confidence": 80,
            "agrees_with_engine": True,
            "reasoning": "Strong matchup.",
            "key_factors": [],
        }

    monkeypatch.setattr(matcher, "analyze_play", fake_analyze)
    _apply_ai_gate(bet)

    assert bet["verdict"] == "YES"
    assert bet["ai_pick"] == "OVER"
    assert bet["ai_confidence"] == 80


def test_ai_failure_keeps_yes_and_flags_unavailable(monkeypatch):
    bet = _yes_bet()

    def fake_analyze(edge, **kwargs):
        raise RuntimeError("Claude CLI error: not logged in")

    monkeypatch.setattr(matcher, "analyze_play", fake_analyze)
    _apply_ai_gate(bet)

    assert bet["verdict"] == "YES"
    assert bet["flags"] == "AI check unavailable"
    assert "ai_pick" not in bet


def test_malformed_ai_json_keeps_yes_not_downgraded(monkeypatch):
    # Parsed fine as JSON, but no valid 'pick' — this is malformed output, not
    # a genuine PASS, and must not read as disagreement (council finding).
    bet = _yes_bet()

    def fake_analyze(edge, **kwargs):
        from engine.ai_analyst import extract_recommendation
        return extract_recommendation('{"confidence": 80, "reasoning": "no pick field"}')

    monkeypatch.setattr(matcher, "analyze_play", fake_analyze)
    _apply_ai_gate(bet)

    assert bet["verdict"] == "YES"
    assert bet["flags"] == "AI check unavailable"
    assert "ai_pick" not in bet


def test_genuine_ai_pass_still_downgrades_yes(monkeypatch):
    bet = _yes_bet()

    def fake_analyze(edge, **kwargs):
        return {
            "pick": "PASS",
            "confidence": 60,
            "agrees_with_engine": False,
            "reasoning": "Genuinely thin edge.",
            "key_factors": [],
            "malformed": False,
        }

    monkeypatch.setattr(matcher, "analyze_play", fake_analyze)
    _apply_ai_gate(bet)

    assert bet["verdict"] == "LEAN"
    assert bet["ai_pick"] == "PASS"
