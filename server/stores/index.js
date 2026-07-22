// Direct retailer fetchers — one file per store, each hitting the same
// unofficial JSON endpoints the store's own site uses. These break silently
// when a retailer changes endpoints or bot rules; per-source health in
// /api/status is how you notice.
// ponytail: Hollister/PacSun/ASOS reject non-browser traffic (Akamai 403) —
// they're covered by Slickdeals search feeds in sources.js instead.
import { fetchBestBuy } from "./bestbuy.js";
import { fetchEpic } from "./epic.js";
import { fetchGOG } from "./gog.js";
import { fetchHM } from "./hm.js";
import { fetchIkea } from "./ikea.js";
import { fetchNike } from "./nike.js";
import { fetchSteam } from "./steam.js";
import { fetchZara } from "./zara.js";

/** All direct scrapers, in the same {name, fetch} shape sources.js uses. */
export const SCRAPERS = [
  { name: "zara.com", fetch: fetchZara },
  { name: "hm.com", fetch: fetchHM },
  { name: "nike.com", fetch: fetchNike },
  { name: "ikea.com", fetch: fetchIkea },
  { name: "steam", fetch: fetchSteam },
  { name: "gog.com", fetch: fetchGOG },
  { name: "epicgames.com", fetch: fetchEpic },
  // official API, needs a free key from developer.bestbuy.com in .env
  ...(process.env.BESTBUY_API_KEY ? [{ name: "bestbuy.com", fetch: fetchBestBuy }] : []),
];
