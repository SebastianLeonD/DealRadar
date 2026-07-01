# Sports Arbitrage & +EV Matching Engine (NBA + FIFA World Cup 2026)
**Target Platform:** PrizePicks vs. Sharp Market Consensus (DK / FD / MGM / Caesars) + Underdog (line shopping only)
**Last Updated:** July 2026

## Multi-Sport: Switching Between NBA and the World Cup

One line in `.env` controls the whole pipeline:

```
ACTIVE_SPORT=world_cup    # or: nba
```

Sport definitions live in `engine/sports.py`. Each sport declares its
Odds-API key, prop markets, PrizePicks stat-name mapping, probability model
per stat, and ESPN settlement paths:

| | NBA | World Cup |
|---|---|---|
| Markets | points (+ alternates) | shots, shots on target, assists |
| Model | Normal (high-count) | Poisson (low-count) |
| Settlement | ESPN NBA box scores | ESPN `fifa.world` rosters |
| Injuries feed | ESPN NBA | none (trap flags still active) |
| Kickoff window | 48h | 36h (≈70 matches on the feed — credits!) |

Soccer notes:
- Books post soccer props as **milestones** ("Over 2" = 2+); the scraper
  normalizes integer lines to half-lines (`2.0` → `1.5`) so everything is
  consistent "X > line" semantics.
- Books post full ladders (shots 1+ through 6+), so PP's half-point lines
  usually hit a ladder point exactly — minimal model extrapolation.
- Soccer props post **late** (day of match) and DK may appear after FanDuel.
  Re-run Fetch Sharp Lines a few hours before kickoff.
- Settlement and CLV infer the sport per edge from its stat type, so NBA and
  World Cup history coexist in one database.

To trade more soccer stats (goals, saves, passes), extend the `world_cup`
entry in `engine/sports.py` — the PP parser prints any stat types it skipped
so you can see exactly what's on the board.

### Model-based pricing (stats no book posts)

Books only price soccer **shots, shots on target, goals, and assists**.
PrizePicks posts many more (saves, fouls, tackles, crosses, offsides), so for
those there is no market line to compare against. Instead the engine builds its
own projection from each player's **World Cup form**:

- `scrapers/fbref_stats.py` pulls every WC player's tournament stats from FBref
  via **soccerdata** (clears Cloudflare with undetected-chromedriver, caches
  locally). Writes `data/processed/fbref_wc_stats.json`.
- `engine/projections.py` maps a PP stat to its FBref field, projects the
  expected count next match as `total / matches played`, and runs it through the
  same push-adjusted Poisson the book path uses.
- `engine/matcher.py:price_model_edges` logs these as `edge_type='Form Model'`.

Caveats, by design:
- These plays are **always flagged** ("no betting market"), so they **cap at
  MAYBE** (LEAN). One-game samples add a second small-sample flag.
- A player needs **≥1 WC match played** to be modeled — opening-match teams
  produce no modeled plays until they kick off.
- FBref's World Cup feed is the simplified Opta box score, so **passes,
  dribbles, key passes, and clearances are NOT available** for the tournament
  (they exist only in domestic-league data).
- These stats have no ESPN settlement mapping yet, so modeled edges stay
  ungraded until that's added.

Run it from the **Update Data** page ("Update World Cup form") or
`python3 scrapers/fbref_stats.py`. Re-run after each matchday.

### Team form as AI context (not edges)

The same scraper also writes **team profiles** (`data/processed/fbref_wc_teams.json`):
each team's attack (shots, SoT, goals/game), defense (goals conceded, shots on
target faced, clean sheets), and style (fouls, crosses, tackles, offsides).

`engine/team_profiles.py` resolves a play's team + opponent (with a name-alias
map for FBref vs book naming) and `engine/ai_analyst.py` injects this into the
Claude prompt as **"Tournament form so far."** This matters because Claude's
training can't see the live tournament — feeding real form turns "is he in
form / is that defense leaky?" from a guess into a data-grounded read. The
prompt flags that samples are small early on, and these numbers are **context
only — never used to generate an edge**. Visible in the "What Claude sees"
toggle.

---

## What This Project Does

This engine prices every PrizePicks NBA **player points** line against a
**multi-book sharp consensus** and answers one question per play:

> **YES, LEAN, or NO?**

How it gets there:

1. **Fetch sharp lines** from The-Odds-API — main line *and* alternate-line
   ladders from DraftKings, FanDuel, BetMGM, and Caesars in one call per game.
2. **De-vig** prices with the power method (less biased than proportional on
   lopsided lines).
3. **Price the exact PP line.** Alternate ladders are interpolated through a
   fitted normal distribution, so "PP 24.5 vs DK 26.5" becomes a real
   probability instead of a vague "line value" flag.
4. **Trap detection.** Stale PP boards, big line gaps (breaking news), book
   disagreement, and ESPN injury status downgrade a play to LEAN.
5. **Verdicts (the gauntlet).** True win prob ≥ 57% **and** the play is
   `consensus_tag == 'identified'` (≥2 SHARP books quoting the exact PP
   line — soft books and PP itself never count) **and** no trap flags → math
   says **YES**. Above the 54.25% flex break-even → **LEAN**. Below → **NO**
   (not logged). A single sharp book at the exact line caps at LEAN with a
   visible reason, even at a high win prob.
6. **AI matchup gate (YES only).** Every play that still reads YES after step
   5 auto-runs the AI analyst once more, this time fed the opponent's defense
   rank (FBref shots-on-target conceded). If Claude disagrees or PASSes, the
   verdict downgrades to LEAN with the reasoning attached; if the check itself
   fails (CLI down, timeout), the YES is kept and flagged "AI check
   unavailable" — the gate can only downgrade, never block on infra failure.
7. **Best-venue line shopping.** Every edge also stamps `best_venue` /
   `venue_note` — PP vs. Underdog, whichever has the softer line for our side
   — shown on the board so you know where to place it.
8. **Slip suggestions.** YES plays are combined into power/flex structures and
   ranked by exact EV.
9. **Settlement.** ESPN box scores grade every logged edge WIN/LOSS/PUSH/VOID
   (see "Settlement Integrity" below), so the dashboard shows your real
   record and the model's calibration gap.

Plus the original **CLV tracking** against DraftKings closing lines.

---

## External APIs

| API | Used for | Key needed | Cost |
|---|---|---|---|
| The-Odds-API | Sharp lines + alternates, 4 books | `ODDS_API_KEY` in `.env` | ~2 credits/game (1 if alternates off) |
| ESPN injuries (public) | Trap flags on hurt players | None | Free |
| ESPN scoreboard/box scores (public) | Settling results | None | Free |

`.env` options:

```
ODDS_API_KEY=your_the_odds_api_key_here
SHARP_BOOKMAKERS=draftkings,fanduel,betmgm,williamhill_us   # optional
INCLUDE_ALTERNATE_LINES=1                                   # optional, set 0 to halve credits
```

---

## Directory Structure

```
Prizepicks/
├── .env                          # API key + options (NEVER commit this)
├── requirements.txt              # Python dependencies
├── api/
│   └── main.py                   # FastAPI backend for the React dashboard
├── frontend/                     # React + TypeScript + Tailwind UI
├── services/
│   └── pipeline.py               # Shared pipeline logic and DB queries
├── scrapers/
│   ├── draftkings_api.py         # Multi-book sharp lines + alternates (Odds-API)
│   ├── prizepicks_api.py         # Parses pasted PP raw JSON into flat format
│   ├── fbref_stats.py            # World Cup player + team form from FBref
│   ├── fbref_club_stats.py       # Club-season form (pre-tournament AI context)
│   ├── injuries_api.py           # ESPN injury report (free, cached 30 min)
│   └── results_api.py            # ESPN box scores (free)
├── engine/
│   ├── sports.py                 # Per-sport config (NBA / World Cup): markets, model, settlement
│   ├── probability.py            # De-vig, ladder interpolation, EV, slips
│   ├── projections.py            # Form-based pricing for stats no book posts
│   ├── team_profiles.py          # Team attack/defense/style form -> AI context
│   ├── matcher.py                # Verdict engine: prices PP lines, flags traps
│   ├── settlement.py             # Grades edges vs box scores, record report
│   ├── clv_report.py             # CLV report from logged edges
│   ├── ai_analyst.py             # Claude second-opinion OVER/UNDER/PASS call
│   └── name_matcher.py           # Fuzzy player name matching
├── storage/
│   └── db_manager.py             # SQLite: props ladders, edges, settlement
└── data/                         # SQLite DB + JSON staging (gitignored)
```

---

## First-Time Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then add your ODDS_API_KEY
python3 storage/db_manager.py init
```

Existing databases migrate automatically on first run (new columns + indexes).

---

## Daily Workflow

Always run from the **project root**.

```bash
# 1. Fetch sharp lines (multi-book + alternates)
python3 scrapers/draftkings_api.py

# 2. Save your PrizePicks board capture to data/raw/prizepicks_raw.json, then:
python3 scrapers/prizepicks_api.py

# 3. Get verdicts (auto-pulls injuries, logs edges, prints YES/LEAN board + best slips)
python3 engine/matcher.py

# 4. (Optional) Re-scrape sharp lines near tip-off, then check CLV
python3 engine/clv_report.py

# 5. Next morning: grade yesterday's plays against real box scores
python3 engine/settlement.py
```

Or run everything from the dashboard.

---

## Dashboard (React + FastAPI)

```bash
./scripts/dev.sh        # or run uvicorn (port 8800) + npm run dev separately
```

Open **http://localhost:5173**

| Page | Purpose |
|---|---|
| **Execution** | Pipeline buttons (incl. Settle Results), feed freshness, log |
| **Active Opportunities** | Verdict board: YES/LEAN badges, win % + EV, trap flags, settled results, record cards |
| **CLV Performance** | CLV metrics, 7-day chart, movement table |

---

## Verdict Rules (the gauntlet)

A **YES** must clear every gate below, in order. Failing any one caps the
verdict at LEAN (or NO); nothing downstream can push it back up to YES.

| Gate | Condition | On fail |
|---|---|---|
| 1. Math | True win prob ≥ 57% | `< 57%` and `≥ 54.25%` → **LEAN**; below 54.25% → **NO** (not logged) |
| 2. Trap flags | None of the flags below fired | any flag → **LEAN** |
| 3. Evidence | `consensus_tag == 'identified'` (≥2 **sharp** books at the exact PP line, from a *complete* DK/Odds-API fetch) | single sharp book / soft-book-only / interpolated / partial fetch (budget-truncated or a failed per-game call) → **LEAN**, flagged "Only one sharp book at this line — need 2+ to confirm a YES" |
| 4. AI matchup check | Claude's second opinion (opponent defense rank in context) agrees or PASSes-through on failure | Claude disagrees/PASSes → **LEAN** with its reasoning attached; Claude unreachable → **YES kept**, flagged "AI check unavailable" |

**Trap flags** (any one downgrades YES → LEAN):

- PP board captured 45+ min before the sharp data (stale board)
- Sharp books disagree by more than 7% on the probability
- Line gap of 2.5+ points vs the sharp anchor line (breaking-news risk)
- Player is Out / Doubtful / Questionable / Day-To-Day on the ESPN report

**54.25%** is the per-pick break-even for PrizePicks 5/6 flex slips. Slip EV
uses the payout tables in `engine/probability.py` — verify them in-app
occasionally; PrizePicks adjusts multipliers.

**"Identified" consensus** (gate 3) means ≥2 **sharp** books (any book not in
`SOFT_BOOKS`, currently just Underdog, and never PrizePicks itself) quote the
exact PP line — a soft-book-only or single-sharp-book play can look like a
great number and still never reach YES. This exists because one book's price
at an exact line is a pricing artifact, not a confirmed edge
(`engine/matcher.py:evaluate_player`).

**Trust policy:** treat every YES as the strongest signal the pipeline can
currently produce, sized small — not as a proven-profitable system. The
lifetime record (pre-fix) was corrupted by the bugs below, so it's tracked
separately from the **post-fix record** (since 2026-07-01, printed by
`engine/settlement.py`). Don't scale stake size up until the post-fix YES
bucket shows a hit rate materially above ~57% over 30+ settled picks — with
current volume that's a real number, not a guess.

---

## Settlement Integrity

Three bugs let bad grades into the record before 2026-07-01; all are fixed
and covered by tests, and a retro audit script exists for the DNP one:

- **Right-game kickoff resolution.** `engine/matcher.py:_resolve_kickoff`
  used to return the first game whose team-name substring matched — for a
  team that plays multiple tournament matches, that could resolve to a
  weeks-old fixture. It now collects every match, prefers the game closest to
  "now" (upcoming/in-progress over past), and only falls back to the latest
  past game if nothing is upcoming.
- **Force-void after 72h unsettled.** `STALE_SETTLE_MAX_HOURS = 72`
  (`engine/config.py`) existed but was never enforced. `settle_edges()` now
  force-voids (`storage/db_manager.py:force_void_edge`) any edge still
  unsettled 72h past its kickoff/flag anchor, so a box-score/name-match gap
  can't leave a play open (and out of the calibration pool) forever.
- **DNP participation gate.** ESPN's soccer box score exposes a binary
  `appearances` stat (1.0 = played at all, 0.0 = benched), mapped to a
  synthetic 0/90 "minutes" figure. `PP_MIN_MINUTES['world_cup'] = 1.0`
  (`engine/config.py`) means a benched player VOIDs instead of settling as an
  UNDER win. `python3 scripts/audit_dnp.py --dry-run` (then without the flag)
  retroactively re-grades already-settled rows against this gate — it's
  idempotent (a row is only touched while `pre_audit_result IS NULL`, and the
  pre-audit result is preserved once it fires), so re-running it after new
  settlements is safe.

**Pricing honesty**, same batch:

- **Dead ladders excluded.** `_drop_dead_books` drops any book's ladder whose
  game has already kicked off before pricing/consensus runs, so a finished
  match's stale-but-internally-consistent lines can't sneak into a new edge.
- **Quote staleness window.** `_drop_stale_books` drops a book if its
  `captured_at` is more than `STALE_MAX_MINUTES` (`engine/config.py`, = 15)
  older than the newest book for that player — relative freshness between
  books, not wall-clock age, so a normal "run the matcher an hour later"
  workflow isn't penalized.

---

## How Probabilities Are Computed

1. Each book's lines (main + alternates) form a **ladder** of
   (line, P(over)) points after de-vigging.
2. If the PP line sits between two ladder points, a normal distribution is
   fitted through the two nearest quantiles and evaluated at the PP line.
3. With a single point, the mean is solved from that anchor using an NBA
   points dispersion heuristic (`sigma ≈ 1.2 * sqrt(mu) + 1`).
4. The per-book probabilities are averaged into a consensus; the spread
   between books feeds trap detection.

One-sided alternate prices are de-vigged using half the book's two-way margin
measured at its main line.

---

## Database Tables

### `props` — line history from every scrape

Now keyed by `(player_name, stat_type, source, bookmaker, line)` so each
book's full alternate ladder is preserved. `commence_time` stores game start.

### `edges` — every flagged play

New columns: `win_prob`, `ev_percent`, `verdict`, `flags`, `book_count`,
`commence_time`, plus settlement fields `result` (WIN/LOSS/PUSH/VOID),
`actual_value`, `settled_at`, `settlement_status`, `void_reason`,
`force_voided_at`, `pre_audit_result` (retro DNP audit bookkeeping).

Also carries the shadow FBref Poisson model (`model_p`, `model_p_side`,
`model_credibility`, `model_n_matches`, `model_source` — logged alongside the
market number, never used to flag a verdict), the line-matched consensus
(`consensus_n`, `consensus_tag`), and line-shopping (`best_book`,
`best_venue`, `venue_note`, `ai_pick`, `ai_confidence` from the AI matchup
gate). All of these are surfaced in the UI and passed into the AI analyst's
context.

---

## Command Reference

| Command | What it does | API cost |
|---|---|---|
| `python3 scrapers/draftkings_api.py` | Multi-book sharp lines + alternates | ~2 credits/game |
| `python3 scrapers/prizepicks_api.py` | Parse pasted PP raw JSON | None |
| `python3 engine/matcher.py` | Verdict board + slip suggestions, logs edges | None (free ESPN injuries) |
| `python3 engine/settlement.py` | Grade edges vs box scores, record report | None (free ESPN) |
| `python3 engine/clv_report.py` | CLV report from logged edges | None |
| `python3 scrapers/injuries_api.py` | Refresh injury cache manually | None |
| `python3 scrapers/results_api.py 20260611` | Inspect box scores for a date | None |
| `python3 scripts/audit_dnp.py --dry-run` | Report already-settled rows a DNP participation gate would VOID (retro; idempotent) | None |
| `python3 scripts/audit_dnp.py` | Apply that re-grade | None |
| `./scripts/dev.sh` | Launch React dashboard + API | None |

---

## Closing Line Value (CLV)

Unchanged: positive CLV means the DK line moved in your favor after you
flagged the play. Re-scrape DK near tip-off, then run the report. CLV is
anchored to DraftKings only (not the consensus) for consistency.

---

## Things You Need to Know

- **Points only** for now. The probability engine is stat-agnostic; widening
  to rebounds/assists/threes means extending the scraper markets and the PP
  parser allowlist.
- **Always run from the project root** — scripts use relative paths.
- **Old PP boards linger** in the database. If a player shows a stale-board
  flag, that PP line came from an earlier paste — re-paste the current board.
- **Settlement waits 4 hours** after game start (or flag time) before grading,
  and force-VOIDs anything still unsettled 72h later (`STALE_SETTLE_MAX_HOURS`).
- All files under `data/` are gitignored.
- **Pipeline endpoints are serialized** — `api/main.py` holds a single lock so
  two pipeline actions (fetch/parse/matcher/settle/full) can't run at once and
  clobber the same JSON/SQLite state; a second call while one is running gets
  an "already running" error instead of queuing silently. Subprocess calls
  time out at 900s, JSON writes are atomic, and timestamp parsing is tz-safe
  (naive timestamps are treated as UTC) throughout the pipeline.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing ODDS_API_KEY` | Create `.env` from `.env.example` |
| `Could not find live.json` | Run `python3 scrapers/prizepicks_api.py` |
| No verdicts printed | Run scrapers first; both PP and sharp data must exist |
| PP players skipped | Name mismatch — check fuzzy match output |
| `No edges ready to settle` | Games haven't finished yet (4h grace period) |
| Injury feed unavailable | Cached copy is used; refresh later |
| Burning too many credits | Set `INCLUDE_ALTERNATE_LINES=0` or trim `SHARP_BOOKMAKERS` |

---

## Supported Betting Types

| Type | Status |
|---|---|
| Standard single-stat props (NBA: pts/reb/ast/threes; WC: shots/SOT/assists/goals/saves) | ✅ Priced + verdicts |
| First-half (1H) props | ✅ Derived via Poisson thinning, capped at LEAN |
| Combo props ("A + B") | ✅ Poisson leg sum, push-adjusted, capped at LEAN |
| Integer-line pushes | ✅ Win prob excludes refund mass |
| Binary scorer markets (anytime goal → 0.5 line) | ✅ Wide-margin de-vig |
| Demons & Goblins | ⏸ Parsed but NOT traded — PP's API exposes no payout multipliers; their lines bracket PP's own median (useful intel) |
| Flash sales / promos | ⏸ Fields detected (`is_promo`, `flash_sale_line_score`), detector not built |
| Live / in-game | ❌ Out of scope (speed game, not analysis game) |

## Engineering Backlog (the funnel plan)

1. **Trust gates** — ✅ *evidence gate shipped 2026-07-01*: YES now requires
   `consensus_tag='identified'` (≥2 sharp books), not just a high win prob.
   Still open: per-bucket (stat × verdict × edge type) settled ROI must be
   positive before that bucket can produce YES; auto-calibration correction
   from the post-fix record.
2. **AI deep-analysis stage** — ✅ *first slice shipped 2026-07-01*: every YES
   auto-runs one AI matchup check (opponent defense rank) before logging.
   Still open: lineup intel, news sweep, motivation context (dead rubbers!) →
   a fuller confirm/downgrade/kill dossier beyond the single matchup check.
3. **Demon/goblin payout tables** — dropped: PP's API exposes no payout
   multipliers for these, so goblin/demon EV is currently impossible to
   compute (see "Supported Betting Types" below).
4. **Correlation-aware slips** — same-game legs currently only flagged, not modeled
5. **Pre-game closing snapshot** — auto-tag last scrape before `commence_time` as true close
6. **Calibration curve UI** — predicted win % vs actual hit rate on the dashboard
7. **Slate filtering** — hide props whose `commence_time` has passed

---

## AI Analyst (ships backlog #2)

Every play that reaches YES through the math + evidence gates auto-runs
through the AI analyst once as the **AI matchup gate** (see Verdict Rules
above) before it's logged — that call is automatic and not optional. Beyond
that gate, the Opportunities page also surfaces plays (**YES / LEAN**) as
cards with an **Ask Claude** button for manual, on-demand second opinions —
nothing calls the model there until you click, so you choose which additional
plays to spend a call on. Claude gets
the play's full context — the sharp-consensus win probability, EV over
break-even, the anchor line vs the PrizePicks line, book count, every trap flag,
**and the matchup (the opponent, derived from the sharp board's game string)** —
and returns an independent **OVER / UNDER / PASS** call with confidence,
reasoning, and key factors. It's a second opinion that reads the warnings *and
weighs the opponent*: it reasons about how strong the other side is and whether
the player's team should control the game, a serious trap flag pushes it toward
PASS even when the math looks good, and it shows whether it **agrees with or
differs from** the engine's verdict.

Every pick also has a **"What Claude sees"** toggle that shows the exact prompt
(the play's facts) and the system instructions — no model call, full
transparency into what's being asked and how.

**Two analysis modes** (toggle next to the verdict chips):
- **Full** — the read described above, anchored to the sharp-book consensus.
- **PrizePicks-only** — drops all sportsbook data and judges the play from the
  *stats alone*: the player's per-game rate (FBref) plus the team form, no
  win%/EV. The "stats half" of the analysis — the right tool for the many PP
  props with no book line. Uses a separate system prompt
  (`STATS_ONLY_SYSTEM_PROMPT`) that leads from the player's rate, respects small
  samples, and defaults to PASS when there's no real basis. Pass `mode` to
  `/api/edges/analyze` and `/api/edges/prompt` (`"full"` | `"stats_only"`).

The player rate comes from `engine/projections.py:player_form`, which prefers
World Cup form and **falls back to club-season form** (`scrapers/fbref_club_stats.py`
→ `data/processed/fbref_club_stats.json`, Big-5 leagues, ~42% of a WC squad) so a
player has a number *before* their first tournament match. The prompt tags the
source ("World Cup" vs "club season 2025-26").

### PrizePicks Board (the full menu)

`scrapers/prizepicks_api.py` also writes the **complete** parsed board
(`data/processed/pp_board.json`) — every stat type, including ones no book prices
and the engine can't grade (Passes, Dribbles, Shots Assisted, Fantasy Score,
Clearances). `GET /api/prizepicks/board` groups these by stat type with a
`has_form_data` flag, and the **PrizePicks Board** tab lists them all with a
stats-only "Ask Claude" on each. Stats without a form feed are clearly marked
"no stats yet" — Claude can only give a general read there.

The board itself only lists **today's upcoming, unsettled plays**: settled
results and games that have already kicked off drop off automatically (your
lifetime record still counts them).

- **Runs on your Claude subscription.** `engine/ai_analyst.py` shells out to the
  logged-in `claude` CLI by default (`AI_BACKEND=auto`/`cli`) — no metered API
  key. Set `AI_BACKEND=sdk` + `ANTHROPIC_API_KEY` to use the metered API instead.
- **Endpoints:** `POST /api/edges/analyze` (takes an edge row, fills in the
  opponent if missing, returns the verdict + the opponent + the exact prompt
  `sent`). `POST /api/edges/prompt` returns just that `sent` payload with **no
  model call** — used by the "What Claude sees" toggle.
- **Tests:** `pip install -r requirements-dev.txt && python3 -m pytest tests/`
  (AI analyst + matchup + Kelly).

**Kelly stake sizing:** slip suggestions now also carry a fractional-Kelly stake
(`kelly_pct`) — the matcher tells you not just *which* slip but *how much* of
your bankroll to put on it.

**Shadow-model scorer:** `engine/shadow_score.py` is a lightweight, standalone
Brier readout — not a gate — that answers the one question the FBref shadow
model exists for: is `model_p` closer to reality than `consensus_p`/`baseline_p`
on the same settled edges? Run `python engine/shadow_score.py` any time; its
headline numbers also get appended (best-effort, non-fatal) to `python
engine/settlement.py` output after the post-fix record.
