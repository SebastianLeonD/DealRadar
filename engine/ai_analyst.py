"""AI analyst: hand a flagged play's full context to Claude for an OVER/UNDER call.

This sits on top of the engine's own pricing. Every signal the engine already
computed — the sharp-consensus win probability, the EV over break-even, the
verdict, the anchor line vs the PrizePicks line, the book count and any trap
flags — is handed to Claude, which returns an independent OVER / UNDER / PASS
call with plain-English reasoning. It is a second opinion that reads the
warnings, not a replacement for the math.

Backends (env AI_BACKEND):
  * 'cli'  -> the logged-in `claude` CLI, which runs on your Claude Pro/Max
              SUBSCRIPTION. No metered API key, no per-call billing.
  * 'sdk'  -> the Anthropic API via ANTHROPIC_API_KEY (metered).
  * 'auto' -> CLI when installed, else SDK (the default).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

AI_BACKEND = os.getenv("AI_BACKEND", "auto")
AI_CLI_BINARY = os.getenv("AI_CLI_BINARY", "claude")
# Model by analysis mode: opus for real picks (full), haiku for the cheap,
# high-volume PrizePicks-board reads (stats_only). All overridable via .env.
AI_CLI_MODEL = os.getenv("AI_CLI_MODEL", "opus")              # full / default
AI_CLI_MODEL_STATS = os.getenv("AI_CLI_MODEL_STATS", "haiku")  # stats_only
AI_SDK_MODEL = os.getenv("AI_MODEL", "claude-opus-4-8")
AI_SDK_MODEL_STATS = os.getenv("AI_MODEL_STATS", "claude-haiku-4-5-20251001")
AI_MAX_TOKENS = int(os.getenv("AI_MAX_TOKENS", "16000"))


def _cli_model_for(mode: str) -> str:
    if mode == "stats_only":
        return os.getenv("AI_CLI_MODEL_STATS", AI_CLI_MODEL_STATS)
    return os.getenv("AI_CLI_MODEL", AI_CLI_MODEL)


def _sdk_model_for(mode: str) -> str:
    if mode == "stats_only":
        return os.getenv("AI_MODEL_STATS", AI_SDK_MODEL_STATS)
    return os.getenv("AI_MODEL", AI_SDK_MODEL)

SYSTEM_PROMPT = (
    "You are a sharp sports-betting analyst reviewing a single PrizePicks player "
    "prop. An automated engine has already priced it against a multi-book sharp "
    "consensus (DraftKings, FanDuel, BetMGM, Caesars) and produced a verdict. "
    "Your job is an independent second opinion: OVER, UNDER, or PASS.\n\n"
    "How to reason:\n"
    "- The sharp consensus win probability is the engine's best estimate of the "
    "true chance. A PrizePicks line far from where the books sit, in your favour, "
    "is the strongest signal.\n"
    "- EV is measured against the 54.25% PrizePicks flex break-even. A play only "
    "makes sense if the win probability clears that and EV is positive.\n"
    "- WEIGH THE MATCHUP, led by the tournament-form numbers when they are given. "
    "The context may include this World Cup's form: the player's team attack and "
    "style, and the opponent's defense (goals conceded, shots on target faced). "
    "PREFER these actual numbers over general reputation — they reflect how the "
    "teams have really played. But they are small samples (often one or two "
    "matches), so do not over-read them; treat one game as weak evidence and fall "
    "back on what you know about the teams. Ask: does this player's side create "
    "enough chances, and is the opponent's defense leaky or stingy, to support the "
    "line? For a goalkeeper, a leaky team in front of a busy keeper means more "
    "saves. A favourable line against a defense that has been conceding chances is "
    "more trustworthy; a tempting line against a defense keeping clean sheets "
    "deserves scepticism. Name the specific opponent and cite the form when it "
    "drives the call.\n"
    "- TAKE THE TRAP FLAGS SERIOUSLY. They catch the classic PrizePicks failure "
    "mode: a 'great' line gap that is really the sharp books pricing in news PP "
    "hasn't reacted to (injuries, stale board, books disagreeing). If a serious "
    "flag is present, lean toward PASS even when the math looks good.\n"
    "- Low-count stats (shots, shots on target, goals, threes) are noisy; a thin "
    "edge from a single book is weak evidence.\n"
    "- Be disciplined: a confident PASS beats a marginal bet. Do not invent "
    "information that is not in the context."
)

STATS_ONLY_SYSTEM_PROMPT = (
    "You are a soccer analyst giving a form- and matchup-based read on a single "
    "PrizePicks player prop. IMPORTANT: there is NO sportsbook line for this "
    "prop — you have no market to lean on. Reason ONLY from the data provided "
    "(the player's tournament form, the team form) plus your tactical knowledge "
    "of the players and teams.\n\n"
    "How to reason:\n"
    "- START FROM THE PLAYER. If a per-game rate is given, that is your anchor: "
    "compare it directly to the PrizePicks line. Is this player a high-volume "
    "source of this stat or a peripheral one?\n"
    "- WEIGH THE MATCHUP using the team form. Does the player's side create "
    "enough volume, and is the opponent leaky or stingy in this area? For a "
    "goalkeeper, more saves come from a busy keeper on a team under pressure.\n"
    "- RESPECT SMALL SAMPLES. World Cup form is often one or two matches. Treat "
    "it as weak evidence and lean on what you know about the player; say so.\n"
    "- BE HONEST ABOUT UNCERTAINTY. With no market and little data, the right "
    "answer is often PASS. Do NOT invent stats you were not given. If you have "
    "no real basis, return PASS with low confidence.\n"
    "- This is the stats half of the analysis only — there is no market check, so "
    "do not pretend one exists."
)

_JSON_INSTRUCTION = (
    "Respond with ONLY a JSON object (no markdown, no code fences, no prose) of "
    "exactly this shape:\n"
    '{"pick": "OVER"|"UNDER"|"PASS", "confidence": <int 0-100>, '
    '"agrees_with_engine": <true|false>, "reasoning": "<2-4 sentences>", '
    '"key_factors": ["<short phrase>", ...]}'
)


def _json_instruction(ctx: dict | None = None) -> str:
    """The required response shape — adds a second pick when the prop is offered
    on PrizePicks and Underdog at different lines (the call can differ)."""
    pp = ctx.get("prizepicks_line") if ctx else None
    ud = ctx.get("underdog_line") if ctx else None
    if ud is not None and pp is not None and ud != pp:
        return (
            "Respond with ONLY a JSON object (no markdown, no code fences, no prose) of "
            "exactly this shape:\n"
            '{"pick": "OVER"|"UNDER"|"PASS", "underdog_pick": "OVER"|"UNDER"|"PASS", '
            '"confidence": <int 0-100>, "agrees_with_engine": <true|false>, '
            '"reasoning": "<2-4 sentences>", "key_factors": ["<short phrase>", ...]}\n'
            f"`pick` is your call for the PrizePicks line ({pp}); `underdog_pick` is your "
            f"call for the Underdog line ({ud})."
        )
    return _JSON_INSTRUCTION


# ---------------------------------------------------------------------------
# Context + prompt (pure / testable)
# ---------------------------------------------------------------------------
def _num(value):
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _stat_label(stat: str | None) -> str:
    if not stat:
        return ""
    return stat.replace("player_", "").replace("_", " ")


def opponent_from_game(game: str | None, team: str | None) -> str:
    """Pick the opponent out of a 'Away @ Home' game string given the player's
    team. Tolerant of loose name matches; returns '' when it can't tell."""
    if not isinstance(game, str) or "@" not in game:
        return ""
    away, _, home = game.partition("@")
    away, home = away.strip(), home.strip()
    if not isinstance(team, str) or not team.strip():
        return ""
    t = team.strip().lower()
    if t and (t in home.lower() or home.lower() in t):
        return away
    if t and (t in away.lower() or away.lower() in t):
        return home
    return ""


def build_context(edge: dict, mode: str = "full") -> dict:
    """Normalise a frontend/DB edge row into the analyst's context.

    mode='full' includes the sharp-book consensus. mode='stats_only' drops it and
    adds the player's own form rate — a PrizePicks-only, stats-driven read.
    """
    pp_line = _num(edge.get("pp_line"))
    dk_line = _num(edge.get("dk_line") if edge.get("dk_line") is not None
                   else edge.get("dk_line_at_flag"))
    win_prob = _num(edge.get("win_prob"))
    line_gap = round(dk_line - pp_line, 2) if (dk_line is not None and pp_line is not None) else None

    flags = edge.get("flags")
    if isinstance(flags, str):
        flag_list = [f.strip() for f in flags.split("|") if f.strip()]
    elif isinstance(flags, (list, tuple)):
        flag_list = list(flags)
    else:
        flag_list = []

    team = edge.get("team") or ""
    game = edge.get("game") or ""
    opponent = edge.get("opponent") or opponent_from_game(game, team)

    from engine.team_profiles import team_form
    form = team_form(team, opponent)

    player = edge.get("player") or edge.get("pp_player_name")
    player_rate = None
    if mode == "stats_only":
        from engine.projections import player_form
        player_rate = player_form(player, edge.get("stat_type"))

    return {
        "mode": mode,
        "player": edge.get("player") or edge.get("pp_player_name"),
        "team": team,
        "opponent": opponent,
        "matchup": game,
        "stat_type": _stat_label(edge.get("stat_type")),
        "prizepicks_line": pp_line,
        "underdog_line": _num(edge.get("ud_line")),
        "best_venue": edge.get("best_venue"),
        "venue_note": edge.get("venue_note"),
        "engine_favoured_side": edge.get("play"),
        "engine_verdict": edge.get("verdict"),
        "win_probability": win_prob,
        "ev_percent": _num(edge.get("ev_percent")),
        "sharp_anchor_line": dk_line,
        "line_gap": line_gap,
        "edge_type": edge.get("edge_type"),
        "book_count": edge.get("book_count"),
        "trap_flags": flag_list,
        "team_form": form,
        "player_form": player_rate,
        "model_p": _num(edge.get("model_p")),
        "model_p_side": _num(edge.get("model_p_side")),
        "model_credibility": _num(edge.get("model_credibility")),
        "consensus_n": edge.get("consensus_n"),
        "consensus_tag": edge.get("consensus_tag"),
    }


def format_prompt(ctx: dict) -> str:
    opponent = ctx.get("opponent")
    matchup = ctx.get("matchup")
    if opponent:
        matchup_line = f"Matchup: {ctx.get('team') or 'player'} vs {opponent}"
    elif matchup:
        matchup_line = f"Matchup: {matchup}"
    else:
        matchup_line = "Matchup: opponent unknown — reason from the numbers only"

    stats_only = ctx.get("mode") == "stats_only"
    pp_line = ctx.get("prizepicks_line")
    ud_line = ctx.get("underdog_line")
    two_books = ud_line is not None and pp_line is not None and ud_line != pp_line

    lines = [
        f"Player: {ctx.get('player')} ({ctx.get('team') or 'team n/a'})",
        matchup_line,
        f"Market: {ctx.get('stat_type')}",
        f"PrizePicks line: {pp_line}",
    ]
    if two_books:
        lines.append(f"Underdog line: {ud_line}  (different from PrizePicks — call each one)")

    venue_note = ctx.get("venue_note")
    if venue_note:
        lines.append(f"Venue: {venue_note}")

    if stats_only:
        pf = ctx.get("player_form")
        lines.append("")
        if pf:
            lines.append(
                f"Player form ({pf.get('source', 'World Cup')}): {pf['per_game']} "
                f"{pf['stat']} per game over {pf['games']} match(es) ({pf['minutes']} min)."
            )
        else:
            lines.append("Player form: no tournament data yet for this stat — "
                         "reason from what you know about the player, and be cautious.")
    else:
        lines += [
            f"Engine's favoured side: {ctx.get('engine_favoured_side')}  "
            f"(verdict: {ctx.get('engine_verdict')})",
            "",
            "Sharp multi-book consensus:",
            f"  true win probability of the favoured side: {_pct(ctx.get('win_probability'))}",
            f"  EV over the 54.25% break-even: {_signed(ctx.get('ev_percent'))}",
            f"  books' anchor line: {ctx.get('sharp_anchor_line')}  "
            f"(gap vs PP line: {ctx.get('line_gap')})",
            f"  edge type: {ctx.get('edge_type')}",
            f"  books contributing: {ctx.get('book_count')}",
        ]
    form = ctx.get("team_form") or {}
    if form:
        lines.append("")
        lines.append("Tournament form so far (this World Cup — small samples, "
                     "weigh accordingly):")
        if form.get("team_attack"):
            lines.append(f"  {ctx.get('team')} attack ({form.get('team_games')}g): "
                         f"{form['team_attack']}")
        if form.get("team_style"):
            lines.append(f"  {ctx.get('team')} style: {form['team_style']}")
        if form.get("opponent_defense"):
            lines.append(f"  {ctx.get('opponent')} defense "
                         f"({form.get('opponent_games')}g): {form['opponent_defense']}")
        if form.get("opponent_defense_rank"):
            lines.append(
                "  Weigh the matchup explicitly: a shooter facing a top-8 defense "
                "needs a discount; facing a bottom-8 defense supports the over. "
                "Flag picks that ignore an extreme matchup."
            )

    model_p_side = ctx.get("model_p_side")
    if model_p_side is not None:
        credibility = ctx.get("model_credibility")
        confidence = (
            "low confidence" if credibility is None or credibility < 0.34
            else "medium confidence" if credibility < 0.67
            else "high confidence"
        )
        lines.append("")
        lines.append(
            f"Independent FBref form model puts P({ctx.get('engine_favoured_side', 'this side')}) "
            f"at {_pct(model_p_side)} ({confidence})."
        )

    consensus_tag = ctx.get("consensus_tag")
    if consensus_tag:
        tag_label = {
            "identified": f"identified ({ctx.get('consensus_n')} books at the exact line)",
            "single_book": "single book only",
            "degraded": "degraded (interpolated estimate)",
        }.get(consensus_tag, consensus_tag)
        lines.append(f"Book consensus quality: {tag_label}.")

    flags = ctx.get("trap_flags") or []
    lines.append("")
    if flags:
        lines.append("Trap flags raised by the engine:")
        lines.extend(f"  - {flag}" for flag in flags)
    else:
        lines.append("Trap flags: none.")
    lines.append("")
    two_book_note = (
        " Because the two lines differ, give a separate call for each: the player "
        "can clear the lower line but not the higher."
        if two_books else ""
    )
    if stats_only:
        lines.append(
            "Decide OVER, UNDER, or PASS from the form and matchup alone. There is no "
            "engine pick to compare to, so set agrees_with_engine to false." + two_book_note
        )
    else:
        lines.append(
            "Decide OVER, UNDER, or PASS. Set agrees_with_engine to whether your "
            "PrizePicks call matches the engine's favoured side." + two_book_note
        )
    return "\n".join(lines)


def _system_for(mode: str) -> str:
    return STATS_ONLY_SYSTEM_PROMPT if mode == "stats_only" else SYSTEM_PROMPT


def describe_request(edge: dict, mode: str = "full") -> dict:
    """Exactly what gets handed to Claude, for UI transparency. No model call.

    Returns the structured context the engine extracted, the rendered user
    prompt, the system instructions, and the required response shape.
    """
    ctx = build_context(edge, mode=mode)
    return {
        "context": ctx,
        "prompt": format_prompt(ctx),
        "system": _system_for(mode),
        "response_format": _json_instruction(ctx),
    }


def _pct(value):
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def _signed(value):
    try:
        return f"{float(value):+.1f}%"
    except (TypeError, ValueError):
        return "n/a"


def extract_recommendation(text: str) -> dict:
    """Parse the JSON verdict out of model text (tolerates fences/prose)."""
    payload = _first_json_object(text)
    pick = str(payload.get("pick", "PASS")).upper()
    if pick not in ("OVER", "UNDER", "PASS"):
        pick = "PASS"
    factors = payload.get("key_factors") or []
    if isinstance(factors, str):
        factors = [factors]
    try:
        confidence = int(payload.get("confidence", 50))
    except (TypeError, ValueError):
        confidence = 50
    underdog_pick = str(payload.get("underdog_pick", "")).upper()
    if underdog_pick not in ("OVER", "UNDER", "PASS"):
        underdog_pick = None
    return {
        "pick": pick,
        "underdog_pick": underdog_pick,
        "confidence": max(0, min(100, confidence)),
        "agrees_with_engine": bool(payload.get("agrees_with_engine", False)),
        "reasoning": str(payload.get("reasoning", "")).strip(),
        "key_factors": [str(f).strip() for f in factors if str(f).strip()],
    }


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
def analyze_play(edge: dict, backend: str | None = None, runner=None, mode: str = "full") -> dict:
    """Evaluate one edge with Claude. Returns the recommendation dict."""
    ctx = build_context(edge, mode=mode)
    backend = (backend or os.getenv("AI_BACKEND") or AI_BACKEND).lower()
    if backend == "auto":
        backend = "cli" if cli_available() else "sdk"
    if backend == "cli":
        return _analyze_via_cli(ctx, runner=runner)
    return _analyze_via_sdk(ctx)


def cli_available() -> bool:
    return shutil.which(os.getenv("AI_CLI_BINARY", AI_CLI_BINARY)) is not None


def _analyze_via_cli(ctx: dict, runner=None) -> dict:
    runner = runner or subprocess.run
    binary = os.getenv("AI_CLI_BINARY", AI_CLI_BINARY)
    model = _cli_model_for(ctx.get("mode", "full"))
    prompt = f"{format_prompt(ctx)}\n\n{_json_instruction(ctx)}"
    cmd = [
        binary, "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--append-system-prompt", _system_for(ctx.get("mode", "full")),
    ]
    result = runner(cmd, capture_output=True, text=True, timeout=240)
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    # The CLI returns a JSON envelope; on errors (e.g. a usage limit) the human
    # reason lives in its "result" field, not stderr — pull it out either way.
    text = stdout
    try:
        envelope = json.loads(stdout)
        if isinstance(envelope, dict):
            text = envelope.get("result") or envelope.get("error") or stdout
    except json.JSONDecodeError:
        pass

    if getattr(result, "returncode", 0) != 0:
        detail = (text or stderr or f"exit {result.returncode}").strip()
        raise RuntimeError(f"Claude CLI error: {detail[:300]}")
    return extract_recommendation(text)


def _analyze_via_sdk(ctx: dict) -> dict:
    try:
        import anthropic
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "The 'anthropic' package is required for the SDK backend. Install it, "
            "or set AI_BACKEND=cli to use your Claude subscription via the CLI."
        ) from error

    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError(
            "No Claude credentials. Use the `claude` CLI (AI_BACKEND=cli, your "
            "subscription) or set ANTHROPIC_API_KEY for the metered API."
        )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=_sdk_model_for(ctx.get("mode", "full")),
        max_tokens=AI_MAX_TOKENS,
        system=_system_for(ctx.get("mode", "full")),
        messages=[{"role": "user", "content": f"{format_prompt(ctx)}\n\n{_json_instruction(ctx)}"}],
    )
    text = "".join(b.text for b in message.content if getattr(b, "type", None) == "text")
    return extract_recommendation(text)


def _first_json_object(text: str) -> dict:
    """Return the first JSON object in `text`, ignoring any surrounding prose.

    Uses raw_decode so trailing text after the object (a common model habit)
    doesn't break parsing.
    """
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    # strict=False tolerates literal newlines/tabs the model sometimes leaves
    # unescaped inside the "reasoning" string, which would else break parsing.
    decoder = json.JSONDecoder(strict=False)
    index = 0
    while True:
        start = text.find("{", index)
        if start == -1:
            raise ValueError(f"No JSON object found in model output: {text[:200]!r}")
        try:
            obj, _ = decoder.raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
        index = start + 1
