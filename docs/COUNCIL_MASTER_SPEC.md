# PrizePicks Engine — Council-Ratified Master Specification

> Status: **UNANIMOUS — 6/6 council lenses signed off, 0 open objections.**
> Produced by an adversarial LLM council (51-agent design + challenge run; 21-agent scoped resolution/ratification run).
> Lenses: quantitative modeling · sportsbook microstructure · multi-sport expansion · data engineering · ML/calibration · risk/portfolio.

## North-star vision

A measurement-first PrizePicks +EV engine whose entire value proposition is an honest firewall between IDENTIFIED quantities (recompute-attributable from market data: per-book two-sided de-vig, equal-weight no-vig consensus, CLV vs a captured closing snapshot) and ASSERTED quantities (anything resting on a chosen distributional shape, a sharpness/vig weighting, or a sigma form). Every probability that reaches bet selection is stamped with its provenance (devig_method, sigma_source, consensus_n, snapshot_tag, market_type) and is gated behind PER-REGIME, game-clustered, walk-forward calibration against PrizePicks-rule-aligned settled outcomes. We do not ship a number we cannot recompute and cannot prove out-of-sample. Sophistication (ladder sigma, push math, Normal shape layer, multi-book consensus, multi-sport seam) is preserved but each piece ships behind its own calibration gate and its own honesty label; nothing asserted is allowed to flag a bet until it out-Briers the identified null on held-out, game-clustered data. The headline ground truth is the multi-book no-vig CONSENSUS close, not any single book.

## The firewall (the core discipline)
Every probability that reaches bet selection is stamped with its provenance and classified on one side of a firewall:
- **IDENTIFIED** — recompute-attributable purely from market data (per-book de-vig, line-matched consensus, CLV vs captured close). Ships in Phase 1.
- **ASSERTED / GATED** — rests on a chosen shape, weight, or sigma form. May not flag a bet until it out-Briers the identified null out-of-sample, per regime.
- **ENGINEERING** — schema/ingestion/robustness infrastructure the integrity rests on.

## Frozen decisions (canonical)
1. Consensus is line-matched only: the headline consensus estimator averages no-vig true_p ACROSS BOOKS QUOTING THE SAME (player, stat, line) at the same captured_at bucket; consensus_n (count of contributing two-sided books) is stamped per matched line. Cross-line mapping (folding books on adjacent lines into one number) is ASSERTED/GATED via the sigma form and never feeds an identified verdict.
2. Averaging SPACE is no-vig PROBABILITY space (arithmetic mean of per-book de-vigged true_p_over), NOT logit. Justification: the displayed/scored quantity and PrizePicks break-even comparison are both in probability units, the estimand (P(Over)) is a probability so an unbiased estimate of it is the prob-space mean, and logit-averaging injects Jensen curvature bias near the 0/1 tails that is exactly where points props sit.
3. Headline CLV = delta in CONSENSUS no-vig true_p between flag-time and close (close_true_p - flag_true_p, signed to the bet side), expressed in probability units. Line-CLV (delta in line points) is SECONDARY/diagnostic only.
4. Phase-2 variance refit fits var = c * line^gamma with gamma FREE (estimated), never fixed at 0.5/Poisson.
5. Shin z is solved per book from the SAME Over/Under American price pair (2 implied probs, 2 unknowns true_p and z) so it is fully determined per quote and firewall-safe; no external data enters the de-vig.
6. props upsert key becomes (player_name, stat_type, source, book, line) with book NON-NULL ('consensus' sentinel only for the derived consensus row); raw American price_over/price_under persisted per book row.
7. league + league_id -> sport_key is a possibly 1-to-N map with an explicit unmapped->quarantine fallback; new-sport activation is GATED on a populated per-sport roster/schedule/game_id source slot.
8. Calibration verdicts start identified-consensus-only and COLLAPSE strata up a fixed fallback hierarchy until MIN_INDEPENDENT_GAMES is met; the test is a one-sided paired-difference game-clustered bootstrap on the Brier DIFFERENCE (consensus minus baseline) with Benjamini-Hochberg FDR across strata.
9. PrizePicks payout multipliers are a sourced, versioned config primitive (flex + power, per board size); slip objective = maximize portfolio EV s.t. variance cap, per-leg and per-player exposure caps, and a hard fractional-Kelly drawdown/stake cap, solved jointly across simultaneous shared-leg slips.
10. Correlation rho uses a conservative Phase-1 PRIOR (rho0 = 0.15 same-game intra-slip, 0 cross-game) to shrink displayed break-even and size caps; Phase-3 replaces it with a shrinkage-estimated empirical residual-correlation matrix.
11. CREDIT COST MODEL (engineering, firewall-load-bearing): cost of each /events/{id}/odds call = (#markets requested) x (#regions/books requested), reconciled against The-Odds-API x-requests-used/x-requests-remaining response headers persisted per scrape_run_id. A MAX_CREDITS_PER_SLATE budget with a deterministic book-priority DROP ORDER (Pinnacle/DK first, then FD, then BetMGM/WilliamHill) governs truncation; a slate (or matched line) truncated by budget stamps consensus_n from ONLY the books actually fetched and flags the line budget_truncated, withholding the identified-consensus tag rather than computing it on a partial book set. This makes MIN_CONSENSUS_BOOKS>=2 budget-honest.
12. SCRAPER HTTP ROBUSTNESS (engineering): all Odds-API calls go through a shared client with per-request timeout, bounded exponential backoff with jitter on 429/5xx honoring Retry-After, and a max-retry budget. On persistent per-book failure an explicit fetch_status in {ok,http_error,timeout,empty} is persisted per (event, book) so a missing book is a TYPED FAILURE ROW, not an absent row; consensus excludes http_error/timeout books from consensus_n, WARNs, and withholds the identified-consensus tag when failures drop a matched line below MIN_CONSENSUS_BOOKS. This preserves recompute-attributability: a persisted row can always distinguish 'book did not quote this line' from 'fetch failed'.
13. PILLAR-4 STAKE BASELINE AXIS (OBJ-38): the flat-stake baseline that Phase-3 fractional Kelly must beat is a fixed FRACTION of CURRENT bankroll (compounding), NOT a fixed-dollar STAKE_UNIT; a running bankroll and max-drawdown series keyed to slip settlement is persisted; and the Kelly-vs-flat OOS comparison is a PAIRED PER-SLIP LOG-GROWTH (geometric-growth-rate) comparison with a game/slip-clustered CI and a minimum-settled-slip gate -- never a raw cumulative-profit inequality.
14. FLEX SLIP-EV ENGINE (OBJ-39): FLEX slip EV/variance is computed by a Phase-3 Monte-Carlo (or copula) simulation over the per-leg calibrated marginals plus the PSD correlation matrix, evaluating the FLEX hit-count payout tiers from the pinned multiplier ladder. Positive same-direction leg correlation is NON-MONOTONE for FLEX (helps the all-hit tier, HURTS the partial-hit 5/6,4/6 tiers), so FLEX EV/variance must come from this joint simulation and NEVER from per-leg break-even separability; FLEX per-leg numbers remain screening heuristics only.

## Resolutions (every objection closed)
### [IDENTIFIED] Consensus estimator: line-matched identified core vs cross-line asserted mapping; averaging space
*Resolves OBJ-1, OBJ-3 · files: storage/db_manager.py, engine/matcher.py*

IDENTIFIED estimator: for each (player_name, stat_type, line, captured_at bucket) collect every book row whose de-vigged true_p_over exists at that EXACT line; consensus_true_p_over = arithmetic mean over those books in NO-VIG PROBABILITY space; consensus_true_p_under = 1 - consensus_true_p_over; stamp consensus_n = count of contributing books and consensus_book_set (sorted distinct book list) on the derived row. A line with consensus_n < MIN_BOOKS_FOR_CONSENSUS (=2) is NOT a consensus estimate and may not back an identified verdict (it is single-book, flagged as such). Probability space chosen because the estimand and the PP break-even comparison live in probability units and logit-averaging adds tail curvature bias. CROSS-LINE mapping (combining books quoting different lines, e.g. 24.5 and 25.5, into one number) is ASSERTED/GATED: map each book's line to the matched line via a Normal/sigma displacement true_p(L) = Phi((mu - L)/sigma) with sigma from the Phase-2 var=c*line^gamma fit, then average; this is gated behind the calibration firewall and never stamped as the identified consensus_true_p.

### [IDENTIFIED] CLV definition: headline in consensus no-vig prob units, line-CLV secondary
*Resolves OBJ-2 · files: engine/clv_report.py, storage/db_manager.py*

Headline CLV per logged edge = consensus_close_true_p(side) - consensus_flag_true_p(side), where side is the bet (OVER/UNDER), each term is the line-matched consensus no-vig probability at flag time and at the last pre-tipoff consensus snapshot; positive = market moved toward your side in probability. Persist clv_prob (headline), plus secondary diagnostics clv_line = (close_consensus_line - flag line) signed to side, and consensus_n at both flag and close. Replace engine/clv_report.py calculate_clv (currently pure line-point delta against single DK line) with the probability-delta computation; keep the line delta as the 'MOVE' diagnostic column only.

### [ASSERTED_GATED] Variance shape / overdispersion: gamma FREE in Phase-2 refit
*Resolves OBJ-14, OBJ-15 · files: engine/matcher.py*

Phase-2 dispersion model is var(stat) = c * line^gamma with BOTH c and gamma estimated FREE by per-(sport,stat_type) regression of realized squared residuals on line in log space (log var = log c + gamma*log line); gamma is reported with CI and never hard-coded to 0.5 (Poisson) or 1.0. This sigma(line)=sqrt(c*line^gamma) feeds (a) the asserted cross-line sigma mapping (OBJ-1/3) and (b) the slip variance cap. Phase-1 placeholder may use a fixed conservative gamma but it is flagged asserted and excluded from identified verdicts until the free fit has MIN_INDEPENDENT_GAMES support.

### [ASSERTED_GATED] Correlation rho: conservative Phase-1 prior + named Phase-3 estimator
*Resolves OBJ-16, OBJ-17, OBJ-18 · files: engine/matcher.py, engine/correlation.py, web_ui/components.py*

Phase-1 commits a CONSERVATIVE PRIOR rho0 = 0.15 for any two legs in the same game (same game_id), 0.0 for cross-game legs. This rho0 is used to (a) inflate the displayed slip break-even (correlated legs reduce effective independence, raising required per-leg win prob) and (b) tighten size caps via the correlated-variance term in the variance cap. Phase-3 ESTIMATOR: shrinkage-regularized empirical residual correlation matrix (Ledoit-Wolf shrinkage toward rho0*same-game block structure) estimated from realized per-leg outcome residuals, refit per sport, with a PSD projection and its own stability gate; only adopted into displayed numbers once it clears the calibration gate, otherwise rho0 stands.

### [ENGINEERING] Schema: non-null book column in upsert key; persist raw American prices per book
*Resolves OBJ-7, OBJ-8 · files: storage/db_manager.py, scrapers/draftkings_api.py, scrapers/prizepicks_api.py*

props table adds: book TEXT NOT NULL (per-book identifier e.g. 'draftkings','fanduel','pinnacle'; the derived consensus row uses book='consensus'), price_over INTEGER (raw American, nullable only for PP which has no price), price_under INTEGER, league TEXT, league_id TEXT, sport_key TEXT, game_id TEXT. New UNIQUE upsert key = (player_name, stat_type, source, book, line). true_over_prob/true_under_prob remain the de-vigged values DERIVED from price_over/price_under via Shin (OBJ-5). consensus_n and consensus_book_set live on the book='consensus' row. ingest_draftkings/ingest_prizepicks and upsert_prop signatures gain book + price_over/price_under params; existing single-book index idx_props_upsert is dropped and recreated with the book column.

### [IDENTIFIED] Shin z de-vig: solved from the same Over/Under pair (fully determined, firewall-safe)
*Resolves OBJ-5 · files: scrapers/draftkings_api.py*

Per book, per (player, stat, line): from the raw American price_over/price_under compute implied probs q_over=implied(price_over), q_under=implied(price_under). Solve the 2-equation Shin system for (true_p, z) where q_i = (sqrt(z^2 + 4(1-z) * true_p_i^2 / sum_j true_p_j) ... )-form reducing for the 2-outcome case to the standard closed/Newton Shin solution: 2 observed implieds, 2 unknowns (true_p_over and insider fraction z), FULLY DETERMINED with no external input. Persist devig_method='shin' and z per book row. This replaces the current proportional de-vig in calculate_true_probability (draftkings_api.py) which just normalizes ip_over/(ip_over+ip_under); keep proportional as a labeled fallback when Newton fails to converge. Firewall-safe because z derives solely from the same quote pair.

### [ENGINEERING] Multi-sport seam: league mapping with fallback; per-sport name-match + team anchoring
*Resolves OBJ-4, OBJ-6 · files: engine/name_matcher.py, engine/matcher.py, storage/db_manager.py*

(OBJ-4) Maintain an explicit LEAGUE_MAP: (league, league_id) -> sport_key, allowed to be 1-to-N (a league_id may fan out to multiple sport_keys, e.g. combined feeds); any (league,league_id) not in the map routes to a QUARANTINE bucket (sport_key='unmapped', excluded from matching and verdicts, logged for operator review) rather than silently defaulting to NBA. (OBJ-6) Name matching is per-sport: NAME_MATCH_THRESHOLD becomes a per-sport dict (NBA 0.88 default; sports with sparse/ambiguous names get a higher threshold). Disambiguation is TEAM-ANCHORED: candidates are first filtered to the same team (or same game_id) before fuzzy scoring, so name_similarity ties are broken by team match; match_player_name gains a team/sport argument. Implement in engine/name_matcher.py and engine/matcher.py.

### [ENGINEERING] Per-sport roster/schedule/game_id source slot; gate new-sport activation
*Resolves OBJ-19, OBJ-20 · files: storage/db_manager.py, engine/matcher.py, scrapers/draftkings_api.py*

Add a per-sport SOURCE REGISTRY entry providing: roster source (player->team), schedule/game source (game_id, start_time, home/away), and the canonical game_id namespace used for team-anchored matching and same-game correlation. A sport_key is INACTIVE (props ingested but quarantined, no verdicts) until its registry slot is populated and validated (roster non-empty, schedule resolves game_id for the slate). New-sport activation flips an explicit per-sport 'activated' flag only after this gate passes. Stored as a config primitive consumed by ingestion and matcher; game_id column added to props (OBJ-7 schema).

### [IDENTIFIED] Calibration feasibility: stratum-collapse fallback hierarchy, time-to-first-verdict, paired clustered bootstrap with FDR
*Resolves OBJ-9, OBJ-10 · files: engine/clv_report.py, storage/db_manager.py*

FALLBACK HIERARCHY for verdict strata, collapsing only when a finer stratum lacks MIN_INDEPENDENT_GAMES (=200 independent games as the Phase-1 default; configurable): start at (sport, stat_type, line-band, edge_type); if short, collapse line-band; then collapse edge_type; then collapse stat_type; floor is (sport) identified-consensus-only. Always begin identified-consensus-only (single-book and asserted-mapped edges are excluded from the verdict pool). TIME-TO-FIRST-VERDICT expectation: stated explicitly per sport as games_needed/slate_games_per_day (e.g. NBA ~200 indep games / ~10 per slate-day with clustering => on the order of weeks, not days); surfaced in the dashboard as 'verdict pending, N/200 games'. TEST: one-sided paired-difference bootstrap on the Brier DIFFERENCE d = Brier(consensus) - Brier(baseline) per scored leg, CLUSTERED by game_id (resample games, not legs, to respect intra-game correlation), H0: mean d >= 0 vs H1: mean d < 0 (consensus strictly better); apply Benjamini-Hochberg FDR control across all simultaneously evaluated strata. A stratum earns a CALIBRATED verdict only if its FDR-adjusted one-sided p < alpha (0.05) AND it met MIN_INDEPENDENT_GAMES.

### [ENGINEERING] PrizePicks payout multiplier table as sourced config primitive
*Resolves OBJ-11 · files: engine/matcher.py, engine/payout_table.py*

Pin a versioned config primitive PRIZEPICKS_PAYOUTS keyed by (board_type in {power,flex}, n_legs) -> multiplier (and for flex, the per-correct-count payout ladder, e.g. flex 6-pick: 6/6, 5/6, 4/6 multipliers). Each entry carries source_url and effective_date so it is auditable and updatable when PrizePicks changes payouts. The 54.25% constant currently hard-coded as EV_THRESHOLD in matcher.py is DERIVED from this table (break-even for the chosen board), not a magic number; matcher.py reads the threshold from the config. This table lives in engine/payout_table.py and is the single source every EV/break-even/Kelly/FLEX-simulation read.

### [ASSERTED_GATED] Slip-construction objective and simultaneous fractional-Kelly with hard caps
*Resolves OBJ-12, OBJ-13 · files: engine/matcher.py, engine/portfolio.py, engine/kelly.py, web_ui/components.py*

OBJECTIVE: choose a set of slips to MAXIMIZE total portfolio EV (POWER EV per slip = sum over outcome counts of payout_multiplier * P(count) - 1, using leg true_p and the PRIZEPICKS_PAYOUTS ladder, with leg dependence via rho; FLEX slip EV/variance comes from the OBJ-39 joint simulation, never per-leg separability) SUBJECT TO: (1) portfolio variance <= VAR_CAP; (2) per-leg exposure cap and per-player cap (a player appears in at most K simultaneous slips); (3) number of simultaneous slips <= MAX_SLIPS; (4) total staked <= STAKE_CAP, with exposure measured in FRACTION-OF-BANKROLL-AT-RISK units. SIZING: simultaneous FRACTIONAL-Kelly across shared-leg slips: solve for stake vector b maximizing sum E[log(1 + portfolio return)] approximated with the shared-leg covariance (built from rho0/Phase-3 rho), then multiply by Kelly fraction f (Phase-1 f=0.25) and CLIP to a HARD per-slip and aggregate drawdown/stake cap so no shared-leg concentration can exceed the cap. Shared legs are modeled once in the covariance so correlated stakes are not double-counted. POWER per-leg gate is exact-under-independence; FLEX is heuristic-only and never a slip-level gate.

### [IDENTIFIED] Captured_at bucketing, consensus snapshot timing, staleness, and PP-vs-consensus alignment
*Resolves OBJ-21, OBJ-22, OBJ-23, OBJ-24 · files: storage/db_manager.py, engine/clv_report.py*

Define a SNAPSHOT BUCKET = floor(captured_at to SNAPSHOT_GRAN, =5 min). Consensus is computed only within one bucket so books are compared contemporaneously; a book row older than STALE_MAX (=15 min) is excluded from that bucket's consensus and consensus_n. The CLV flag snapshot and close snapshot are the bucketed consensus rows nearest flag-time and last pre-tipoff. PP lines are matched to the consensus row in the same (or nearest non-stale) bucket. get_latest_props/get_latest_dk_line are generalized to bucket-aware lookups; a consensus_snapshot row is materialized per bucket with consensus_n, contributing book set, and computed_at.

### [IDENTIFIED] De-vig edge cases: missing side, one-sided markets, convergence failure, alternate lines
*Resolves OBJ-25, OBJ-26, OBJ-27 · files: scrapers/draftkings_api.py, storage/db_manager.py, engine/matcher.py*

If a book quotes only one side (no Over/Under pair) it CANNOT be de-vigged and is excluded from consensus for that line (logged). Shin Newton iteration that fails to converge or yields z outside [0,1) falls back to proportional de-vig with devig_method='proportional_fallback' stamped. Alternate-line ladders from one book at the same (player,stat) are kept as separate line rows (matching current closest-line behavior in matcher.pick_closest_line) and only the EXACT-line match enters identified consensus; off-line ladder rungs feed only the asserted cross-line sigma map. Each excluded/fallback case is counted so consensus_n reflects only clean contributions.

### [IDENTIFIED] Edge definition vs consensus, +EV threshold derivation, and dedup
*Resolves OBJ-28, OBJ-29, OBJ-30 · files: engine/matcher.py, storage/db_manager.py*

Edge detection is rewritten against CONSENSUS (not single DK): line-discrepancy edge when PP line differs from the consensus line; +EV edge when at the matched line consensus_true_p(side) >= board break-even from PRIZEPICKS_PAYOUTS (OBJ-11), with consensus_n>=2 required for an identified flag (consensus_n==1 flags are marked single-book/asserted). EV_THRESHOLD literal in matcher.py becomes config-derived. EDGE DEDUP (also README backlog item): collapse repeat flags for the same (player, stat, side, board bucket) within a snapshot bucket to one edge row carrying first_flagged_at and last_seen_at, so CLV and verdict pools are not inflated by duplicate flags.

### [IDENTIFIED] Baseline definition for Brier comparison and verdict labeling
*Resolves OBJ-31, OBJ-32, OBJ-33 · files: engine/clv_report.py, storage/db_manager.py*

The calibration baseline against which consensus Brier is tested (OBJ-9/10) is pinned as the SINGLE-SHARPEST-BOOK no-vig true_p (Pinnacle if present, else the configured sharp book) at the same matched line and bucket; the alternative baseline (PP implied break-even / coin-flip) is recorded as a secondary diagnostic only. Verdicts are labeled per stratum as CALIBRATED / PENDING / FAILED based on the FDR-adjusted paired test; only CALIBRATED identified strata may drive sizing without the asserted gate.

### [ENGINEERING] POWER/FLEX multiplier table as versioned config; slip objective; POWER-exact gate, FLEX heuristic-only
*Resolves OBJ-34, OBJ-35 · files: engine/payout_table.py, engine/matcher.py, engine/portfolio.py*

OBJ-34: the PP POWER/FLEX multiplier table (POWER per-n multiplier + FLEX tiered payout ladder per board size) is a SOURCED/VERSIONED config primitive in engine/payout_table.py that EVERY EV/break-even/Kelly/FLEX-simulation reads; no hardcoded multiplier or break-even literal anywhere. OBJ-35: slip-construction objective = maximize portfolio EV subject to variance and exposure caps over a bounded number (MAX_SLIPS) of simultaneous slips; the POWER per-leg gate (win_prob>breakeven, exact under independence since p^n*M=1) is the only exact per-leg gate, FLEX is heuristic-only and never a slip-level gate.

### [ASSERTED_GATED] Joint fractional-Kelly with hard drawdown/ruin cap; correlation-adjusted exposure caps in bankroll-fraction units
*Resolves OBJ-36, OBJ-37 · files: engine/kelly.py, engine/portfolio.py, engine/calibration.py, storage/db_manager.py*

OBJ-36: stakes are sized by JOINT fractional-Kelly on the correlated shared-leg slip portfolio with a HARD drawdown/stake-ruin cap; the Kelly engine must beat the flat-stake baseline OUT OF SAMPLE on the geometric/log-growth axis pinned in OBJ-38. OBJ-37: MAX_TOTAL_EXPOSURE is correlation-adjusted, with numeric defaults expressed in BANKROLL-FRACTION units; when caps conflict the MOST-BINDING cap wins and ties drop the lowest-edge leg/slip. Exposure caps and Kelly stakes are both evaluated in fraction-of-current-bankroll-at-risk units so they compose with the OBJ-38 compounding baseline.

### [ASSERTED_GATED] Kelly-vs-flat-stake comparison evaluated on the correct (geometric log-growth) axis; compounding fractional baseline; bankroll+drawdown series
*Resolves OBJ-38 · files: engine/kelly.py, engine/portfolio.py, engine/calibration.py, storage/db_manager.py*

PATCH to Pillar-4 baseline and the Portfolio/Kelly resolution. (1) REDEFINE the flat-stake baseline: it is a fixed FRACTION of CURRENT bankroll (compounding) -- BASELINE_STAKE_FRACTION of running bankroll per settled slip -- NOT the frozen fixed-dollar STAKE_UNIT with a cumulative realized_profit accumulator. The fixed-dollar STAKE_UNIT/realized_profit accumulator is retained only as a raw-dollar diagnostic and is explicitly NOT the axis Kelly is judged on. (2) PERSIST a running bankroll series and a max-drawdown series keyed to slip settlement (settled_at): each settled slip updates bankroll *= (1 + realized_return), records bankroll_after, running_max_bankroll, and drawdown = (running_max_bankroll - bankroll_after)/running_max_bankroll, in storage/db_manager.py (extend the slips table / add a bankroll_curve table keyed to slip_id+settled_at). (3) PIN the Kelly-vs-flat-stake OOS comparison METRIC: a PAIRED PER-SLIP LOG-GROWTH (geometric-growth-rate) comparison -- for each settled slip compute log(1+r_kelly) and log(1+r_flat) on the SAME settled outcome and stake context, take the paired difference, and test the mean paired log-growth difference with a GAME/SLIP-CLUSTERED bootstrap CI (resample slip-clusters, not legs). A Kelly-beats-flat VERDICT requires (a) the clustered CI on mean paired log-growth difference excludes 0 in Kelly's favor AND (b) a stated MINIMUM-SETTLED-SLIP gate (MIN_SETTLED_SLIPS, conservative default, configurable) is met. NEVER a raw cumulative-profit (sum of dollars) inequality. This makes the Phase-3 activation gate for the Kelly engine determined on the axis Kelly actually optimizes.

### [ASSERTED_GATED] FLEX slip-EV/variance engine pinned: joint Monte-Carlo over calibrated marginals + PSD correlation, non-monotone correlation note
*Resolves OBJ-39 · files: engine/portfolio.py, engine/payout_table.py, engine/correlation.py*

PATCH replacing the deferred FLEX EV computation with a pinned Phase-3 mechanism. FLEX slip EV and variance are computed by a JOINT MONTE-CARLO simulation (or copula) over the per-leg CALIBRATED marginal win-probabilities plus the Phase-3 PSD correlation matrix (from the OBJ-40 Ledoit-Wolf shrinkage + PSD projection resolution): draw correlated leg outcomes, count hits, map the hit-count to the FLEX tiered payout from the pinned PRIZEPICKS_PAYOUTS ladder (engine/payout_table.py), and average over draws to get FLEX_slip_EV and FLEX_slip_variance. The engine/portfolio.py FLEX EV function DOCSTRING must state: positive same-direction leg correlation is NON-MONOTONE for FLEX -- it fattens both tails, HELPING the all-hit (n/n) tier while HURTING the partial-hit (5/6, 4/6) tiers FLEX relies on -- therefore FLEX slip EV/variance MUST come from this joint simulation and may NEVER be derived from per-leg break-even separability or a separable per-leg sum. POWER EV remains the closed-form correlated hit-count expression; only FLEX requires the simulation. The 'maximize portfolio EV' objective over a mixed POWER/FLEX pool consumes FLEX EV/variance exclusively from this simulation.

### [ENGINEERING] Per-leg correlation fit (Ledoit-Wolf shrinkage + PSD projection + stability gate); reproducibility/versioning of config primitives
*Resolves OBJ-40, OBJ-41 · files: engine/correlation.py, engine/calibration.py, engine/matcher.py, engine/clv_report.py, storage/db_manager.py*

OBJ-40: the Phase-3 per-leg correlation matrix is fit on realized per-leg OUTCOME residuals via Ledoit-Wolf shrinkage toward a single-rho (rho0 same-game block) prior, followed by a PSD PROJECTION (nearest correlation matrix) so it is a valid covariance, behind its OWN stability gate (refit only adopted when stable and clearing the calibration gate; else rho0 stands). This matrix is the one consumed by the OBJ-39 FLEX simulation and the OBJ-36 joint Kelly covariance. OBJ-41/reproducibility: all sourced primitives (PRIZEPICKS_PAYOUTS, LEAGUE_MAP, per-sport SOURCE REGISTRY, per-sport NAME thresholds, rho0, Kelly fraction f, BASELINE_STAKE_FRACTION, MIN_BOOKS_FOR_CONSENSUS/MIN_CONSENSUS_BOOKS, MIN_INDEPENDENT_GAMES, MIN_SETTLED_SLIPS, SNAPSHOT_GRAN, STALE_MAX, VAR_CAP, STAKE_CAP, MAX_SLIPS, MAX_CREDITS_PER_SLATE, HOLD_CEILING, book-priority DROP ORDER, HTTP timeout/backoff/max-retry budget) live in a single versioned config module with effective_date/source fields, and the config version is stamped on every edge and verdict row so any historical verdict is reproducible. Minor fold-ins: standardize CLV display to probability units with line secondary, make get_latest_props book/bucket-aware so PP NULL-price rows never feed de-vig.

### [ENGINEERING] Credit cost/quota primitive: cost-per-event formula reconciled to Odds-API headers, MAX_CREDITS_PER_SLATE budget with book-priority drop order, budget-truncation withholds the identified-consensus tag
*Resolves credit-cost-model · files: scrapers/draftkings_api.py, storage/db_manager.py, engine/consensus.py*

[engineering] Pin a CREDIT COST/QUOTA primitive so the now-mandated multi-book (DK/FD/BetMGM/WilliamHill) fetch cannot silently exhaust quota mid-slate and deflate consensus_n. (a) COST FORMULA: cost charged per /events/{id}/odds call = (number of markets requested) x (number of regions/books requested), config-sourced (markets and book list from config, not a hardcoded '1 credit per game'). The wrong literal at scrapers/draftkings_api.py:42 ('Costs 1 API Credit per game') and the matching README/components.py cost strings are corrected to this markets x regions formula. Each call's ACTUAL cost is reconciled against the Odds-API x-requests-used / x-requests-remaining response headers, and used/remaining are PERSISTED per scrape_run_id (and per call) in storage/db_manager.py so spend is auditable and recomputable. (b) BUDGET: a MAX_CREDITS_PER_SLATE budget with a DETERMINISTIC book-priority DROP ORDER (drop in reverse priority: keep Pinnacle/DK first, then FanDuel, then BetMGM, then WilliamHill) applied when the projected/observed spend would exceed the budget, so truncation is deterministic and reproducible rather than wherever quota happens to run out. (c) BUDGET-TRUNCATION RULE: a slate (or any matched line) truncated by budget stamps consensus_n from ONLY the books actually fetched, flags the matched line budget_truncated=true, and the identified-consensus tag is WITHHELD (consensus_tag downgraded, never 'identified') rather than silently computed on a partial book set -- preserving the MIN_CONSENSUS_BOOKS>=2 guarantee and the identified-consensus tag integrity the chair froze. engine/consensus.py honors budget_truncated when deciding the consensus_tag.

### [ENGINEERING] Scraper HTTP robustness: timeout + bounded backoff/jitter honoring Retry-After + max-retry budget; typed per-(event,book) fetch_status; consensus excludes failed books, WARNs, and withholds the tag below MIN_CONSENSUS_BOOKS
*Resolves http-robustness · files: scrapers/draftkings_api.py, storage/db_manager.py, engine/consensus.py*

[engineering] Pin scraper HTTP robustness so a dropped book or transient 429 under the multi-book fetch is recorded as a typed failure (not an absent row) and never silently averaged. (a) ROBUST CLIENT: every Odds-API request gets a per-request TIMEOUT, BOUNDED EXPONENTIAL BACKOFF WITH JITTER on 429/5xx that HONORS the Retry-After header, and a MAX-RETRY BUDGET; replaces the bare requests.get with no timeout/retry at scrapers/draftkings_api.py:36,53 (shared http_client used by all scrapers). The current behavior of returning None and silently `continue`-ing the loop (draftkings_api.py:74) is removed. (b) TYPED FAILURE PERSISTENCE: on persistent per-book failure, persist an explicit fetch_status in {ok, http_error, timeout, empty} per (event, book) in storage/db_manager.py, so a missing book is a TYPED FAILURE ROW rather than an absent row -- letting a recompute from persisted rows distinguish 'book did not quote this line' (absent/empty pair) from 'fetch failed' (http_error/timeout), restoring recompute-attributability. (c) CONSENSUS RULE: engine/consensus.py EXCLUDES http_error/timeout books from consensus_n and emits a WARN; and WITHHOLDS the identified-consensus tag when failures drop a matched line below MIN_CONSENSUS_BOOKS (consensus_tag downgraded, line flagged), so partial-fetch degradation is recompute-visible and the MIN_CONSENSUS_BOOKS>=2 identified-tag rule is never satisfied by silently averaging over a degraded book set. Interacts with credit-cost-model: budget_truncated and fetch-failure both feed the same tag-withholding logic.

## Roadmap
### Phase 0 — Seam, provenance, robustness, budget (must land before ground truth accumulates)
- Add non-null sport to props upsert key, populated from BOTH sources: extract PP league/league_id (prizepicks_api.py) and derive DK sport from registry odds_api_sport_key
- Build engine/sports.py: per-(sport,stat_type) canonical stat vocab + per-sport PP-label normalization map; market_type and sigma_prior both keyed (sport,stat_type); has_alternate_ladder; availability predicate; settlement_source + lineup_source slots
- Name nba_api rosters/schedule as authoritative roster/team source; persist stable game_id; degrade scope to (sport,game_date) with homonym-risk flag when team unresolvable
- Rename de-vig stamp to 'multiplicative_2way'; pin devig_method as registry parameter; add high-hold guard
- Pin consensus order (de-vig each book then average) in engine/probability.py docstring; persist consensus_n/contributing_books; enforce MIN_CONSENSUS_BOOKS with single-book-DK fallback stamped consensus_n=1
- Commit DEFAULT_SIGMA_FORM=cv_sqrt with sigma-inflating fallback; derive the 1.5-sigma cap (labeled PROVISIONAL/market-implied)
- Shared http_client.py (timeout, retry, backoff+jitter, Retry-After, pooled session); event_scrape_failed sentinel; credit-header capture + per-slate cap + hard stop
- Fix the clock: per-quote last_update for movement + scrape_run_id/snapshot_tag for identity; idempotent re-ingest; remove captured_at from the unique key
- Persist slip_id co-selection grouping (slips + slip_legs tables) and STAKE_UNIT; correct cost-model strings in README/components.py
- Define closing-snapshot trigger keyed off commence_time; fix clv_report.py:38 (no MAX(captured_at) fallback); per-book close_complete flag

_Rationale:_ These are migrations and provenance stamps that cannot be backfilled honestly once outcomes accumulate. The sport dimension, canonical-stat join key, stable game_id, slip grouping, de-vig/consensus provenance, the clock fix, and the credit/robustness layer all gate the integrity of every downstream measurement and the cross-source join the moment a second sport ships.

### Phase 1 — Identified selection (no asserted shape flags yet)
- Cross-book line shopping in matcher: best number/true prob across 4 books becomes the PP anchor; persist best_book
- Equal-weight no-vig consensus as the sole identified default; vig-weight path gated OFF
- POWER-only per-leg gate (exact under independence); FLEX exposed only as a labeled screening heuristic, not a slip break-even
- Binding exposure caps in exposure.py (per-game leg cap, per-cluster concentration, total exposure) keyed on game_id; sign-dependent correlation-bias docstring
- Push model implemented INSTRUMENTED-BUT-DORMANT (computed/stored, no live calibration input) until integer-aware payout table
- Ladder sigma from TWO-SIDED rungs only, shape-contingent stamp; one-sided rungs → prior_thin_ladder; no_ladder_available where applicable

_Rationale:_ Phase 1 ships only what is recompute-attributable (consensus, line shopping, CLV vs consensus close) and coherent gates (POWER-exact). Asserted shape (Normal win_prob) is computed and stamped but its FLAGGING is withheld until Phase 2 proves it per-regime. Exposure caps must be binding before any independence-assuming break-even is applied to a real slip.

### Phase 2 — Settled-outcome calibration loop (gates the asserted shape)
- NBA settlement adapter returns availability_status + did_participate; VOID derived from did_participate==False + PP threshold; partial-game/mid-game-exit exclusion
- Game-clustered block-bootstrap CIs for Brier/log-loss; design-effect deflation; MIN_INDEPENDENT_GAMES gate
- Per-regime stratified reliability (sigma_source, line-band, push-applied, book-coverage); asserted-prior slice must clear its own bar
- Required baselines incl. consensus-p_over and ladder-implied p_over; gate Normal path OFF if it does not beat consensus-p_over OOS
- Re-fit sigma FORM and 1.5-sigma cap against realized box-score dispersion (answer 'is CV~0.5' from settled data)
- Reliability-slope test (logistic on logit(pred), game-clustered SEs, stated pass bands) as documented primary go/no-go
- De-vig method bake-off (multiplicative vs power vs Shin) on the same settled set; attach realized_profit to constructed slips (flat-stake baseline)

_Rationale:_ Calibration MEASURES and GATES. The asserted shape, the sigma form/cap, and the de-vig method are validated against realized outcomes with clustered, regime-stratified statistics — never against the market's own de-vig (circular). Nothing asserted flags a bet until it out-Briers the identified consensus null out-of-sample on enough independent game-nights.

### Phase 3 — Calibration map, sharpness/vig weighting, fractional Kelly, multi-sport activation
- Walk-forward isotonic/Platt win_prob_calibrated, per-regime, identity fallback below stability floor, held-out calibrated-vs-raw improvement required
- Activate vig-implied and DK-tiebreak sharpness weighting only if they beat equal-weight consensus OOS
- Slip-level correlation matrix fit against realized slip outcomes via slip_id linkage
- Fractional Kelly under correlation, must beat the flat-stake baseline
- Integer-aware push payout table → flip push model from dormant to live
- Ship second sport (NCAAB/NHL/soccer) once its (sport,canonical_stat) join, roster source, market_type, and availability predicate pass; soccer uses the two-feed lineup/settlement seam

_Rationale:_ Everything asserted (calibration map, sharpness weights, Kelly, second sport) ships last, each behind its own OOS proof. The map, weights, and Kelly must each beat their identified null/flat-stake baseline; a second sport activates only when its seam invariants and per-regime calibration pass, so expansion is earned, not assumed.

---

## Addendum — 2026-07-01: settlement integrity + evidence-gated YES

Three implementation gaps in the settlement/pricing path (not spec changes —
bugs against this document's own invariants) were fixed and are now covered
by tests: kickoff resolution could match a stale fixture for a multi-match
team (`engine/matcher.py:_resolve_kickoff`), the `STALE_SETTLE_MAX_HOURS`
force-void was specified but never enforced, and a DNP/benched player settled
as a graded UNDER win instead of VOID (no participation gate existed). A
retro audit script (`scripts/audit_dnp.py`) re-grades rows settled before the
participation gate landed.

Also, this document's OBJ-1/3 "identified" consensus rule (≥2 books at the
exact matched line) is now enforced as a **hard verdict gate**, not just a
provenance stamp: `evaluate_player` downgrades YES → LEAN whenever
`consensus_tag != 'identified'`, and soft books (Underdog) plus PrizePicks
itself are excluded from the count that can produce "identified." A further
non-spec addition — an automatic AI matchup check on every YES, using FBref
opponent defense rank as context — runs after this gate and can downgrade to
LEAN but never blocks on its own failure. See `README_AGENTS.md` → "Verdict
Rules (the gauntlet)" for the user-facing description.
