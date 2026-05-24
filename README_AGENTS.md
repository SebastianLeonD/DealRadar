# Sports Arbitrage & +EV Matching Engine (NBA Prop Core)
**Target Platform:** PrizePicks vs. DraftKings (Sharp Market Consensus)  
**Last Updated:** May 2026

---

## What This Project Does

This engine finds mathematical edges on NBA player props by comparing PrizePicks lines against **de-vigged true probabilities** from DraftKings (via The-Odds-API). It flags two types of plays:

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
│       ├── prizepicks_live.json  # Parsed live PP board (gitignored)
│       └── prizepicks_mock.json  # Small test board (tracked in git)
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

Installs `requests` (API calls) and `python-dotenv` (loads `.env`).

### 3. Configure your API key

```bash
cp .env.example .env
```

Open `.env` and set your key:

```
ODDS_API_KEY=your_the_odds_api_key_here
```

Get a key at [the-odds-api.com](https://the-odds-api.com/).

**Important:** If this repo was ever committed with a hardcoded key, **revoke that key** in the dashboard and generate a new one. The old key may still exist in git history.

---

## Step-by-Step: Run a Full Analysis

Always run commands from the **project root**. Paths are relative to that directory.

### Path A — Quick test with mock data (no API calls)

Use this to verify the matcher logic without spending API credits.

**Step 1 — Activate the environment**

```bash
source venv/bin/activate
```

**Step 2 — Run the matcher against the mock board**

```bash
python3 engine/matcher.py
```

**What it does:** Reads `data/processed/prizepicks_mock.json` (4 test players) and compares them against the cached `data/processed/draftkings_data.json`. Prints a table of flagged edges.

**Expected output:** A table with columns `PLAYER | PLAY | PP LINE | DK LINE | PROBABILITY/EDGE | TYPE | TEAM`.

---

### Path B — Full live analysis (DraftKings + PrizePicks)

Use this when you want real sharp lines matched against a real PrizePicks board.

**Step 1 — Activate the environment**

```bash
source venv/bin/activate
```

**Step 2 — Fetch fresh DraftKings sharp lines**

```bash
python3 scrapers/draftkings_api.py
```

**What it does:**
- Calls The-Odds-API for today's NBA games (0 credits)
- Fetches `player_points` props from DraftKings for each game (1 credit per game)
- De-vigs American odds into true Over/Under probabilities
- Saves flattened output to `data/processed/draftkings_data.json`

**Cost:** ~1 API credit per game on the slate.

**Step 3 — (Optional) Inspect the sharp data**

```bash
python3 local_test.py
```

**What it does:** Loads `draftkings_data.json`, sorts props by highest true probability, and prints a formatted terminal table. Useful for sanity-checking the scrape before matching.

**Step 4 — Get PrizePicks data**

You need a raw PrizePicks JSON dump saved as:

```
data/raw/prizepicks_raw.json
```

Place or replace that file with your latest capture, then parse it:

```bash
python3 scrapers/prizepicks_api.py
```

**What it does:**
- Reads the raw JSON:API payload from `data/raw/prizepicks_raw.json`
- Extracts **single-stat Points only** (excludes Fantasy Score, PRA, combos, and multi-player slips)
- Saves to `data/processed/prizepicks_live.json` as `player_points`

**Step 5 — Point the matcher at live PrizePicks data**

Open `engine/matcher.py` and change line 3:

```python
PRIZEPICKS_FILE = 'data/processed/prizepicks_live.json'
```

(Use `prizepicks_mock.json` again when you want to go back to offline testing.)

**Step 6 — Run the analysis**

```bash
python3 engine/matcher.py
```

**What it does:** For each PrizePicks player, finds the closest matching DraftKings line (handles duplicate/alternate lines), applies edge rules, and prints flagged plays.

---

## Command Reference

| Command | What it does | API cost |
|---|---|---|
| `python3 scrapers/draftkings_api.py` | Fetch DK sharp lines → `draftkings_data.json` | ~1 credit/game |
| `python3 scrapers/prizepicks_api.py` | Parse raw PP JSON → `prizepicks_live.json` | None |
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

### PrizePicks output (`data/processed/prizepicks_live.json` / `prizepicks_mock.json`)

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

### Always run from the project root

All scripts use relative paths like `data/processed/...`. If you run from inside `scrapers/` or `engine/`, files will be written or read from the wrong place.

### API key security

- The key lives in `.env` only — never hardcode it in Python files
- `.env` is gitignored; `.env.example` is the safe template to commit
- Rotate your key if it was ever exposed in git history or pushed to GitHub

### Duplicate DraftKings lines

DraftKings sometimes has multiple lines for the same player (e.g. main line 17.5 and alternate 13.5). The matcher stores **all** lines per player and picks the one **closest** to the PrizePicks line before comparing. This prevents false edges from silently using the wrong line.

### Stat type filtering (points only)

- Both scrapers and the matcher are locked to **`player_points`** for now
- PrizePicks raw data includes Fantasy Score, PRA, Pts+Rebs, and combo props — these are **excluded** at parse time
- Only exact raw stat type `"Points"` is ingested (not `"Points (Combo)"`)
- The matcher double-checks `stat_type` / `Stat` on both sides before comparing

### Gitignored vs tracked files

| File | In git? | Why |
|---|---|---|
| `data/processed/prizepicks_mock.json` | Yes | Small test fixture |
| `data/processed/draftkings_data.json` | No | Live/scraped data |
| `data/processed/prizepicks_live.json` | No | Live/scraped data |
| `data/raw/prizepicks_raw.json` | No | Large raw dump |
| `.env` | No | Secrets |

### API credit discipline

- **Do not** call The-Odds-API inside `matcher.py` or utility scripts
- Fetch once with `draftkings_api.py`, then run the matcher offline against the cached file
- Re-fetch only when you need fresh lines for a new slate

---

## Edge Detection Rules

### Tier A — Line discrepancy (automatic)

| Condition | Play |
|---|---|
| PP line < DK line | **OVER** |
| PP line > DK line | **UNDER** |

### Tier B — Same line (+EV juice)

| Condition | Play |
|---|---|
| PP line = DK line AND True Over Prob ≥ 54.25% | **OVER** |
| PP line = DK line AND True Under Prob ≥ 54.25% | **UNDER** |

**54.25%** is the break-even threshold for PrizePicks 5/6 flex slips.

---

## Technical Operational Rules (For Agents)

### DO NOT:
* **DO NOT make redundant API calls.** Never put API execution loops inside matching or utility tasks.
* **DO NOT commit `.env` or live data files.** Only `prizepicks_mock.json` is tracked under `data/processed/`.
* **DO NOT introduce external player database mappings.** Team names come from the PrizePicks payload dynamically.
* **DO NOT hardcode API keys.** Use `os.getenv('ODDS_API_KEY')` via `python-dotenv`.

### DO:
* **DO run all scripts from the project root.**
* **DO maintain `.ljust()` alignment** in terminal output for scannable tables.
* **DO enforce key capitalization** — DK uses `Player`, `Line`, `True_Over_Prob`; PP uses `name`, `line`, `stat_type`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `Missing ODDS_API_KEY` | Create `.env` from `.env.example` and add your key |
| `Could not find data/processed/draftkings_data.json` | Run `python3 scrapers/draftkings_api.py` first |
| `Could not find prizepicks_mock.json` | File should exist in git; run `git checkout data/processed/prizepicks_mock.json` |
| `Missing raw file: data/raw/prizepicks_raw.json` | Save a PrizePicks API dump to that path, then run `prizepicks_api.py` |
| No edges found | Normal — means no props cleared the threshold. Check player name mismatches or stale cache. |
| Wrong line compared for a player | Duplicate DK lines — matcher uses closest line; verify with `local_test.py` |

---

## Engineering Backlog

1. **Automated name normalization** — Handle "PJ Washington" vs "P.J. Washington" with fuzzy matching
2. **Multi-market scaling** — Expand both scrapers to rebounds, assists, threes with stat-type-aware matching
3. **CLI flag for matcher** — `--source mock|live` instead of editing `PRIZEPICKS_FILE` manually
4. **Live PrizePicks API scraper** — Replace manual JSON dump with automated board fetch
