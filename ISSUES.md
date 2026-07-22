# Issues log

Format: date — symptom — root cause — fix.

- 2026-07-22 — Repo lived on branch `claude/ai-discount-aggregator-sy0e6c` of Prizepicks-AI — project started in the wrong repo — cloned branch, repointed origin to SebastianLeonD/DealRadar, pushed as `main`.
- 2026-07-22 — Hollister/PacSun/ASOS direct scraping impossible — Akamai returns 403 to any non-browser request (curl/Node) — covered via Slickdeals per-store search RSS instead; don't retry direct scraping without a headless browser.
- 2026-07-22 — Zara scraper returned 0 men's items — top-level MAN>SALE category id (2721407) returns empty from the products endpoint — use the MAN>SALE>SHOP ALL redirect target (2439352); category ids live in `zara.com/us/en/categories?ajax=true`.
- 2026-07-22 — H&M `listing/resultpage` endpoint always 0 hits server-side — unknown required categoryId — use `search/resultpage` with `facets=sale:true` + broad queries instead (works without cookies).
- 2026-07-22 — Deal card images never loaded (blank cards) — `loading="lazy"` on every img; Chrome defers lazy images indefinitely in unfocused/automated windows — first 10 cards now load eager, rest stay lazy.
- 2026-07-22 — New deal columns (colors/sizes/discount_pct) stayed NULL after deploy — `INSERT OR IGNORE` never backfills existing rows — after adding columns that scrapers populate, purge those sources' rows (`DELETE FROM deals WHERE source IN (...)`) and refresh.
- 2026-07-22 — Non-clothing tabs empty — Reddit RSS 429'd all day because every dev-server restart triggered a full refresh — fixes: skip startup refresh when data <5 min old; 30-min cooldown for any 429'd source; Gaming tab now fed by direct Steam/GOG/Epic fetchers that don't depend on Reddit.
- 2026-07-22 — Uniqlo direct fetcher scrapped — their commerce API's `flagCodes=discount` items always show promo == base price (sale price not exposed on listing endpoint) — covered via slickdeals:uniqlo feed; revisit only if a price-bearing endpoint turns up.
