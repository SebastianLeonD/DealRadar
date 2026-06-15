import json
import types

import pytest

from engine import ai_analyst
from engine.ai_analyst import (
    analyze_play,
    build_context,
    extract_recommendation,
    format_prompt,
    opponent_from_game,
)


def _edge():
    return {
        "player": "Kylian Mbappe",
        "team": "France",
        "stat_type": "player_shots_on_target",
        "play": "OVER",
        "pp_line": 0.5,
        "dk_line": 1.5,
        "edge_type": "Line Discrepancy",
        "verdict": "YES",
        "win_prob": 0.72,
        "ev_percent": 17.75,
        "book_count": 4,
        "flags": "Books disagree by 9% — market unsettled | Injury report: questionable",
    }


def test_build_context_computes_gap_and_splits_flags():
    ctx = build_context(_edge())
    assert ctx["line_gap"] == pytest.approx(1.0)
    assert ctx["stat_type"] == "shots on target"
    assert len(ctx["trap_flags"]) == 2
    assert ctx["engine_verdict"] == "YES"


def test_build_context_handles_missing_and_list_flags():
    ctx = build_context({"pp_player_name": "X", "flags": ["a", "b"], "pp_line": 1.5})
    assert ctx["player"] == "X"
    assert ctx["trap_flags"] == ["a", "b"]
    assert ctx["line_gap"] is None  # no dk line


def test_format_prompt_includes_flags_and_numbers():
    prompt = format_prompt(build_context(_edge()))
    assert "Kylian Mbappe" in prompt
    assert "Injury report: questionable" in prompt
    assert "OVER, UNDER, or PASS" in prompt


def test_opponent_from_game_picks_other_side():
    assert opponent_from_game("New Zealand @ Iran", "New Zealand") == "Iran"
    assert opponent_from_game("Egypt @ Belgium", "Belgium") == "Egypt"


def test_opponent_from_game_handles_bad_input():
    assert opponent_from_game("", "Belgium") == ""
    assert opponent_from_game(None, "Belgium") == ""
    assert opponent_from_game("Egypt @ Belgium", None) == ""
    assert opponent_from_game(float("nan"), float("nan")) == ""  # NaN rows from pandas


def test_build_context_resolves_opponent_and_matchup():
    ctx = build_context({**_edge(), "game": "Tunisia @ France"})
    assert ctx["opponent"] == "Tunisia"
    assert ctx["matchup"] == "Tunisia @ France"
    prompt = format_prompt(ctx)
    assert "Tunisia" in prompt and "Matchup" in prompt


def test_extract_plain_and_fenced():
    plain = extract_recommendation(
        '{"pick":"OVER","confidence":70,"agrees_with_engine":true,'
        '"reasoning":"x","key_factors":["a"]}'
    )
    assert plain["pick"] == "OVER" and plain["confidence"] == 70
    fenced = extract_recommendation(
        '```json\n{"pick":"PASS","confidence":40,"agrees_with_engine":false,'
        '"reasoning":"thin","key_factors":[]}\n```'
    )
    assert fenced["pick"] == "PASS"


def test_extract_ignores_trailing_and_leading_prose():
    trailing = extract_recommendation(
        '{"pick":"UNDER","confidence":55,"agrees_with_engine":false,'
        '"reasoning":"y","key_factors":["z"]}\n\nNote: extra prose here.'
    )
    assert trailing["pick"] == "UNDER"
    leading = extract_recommendation(
        'Here is my call:\n{"pick":"OVER","confidence":80,'
        '"agrees_with_engine":true,"reasoning":"q","key_factors":[]}'
    )
    assert leading["pick"] == "OVER"


def test_extract_clamps_and_normalizes():
    rec = extract_recommendation(
        '{"pick":"maybe","confidence":250,"reasoning":"r","key_factors":"single"}'
    )
    assert rec["pick"] == "PASS"          # unknown pick -> PASS
    assert rec["confidence"] == 100        # clamped
    assert rec["key_factors"] == ["single"]  # string coerced to list
    assert rec["agrees_with_engine"] is False  # missing -> default


def test_extract_raises_on_no_json():
    with pytest.raises(ValueError):
        extract_recommendation("no json here at all")


def test_analyze_via_cli_parses_envelope():
    inner = {
        "pick": "OVER", "confidence": 78, "agrees_with_engine": True,
        "reasoning": "Big gap.", "key_factors": ["line gap", "+EV"],
    }

    captured = {}

    def fake_runner(cmd, **kwargs):
        captured["cmd"] = cmd
        envelope = {"type": "result", "result": json.dumps(inner)}
        return types.SimpleNamespace(returncode=0, stdout=json.dumps(envelope), stderr="")

    rec = analyze_play(_edge(), backend="cli", runner=fake_runner)
    assert rec["pick"] == "OVER" and rec["confidence"] == 78
    assert "-p" in captured["cmd"] and "--output-format" in captured["cmd"]


def test_analyze_via_cli_raises_on_failure():
    def fake_runner(cmd, **kwargs):
        return types.SimpleNamespace(returncode=1, stdout="", stderr="not logged in")

    with pytest.raises(RuntimeError, match="not logged in"):
        analyze_play(_edge(), backend="cli", runner=fake_runner)


def test_extract_tolerates_unescaped_control_chars():
    # Models sometimes leave a literal newline inside the reasoning string.
    rec = extract_recommendation(
        '{"pick":"OVER","confidence":70,"reasoning":"line one\nline two","key_factors":["a"]}'
    )
    assert rec["pick"] == "OVER" and "line two" in rec["reasoning"]


def test_cli_failure_surfaces_envelope_message():
    # A usage limit comes back as returncode 1 with the reason in result, not stderr.
    def fake_runner(cmd, **kwargs):
        envelope = {"type": "result", "result": "You've hit your Opus limit · resets Jun 18"}
        return types.SimpleNamespace(returncode=1, stdout=json.dumps(envelope), stderr="")

    with pytest.raises(RuntimeError, match="Opus limit"):
        analyze_play(_edge(), backend="cli", runner=fake_runner)


def test_cli_available_returns_bool():
    assert isinstance(ai_analyst.cli_available(), bool)


def test_cli_model_splits_by_mode():
    # Picks (full) get opus; the high-volume board (stats_only) gets haiku.
    def capture(store):
        def run(cmd, **kwargs):
            store["model"] = cmd[cmd.index("--model") + 1]
            envelope = {"result": json.dumps(
                {"pick": "PASS", "confidence": 50, "reasoning": "r", "key_factors": []}
            )}
            return types.SimpleNamespace(returncode=0, stdout=json.dumps(envelope), stderr="")
        return run

    full, stats = {}, {}
    analyze_play(_edge(), backend="cli", mode="full", runner=capture(full))
    analyze_play(_edge(), backend="cli", mode="stats_only", runner=capture(stats))
    assert full["model"] == "opus"
    assert stats["model"] == "haiku"
