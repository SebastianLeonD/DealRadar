# Sports Arbitrage & +EV Matching Engine (NBA Prop Core)
**Target Platform:** PrizePicks vs. DraftKings (Sharp Market Consensus)  
**Last Updated:** May 2026

---

## What This Project Does

This engine finds mathematical edges on NBA **player points** by comparing PrizePicks lines against **de-vigged true probabilities** from DraftKings (via The-Odds-API). It flags two types of plays:

1. **Line discrepancies** — PrizePicks line differs from the sharp book (auto OVER/UNDER)
2. **+EV juice** — Same line, but true probability exceeds the PrizePicks break-even threshold (54.25%)

Every flagged edge is **logged to SQLite** for historical tracking and **Closing Line Value (CLV)** analysis.

---

## Directory Structure

```
Prizepicks/
├── .env                          # Your API key (NEVER commit this)
├── .env.example                  # Template for setup
├── requirements.txt              # Python dependencies
├── scrapers/
│   ├── draftkings_api.py         # Fetches sharp lines from The-Odds-API
│   └── prizepicks_api.py         # Parses pasted PP raw JSON into flat format
├── engine/
│   ├── matcher.py                # Finds edges, fuzzy name match, logs to DB
│   ├── clv_report.py             # CLV report from logged edges
│   └── name_matcher.py           # Fuzzy player name matching
├── storage/
│   └── db_manager.py             # SQLite ingestion, props + edges tables
├── data/
│   ├── arb_engine.db             # Local SQLite database (gitignored)
│   ├── raw/
│   │   └── prizepicks_raw.json   # Pasted PrizePicks API dump (gitignored)
│   └── processed/
│       ├── draftkings_data.json  # Flattened sharp lines (gitignored)
│       └── live.json             # Parsed PP points board (gitignored)
└── local_test.py                 # Pretty-prints DraftKings probabilities
```

---

## First-Time Setup

Run these once from the **project root** (`Prizepicks/`):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Add your Odds API key to `.env`:

```
ODDS_API_KEY=your_the_odds_api_key_here
```

Initialize the database:

```bash
python3 storage/db_manager.py init
```

---

## Step-by-Step: Full Analysis Workflow

Always run from the **project root**.

### 1. Fetch DraftKings sharp lines

```bash
python3 scrapers/draftkings_api.py
```

- Fetches `player_points` for today's NBA slate (~1 API credit per game)
- De-vigs American odds into true Over/Under probabilities
- Saves to `data/processed/draftkings_data.json`

### 2. Paste PrizePicks raw JSON

Save your PrizePicks board capture to:

```
data/raw/prizepicks_raw.json
```

There is **no live PP scraper** — manual paste is intentional.

### 3. Parse PrizePicks points board

```bash
python3 scrapers/prizepicks_api.py
```

- Extracts **single-stat Points only** (excludes Fantasy Score, PRA, combos)
- Saves to `data/processed/live.json`

### 4. Run the matcher (find + log edges)

```bash
python3 engine/matcher.py
```

- Syncs JSON staging → SQLite
- Fuzzy-matches PP player names to DK names
- Compares latest `player_points` lines
- Prints flagged edges
- **Logs every edge to the `edges` table**

### 5. Re-scrape DK closer to tip-off (recommended for CLV)

```bash
python3 scrapers/draftkings_api.py
```

This captures line movement before game time.

### 6. Run the CLV report

```bash
python3 engine/clv_report.py
```

- Compares your logged PP line vs the **latest DK line**
- Shows line movement and CLV per play
- Summarizes positive CLV rate and average CLV

---

## Command Reference

| Command | What it does | API cost |
|---|---|---|
| `python3 scrapers/draftkings_api.py` | Fetch DK sharp lines → JSON staging | ~1 credit/game |
| `python3 scrapers/prizepicks_api.py` | Parse pasted PP raw JSON → `live.json` | None |
| `python3 storage/db_manager.py ingest` | Manual JSON → SQLite sync | None |
| `python3 engine/matcher.py` | Find edges, fuzzy match, log to DB | None |
| `python3 engine/clv_report.py` | CLV report from logged edges | None |
| `python3 local_test.py` | Inspect DK true probabilities | None |

---

## Database Tables

### `props` — line history from every scrape

| Column | Purpose |
|---|---|
| `player_name`, `line`, `source` | DK or PP line snapshot |
| `true_over_prob`, `true_under_prob` | DK de-vigged probs (NULL for PP) |
| `captured_at` | When the line was scraped |

Upsert key: `(player_name, stat_type, source, line)`. Line changes create new historical rows.

### `edges` — every flagged play from the matcher

| Column | Purpose |
|---|---|
| `pp_player_name`, `dk_player_name` | Names used (may differ if fuzzy matched) |
| `play`, `pp_line`, `dk_line_at_flag` | What you would bet and at what numbers |
| `edge_type` | Line Discrepancy or +EV Odds Juice |
| `flagged_at` | When the edge was detected |

---

## Edge Detection Rules

| Condition | Play |
|---|---|
| PP line < DK line | **OVER** |
| PP line > DK line | **UNDER** |
| PP line = DK line AND True Over Prob ≥ 54.25% | **OVER** |
| PP line = DK line AND True Under Prob ≥ 54.25% | **UNDER** |

**54.25%** is the break-even threshold for PrizePicks 5/6 flex slips.

---

## Fuzzy Name Matching

PrizePicks and DraftKings sometimes spell names differently (e.g. `"PJ Washington"` vs `"P.J. Washington"`).

`engine/name_matcher.py` normalizes names and fuzzy-matches at **88% similarity**. When a fuzzy match is used, the matcher prints:

```
Fuzzy matched 1 player name(s):
  PJ Washington -> P.J. Washington (92%)
```

---

## Closing Line Value (CLV)

**CLV** measures whether you got a better number than the market settled at.

| Play | Positive CLV means |
|---|---|
| **OVER** | Latest DK line moved **above** your PP line |
| **UNDER** | Latest DK line moved **below** your PP line |

**Best practice:**
1. Run matcher when you see edges → edges logged with `dk_line_at_flag`
2. Re-scrape DK closer to tip-off
3. Run `python3 engine/clv_report.py`

The report shows `DK@FLAG` (line when edge was found), `DK NOW` (latest scrape), `MOVE`, and `CLV`.

---

## Things You Need to Know

### Points only

Both scrapers and the matcher are locked to **`player_points`**. Fantasy Score, PRA, and combo props are excluded at parse time.

### Always run from the project root

All scripts use relative paths like `data/processed/...`.

### Duplicate DraftKings lines

The matcher picks the DK line **closest** to the PP line when alternates exist.

### Gitignored data

All files under `data/raw/`, `data/processed/`, and `data/*.db` are gitignored. Generate locally by running the pipeline.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing ODDS_API_KEY` | Create `.env` from `.env.example` |
| `Could not find live.json` | Run `python3 scrapers/prizepicks_api.py` |
| `No logged edges found` | Run `python3 engine/matcher.py` first |
| PP players skipped | Name mismatch — check fuzzy match output |
| CLV all zeros on MOVE | Re-scrape DK; lines haven't moved since flag |

---

## Engineering Backlog

1. **Multi-market scaling** — Rebounds, assists, threes with stat-type-aware matching
2. **Edge deduplication** — Collapse repeat flags for same player/play within a session
3. **Pre-game closing snapshot** — Auto-tag last DK scrape before game start as "closing line"
