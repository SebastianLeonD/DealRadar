// Direct retailer fetchers — one file per store, each hitting the same
// unofficial JSON endpoints the store's own site uses. These break silently
// when a retailer changes endpoints or bot rules; per-source health in
// /api/status is how you notice.
// ponytail: Hollister/PacSun/ASOS reject non-browser traffic (Akamai 403) —
// direct scraping needs a headless browser, so they're not covered.
import { fetchBestBuy } from "./bestbuy.js";
import { fetchGap, fetchOldNavy } from "./gap.js";
import { fetchHM } from "./hm.js";
import { fetchIkea } from "./ikea.js";
import { fetchNike } from "./nike.js";
import {
  fetchBrooklinen, fetchColorCord, fetchCoyuchi, fetchGymshark, fetchJonathanY,
  fetchLuluGeorgia, fetchMitzi, fetchOurPlace, fetchParachute, fetchVitruvi,
} from "./shopify.js";
import { fetchTarget } from "./target.js";
import { fetchZara } from "./zara.js";

/** All direct scrapers, in the same {name, fetch} shape sources.js uses. */
export const SCRAPERS = [
  { name: "zara.com", fetch: fetchZara },
  { name: "hm.com", fetch: fetchHM },
  { name: "nike.com", fetch: fetchNike },
  { name: "ikea.com", fetch: fetchIkea },
  { name: "gap.com", fetch: fetchGap },
  { name: "oldnavy.com", fetch: fetchOldNavy },
  { name: "gymshark.com", fetch: fetchGymshark },
  { name: "parachutehome.com", fetch: fetchParachute },
  { name: "coyuchi.com", fetch: fetchCoyuchi },
  { name: "brooklinen.com", fetch: fetchBrooklinen },
  { name: "fromourplace.com", fetch: fetchOurPlace },
  // "For Your Room" — lights, rugs, decor, air/scent
  { name: "mitzi.com", fetch: fetchMitzi },
  { name: "colorcord.com", fetch: fetchColorCord },
  { name: "vitruvi.com", fetch: fetchVitruvi },
  { name: "jonathany.com", fetch: fetchJonathanY },
  { name: "luluandgeorgia.com", fetch: fetchLuluGeorgia },
  // Target's RedSky is Akamai-protected: it captchas repeated/flagged traffic
  // (see ISSUES.md). Off by default; set ENABLE_TARGET=1 to try it from a clean,
  // low-volume IP. Fails safe (throws on captcha) rather than polluting data.
  ...(process.env.ENABLE_TARGET ? [{ name: "target.com", fetch: fetchTarget }] : []),
  // official API, needs a free key from developer.bestbuy.com in .env
  ...(process.env.BESTBUY_API_KEY ? [{ name: "bestbuy.com", fetch: fetchBestBuy }] : []),
];
