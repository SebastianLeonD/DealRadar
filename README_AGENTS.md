# Sports Arbitrage & +EV Matching Engine (NBA Prop Core)
**Target Platform:** PrizePicks vs. DraftKings (Sharp Market Consensus)  
**Last Updated:** May 2026

---

## 1. Project Context & Current State
This software identifies mathematical edges in the player prop markets by cross-referencing live projection lines from Daily Fantasy Sports (DFS) sites against de-vigged true probabilities calculated from sharp sportsbooks.

### Directory Structure
```
data/
  raw/          # Unprocessed scraper output
  processed/    # Flattened, engine-ready datasets
scrapers/       # Data ingestion scripts (sportsbooks, DFS boards)
engine/         # Matching, edge detection, and alert logic
```

### Current Implementation Status:
*   **Data Architecture:** Local pipeline operating entirely offline using static cache layers to completely preserve API limits during testing cycles.
*   **`scrapers/draftkings_api.py`:** Fetches live events and player prop data (currently targeting NBA `player_points`) via The-Odds-API. Processes nested data structures, strips the market hold (de-vigs American odds to find true probability), flattens the records, and outputs a clean master file to `data/processed/draftkings_data.json`.
*   **`local_test.py`:** An optimization testing tool that reads the flattened `data/processed/draftkings_data.json` cache and formats it left-justified for terminal inspection.
*   **`data/processed/prizepicks_mock.json`:** A simulated mock snapshot of the PrizePicks board used to safe-test edge logic without requiring continuous live scraping injections.
*   **`engine/matcher.py`:** Core analysis script. Ingests the flat sharp data and the PrizePicks lines, maps players dynamically by name string, enforces threshold screening, and generates a filtered alert log.

---

## 2. Technical Operational Rules

### Core Betting Mathematics (De-Vigging Formula)
All probability evaluations must pass through a two-step fair-value calculator to eliminate sportsbook juice ($Hold$):

1. **Implied Probability calculation:**
$$Implied\ Prob = \begin{cases} \frac{|American\ Odds|}{|American\ Odds| + 100} & \text{if Odds } < 0 \\ \frac{100}{American\ Odds + 100} & \text{if Odds } > 0 \end{cases}$$

2. **Fair-Value Normalization:**
$$True\ Prob_{Over} = \frac{Implied_{Over}}{Implied_{Over} + Implied_{Under}}$$

### Threshold Constraints
*   **The Fixed Payout Barrier:** PrizePicks uses a fixed payout structure (e.g., standard 5-leg/6-leg flex slips require an individual prop win rate higher than **54.25%** to break even mathematically).
*   **Alert Rules:** 
    *   *Identical Lines:* Flag only if $True\ Prob_{Over}$ or $True\ Prob_{Under} \ge 54.25\%$.
    *   *Line Discrepancies:* If PrizePicks Line is less than DraftKings Line $\rightarrow$ Auto-Flag **OVER**. If PrizePicks Line is greater than DraftKings Line $\rightarrow$ Auto-Flag **UNDER**.

---

## 3. Strict Execution Directives for Agents

### DO NOT:
*   **DO NOT make redundant API calls.** Never put API execution loops inside matching or utility tasks. The `data/processed/draftkings_data.json` file is an immutable mock cache for script development. Use it exclusively until logic passes validation.
*   **DO NOT introduce external player database mappings.** Do not hardcode dictionaries mapping players to teams. The system design solves this implicitly by extracting team names dynamically from the DFS payload side during the merge phase.
*   **DO NOT write nested XML components inside Markdown or layouts.** Keep table blocks completely clean of complex markup to avoid compiler crashes.

### DO:
*   **DO maintain strict string spacing alignment.** Use `.ljust()` tracking for shell print outputs (`.ljust(25)` for players, `.ljust(15)` for stat tags) to keep diagnostic readouts visually scannable in the terminal.
*   **DO enforce precise key capitalization.** Remember that intermediate pipeline arrays capitalize structural variables (`Line`, `Player`, `True_Over_Prob`) while raw scraping arrays use platform-specific formatting. Double-check keys before deploying new compare loops to prevent `KeyError` crashes.

---

## 4. Next-Action Engineering Backlog

1.  **Automated Text Normalization:** Build a robust name-matching sanitizer (e.g., handling "Karl-Anthony Towns" vs. "Karl-Anthony Towns " or "PJ Washington" vs. "P.J. Washington") using Levenshtein distance thresholds or clean regex stripping to prevent mapping drops.
2.  **Multi-Market Scaling:** Expand `MARKET` params beyond `player_points` to support simultaneous ingestion and comparison of `player_rebounds`, `player_assists`, and `player_threes`.
3.  **Live DFS Ingestion:** Build out the live retrieval script for real-time PrizePicks board ingestion to replace the `data/processed/prizepicks_mock.json` testing mock layer.
