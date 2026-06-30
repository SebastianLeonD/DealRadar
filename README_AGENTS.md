# Sports Arbitrage & +EV Matching Engine (NBA + FIFA World Cup 2026)
**Target Platform:** PrizePicks vs. Sharp Market Consensus (DK / FD / MGM / Caesars)
**Last Updated:** June 2026

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
5. **Verdicts.** True win prob ≥ 57% with no flags → **YES**. Above the 54.25%
   flex break-even → **LEAN**. Below → **NO** (not logged).
6. **Slip suggestions.** YES plays are combined into power/flex structures and
   ranked by exact EV.
7. **Settlement.** ESPN box scores grade every logged edge WIN/LOSS/PUSH, so
   the dashboard shows your real record and the model's calibration gap.

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

## Verdict Rules

| Condition | Verdict |
|---|---|
| True win prob ≥ 57% and no trap flags | **YES** |
| Above 54.25% break-even (or strong but flagged) | **LEAN** |
| Below 54.25% break-even | **NO** (not logged) |

**Trap flags** (any one downgrades YES → LEAN):

- PP board captured 45+ min before the sharp data (stale board)
- Sharp books disagree by more than 7% on the probability
- Line gap of 2.5+ points vs the sharp anchor line (breaking-news risk)
- Player is Out / Doubtful / Questionable / Day-To-Day on the ESPN report

**54.25%** is the per-pick break-even for PrizePicks 5/6 flex slips. Slip EV
uses the payout tables in `engine/probability.py` — verify them in-app
occasionally; PrizePicks adjusts multipliers.

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
`commence_time`, plus settlement fields `result` (WIN/LOSS/PUSH),
`actual_value`, `settled_at`.

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
- **Settlement waits 4 hours** after game start (or flag time) before grading.
- All files under `data/` are gitignored.

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

1. **Trust gates** — per-bucket (stat × verdict × edge type) settled ROI must be
   positive before that bucket can produce YES; auto-calibration correction from record
2. **AI deep-analysis stage** — for plays surviving the math gates: lineup intel,
   news sweep, motivation context (dead rubbers!) → confirm/downgrade/kill dossier
3. **Demon/goblin payout tables** — encode from the app UI to make them tradeable
4. **Correlation-aware slips** — same-game legs currently only flagged, not modeled
5. **Pre-game closing snapshot** — auto-tag last scrape before `commence_time` as true close
6. **Calibration curve UI** — predicted win % vs actual hit rate on the dashboard
7. **Slate filtering** — hide props whose `commence_time` has passed

---

## AI Analyst (ships backlog #2)

On the Opportunities page, the plays the engine likes (**YES / MAYBE**) are
surfaced as cards and every row has an **Ask Claude** button — nothing calls the
model until you click, so you choose which plays to spend a call on. Claude gets
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
