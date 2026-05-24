# Sports Arbitrage & +EV Matching Engine (NBA Prop Core)
**Target Platform:** PrizePicks vs. DraftKings (Sharp Market Consensus)  
**Last Updated:** May 2026

---

## What This Project Does

This engine finds mathematical edges on NBA **player points** by comparing PrizePicks lines against **de-vigged true probabilities** from DraftKings (via The-Odds-API). It flags two types of plays:

1. **Line discrepancies** — PrizePicks line differs from the sharp book (auto OVER/UNDER)
2. **+EV juice** — Same line, but true probability exceeds the PrizePicks break-even threshold (54.25%)

---

## Directory Structure

```
Prizepicks/
├── .env                          # Your API key (NEVER commit this)
├── .env.example                  # Template for setup
├── requirements.txt              # Python dependencies
├── scrapers/
│   ├── draftkings_api.py         # Fetches sharp lines from The-Odds-API
│   └── prizepicks_api.py         # Parses raw PrizePicks JSON into flat format
├── engine/
│   └── matcher.py                # Compares PP vs DK and prints edge alerts
├── data/
│   ├── raw/
│   │   └── prizepicks_raw.json   # Unprocessed PrizePicks API dump (gitignored)
│   └── processed/
│       ├── draftkings_data.json  # Flattened sharp lines (gitignored)
│       └── live.json             # Parsed PP points board (gitignored)
├── local_test.py                 # Pretty-prints DraftKings probabilities
└── manual_parse.py               # Legacy parser (use prizepicks_api.py instead)
```

---

## First-Time Setup

Run these once from the **project root** (`Prizepicks/`):

### 1. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure your API key

```bash
cp .env.example .env
```

Open `.env` and set your key:

```
ODDS_API_KEY=your_the_odds_api_key_here
```

Get a key at [the-odds-api.com](https://the-odds-api.com/).

---

## Step-by-Step: Run a Full Analysis

Always run commands from the **project root**.

**Step 1 — Activate the environment**

```bash
cd "/Users/sebastianleon/Documents/Code Portfolio/Prizepicks"
source venv/bin/activate
```

**Step 2 — Fetch fresh DraftKings sharp lines**

```bash
python3 scrapers/draftkings_api.py
```

- Calls The-Odds-API for today's NBA games (0 credits)
- Fetches `player_points` props from DraftKings (1 credit per game)
- De-vigs American odds into true Over/Under probabilities
- Saves to `data/processed/draftkings_data.json`

**Step 3 — (Optional) Inspect the sharp data**

```bash
python3 local_test.py
```

**Step 4 — Paste PrizePicks raw JSON**

Save your PrizePicks API dump to:

```
data/raw/prizepicks_raw.json
```

**Step 5 — Parse PrizePicks points board**

```bash
python3 scrapers/prizepicks_api.py
```

- Reads `data/raw/prizepicks_raw.json`
- Extracts **single-stat Points only** (excludes Fantasy Score, PRA, combos, multi-player slips)
- Saves to `data/processed/live.json` as `player_points`

**Step 6 — Run the matcher**

```bash
python3 engine/matcher.py
```

- Reads `data/processed/live.json` and `data/processed/draftkings_data.json`
- Matches `player_points` on both sides only
- Picks the closest DraftKings line when duplicates exist
- Prints flagged edges

---

## Command Reference

| Command | What it does | API cost |
|---|---|---|
| `python3 scrapers/draftkings_api.py` | Fetch DK sharp lines → `draftkings_data.json` | ~1 credit/game |
| `python3 scrapers/prizepicks_api.py` | Parse raw PP JSON → `live.json` | None |
| `python3 engine/matcher.py` | Compare PP vs DK and print edges | None |
| `python3 local_test.py` | Pretty-print all DK true probabilities | None |

---

## Data File Schemas

### DraftKings output (`data/processed/draftkings_data.json`)

```json
{
  "Player": "Jalen Brunson",
  "Game": "New York Knicks @ Cleveland Cavaliers",
  "Stat": "player_points",
  "Line": 25.5,
  "True_Over_Prob": 50.21,
  "True_Under_Prob": 49.79
}
```

### PrizePicks output (`data/processed/live.json`)

```json
{
  "name": "Jalen Brunson",
  "team": "New York Knicks",
  "stat_type": "player_points",
  "line": 25.5
}
```

---

## Things You Need to Know

### Points only

- Both scrapers and the matcher are locked to **`player_points`**
- PrizePicks raw data includes Fantasy Score, PRA, Pts+Rebs, and combo props — **excluded** at parse time
- Only exact raw stat type `"Points"` is ingested (not `"Points (Combo)"`)

### Always run from the project root

All scripts use relative paths like `data/processed/...`.

### Duplicate DraftKings lines

The matcher stores all lines per player and picks the one **closest** to the PrizePicks line before comparing.

### Gitignored data

All files under `data/raw/` and `data/processed/` are gitignored. Generate them locally by running the scrapers.

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

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing ODDS_API_KEY` | Create `.env` from `.env.example` and add your key |
| `Could not find data/processed/draftkings_data.json` | Run `python3 scrapers/draftkings_api.py` first |
| `Could not find data/processed/live.json` | Run `python3 scrapers/prizepicks_api.py` first |
| `Missing raw file: data/raw/prizepicks_raw.json` | Save a PrizePicks API dump to that path |
| No edges found | Normal if nothing clears the threshold — check stale cache or name mismatches |

---

## Engineering Backlog

1. **Automated name normalization** — Handle "PJ Washington" vs "P.J. Washington" with fuzzy matching
2. **Multi-market scaling** — Expand both scrapers to rebounds, assists, threes with stat-type-aware matching
3. **Live PrizePicks API scraper** — Replace manual JSON dump with automated board fetch
