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
import { fetchGymshark, fetchParachute } from "./shopify.js";
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
  { name: "target.com", fetch: fetchTarget },
  // official API, needs a free key from developer.bestbuy.com in .env
  ...(process.env.BESTBUY_API_KEY ? [{ name: "bestbuy.com", fetch: fetchBestBuy }] : []),
];
