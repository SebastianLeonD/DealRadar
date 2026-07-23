// Target — RedSky is the public JSON API target.com's own product-list pages
// call. `key` is Target's public web key and `pricing_store_id` a real store;
// both rotate occasionally — update here if this starts 400'ing. Home focus per
// user preference: a few home clearance queries, deduped, markdowns only.
//
// Akamai TLS-fingerprints Node's fetch and 403s it (browser-ClientHello only),
// so we shell out to the system `curl`, whose fingerprint passes. curl ships
// with macOS/Linux; if it's missing this source just reports an error in health.
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { usd } from "./util.js";

const execFileP = promisify(execFile);
const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36";

async function curlJSON(url) {
  const { stdout } = await execFileP(
    "curl",
    ["-s", "--max-time", "20",
     "-H", `User-Agent: ${UA}`, "-H", "Accept: application/json",
     "-H", "Origin: https://www.target.com", "-H", "Referer: https://www.target.com/",
     url],
    { maxBuffer: 16 * 1024 * 1024 }
  );
  let data;
  try { data = JSON.parse(stdout); } catch { throw new Error("Target: non-JSON response (bot wall?)"); }
  // Akamai occasionally serves a captcha challenge under bursty traffic — fail
  // loudly so per-source health flags it instead of silently reporting 0 deals.
  if (data.captchaRelativeURL || data.captchaAbsoluteURL) throw new Error("Target: Akamai captcha challenge");
  return data;
}

const KEY = "9f36aeafbe60771e321a7cc95a78140772ab3e96";
const STORE = "3991";
// One query only: Akamai captchas even a few spaced requests, but a single
// call per refresh stays under the radar and still returns ~30 home items.
const QUERIES = ["home clearance"];
const GAP_MS = 1500; // pause between queries if the list ever grows
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Pure mapper: RedSky plp_search_v2 JSON -> deals (real markdowns only). */
export function mapTarget(data) {
  const deals = [];
  for (const p of data.data?.search?.products ?? []) {
    const price = p.price?.current_retail;
    const was = p.price?.reg_retail;
    const title = p.item?.product_description?.title;
    const url = p.item?.enrichment?.buy_url;
    if (!title || !url || !price || !was || price >= was) continue;
    const pct = p.price.save_percent || Math.round((1 - price / was) * 100);
    const img = p.item?.enrichment?.image_info?.primary_image?.url;
    deals.push({
      title: `${title} — ${usd(price)} (was ${usd(was)}, ${pct}% off)`,
      url,
      source: "target.com",
      category: "Home",
      store: "Target",
      image_url: img ? `${img}?wid=600` : null,
      posted_at: null,
      colors: null,
      sizes: null,
      discount_pct: pct,
    });
  }
  return deals;
}

export async function fetchTarget() {
  const seen = new Set();
  const deals = [];
  for (const [i, q] of QUERIES.entries()) {
    if (i) await sleep(GAP_MS);
    const params = new URLSearchParams({
      key: KEY, channel: "WEB", count: "28", offset: "0",
      page: `/s/${q}`, keyword: q, platform: "desktop",
      pricing_store_id: STORE, store_ids: STORE,
      visitor_id: "0189ABCDEF0123456789ABCDEF012345",
      default_purchasability_filter: "true",
    });
    const data = await curlJSON(
      `https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2?${params}`
    );
    for (const d of mapTarget(data)) {
      if (seen.has(d.url)) continue;
      seen.add(d.url);
      deals.push(d);
    }
  }
  return deals;
}
