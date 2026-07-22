# Issues log

Format: date — symptom — root cause — fix.

- 2026-07-22 — Repo lived on branch `claude/ai-discount-aggregator-sy0e6c` of Prizepicks-AI — project started in the wrong repo — cloned branch, repointed origin to SebastianLeonD/DealRadar, pushed as `main`.
- 2026-07-22 — Hollister/PacSun/ASOS direct scraping impossible — Akamai returns 403 to any non-browser request (curl/Node) — covered via Slickdeals per-store search RSS instead; don't retry direct scraping without a headless browser.
- 2026-07-22 — Zara scraper returned 0 men's items — top-level MAN>SALE category id (2721407) returns empty from the products endpoint — use the MAN>SALE>SHOP ALL redirect target (2439352); category ids live in `zara.com/us/en/categories?ajax=true`.
- 2026-07-22 — H&M `listing/resultpage` endpoint always 0 hits server-side — unknown required categoryId — use `search/resultpage` with `facets=sale:true` + broad queries instead (works without cookies).
- 2026-07-22 — Deal card images never loaded (blank cards) — `loading="lazy"` on every img; Chrome defers lazy images indefinitely in unfocused/automated windows — first 10 cards now load eager, rest stay lazy.
