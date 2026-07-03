# CLAUDE.md

Orientation for future Claude sessions working in this repo.

## What this is

A +EV matching engine that prices PrizePicks player props (NBA points; FIFA
World Cup 2026 shots/SOT/assists) against sharp sportsbook consensus
(DraftKings/FanDuel/BetMGM/Caesars via The-Odds-API) and returns a YES/LEAN/NO
verdict per play, plus a React/FastAPI dashboard. `README_AGENTS.md` is the
full spec; read it before making pipeline/verdict changes.

## Hot files

- `engine/matcher.py` — the verdict engine: pricing, trap flags, the
  evidence gate (`consensus_tag == 'identified'`), the AI matchup gate.
- `engine/settlement.py` — grades edges/bets vs ESPN box scores; force-void,
  DNP participation gate.
- `engine/config.py` — thresholds (`PLAY_THRESHOLD`, `BREAKEVEN_PROB`,
  `PP_MIN_MINUTES`, `STALE_SETTLE_MAX_HOURS`, `STALE_MAX_MINUTES`).
- `engine/ai_analyst.py` — Claude second-opinion prompt/context builder.
- `engine/glm_model.py` + `scripts/fit_glm_v2.py` — shadow model v2 (3-coef
  Poisson GLM); logs to the `model_predictions` sidecar, never gates verdicts.
- `storage/db_manager.py` — SQLite schema/migrations, `data/arb_engine.db`.
- `scripts/audit_dnp.py` — idempotent retro re-grade for the DNP gate.
- `api/main.py` — FastAPI backend; pipeline endpoints share one lock.

## Running things

```bash
source venv/bin/activate
python -m pytest -q                 # full test suite
python3 engine/matcher.py           # verdict board (needs scraped data first)
python3 engine/settlement.py        # grade yesterday's plays
./scripts/dev.sh                    # dashboard: FastAPI (8800) + Vite (5173)
```

DB lives at `data/arb_engine.db` (gitignored, like the rest of `data/`).

## The gauntlet and trust policy, in one line each

**Verdict gauntlet:** YES requires win prob ≥ 57%, no trap flags,
`consensus_tag == 'identified'` (≥2 sharp books at the exact line — soft
books/PrizePicks never count), AND the auto AI matchup check agreeing (its
own failure never blocks, only its disagreement downgrades); any gate failure
caps the play at LEAN.

**Trust policy:** a YES is the strongest available signal, sized small, not
a proven system — the pre-2026-07-01 lifetime record was corrupted by
settlement bugs (now fixed), so track the post-fix record separately and
don't size up until it holds >~57% over 30+ settled picks.

## Documentation maintenance

**Whenever you change code in this repo, check whether README.md,
README_AGENTS.md, CLAUDE.md, or `docs/` describe the changed behavior, and
update them in the same change. Documentation that contradicts code is a
bug.**
