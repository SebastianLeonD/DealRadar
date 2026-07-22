// Nike — discover/product_wall API (the one nike.com's own sale wall calls).
// Open, but requires the public nike-api-caller-id header.
import { getJSON, usd } from "./util.js";

const CHANNEL = "d9a5bc42-4b9c-4976-858a-f159cf99c647"; // nike.com
const WALL_PATH = "/w/mens-sale-3yaepznik1"; // Men's Sale
const CALLER_ID = { "nike-api-caller-id": "nike:dotcom:browse:wall.client:2.0" };

/** Pure mapper: Nike product-wall JSON -> deals (one per grouping, discounted only). */
export function mapNike(data) {
  const deals = [];
  for (const g of data.productGroupings ?? []) {
    const p = g.products?.[0]; // first colorway represents the grouping
    if (!p) continue;
    const cur = p.prices?.currentPrice;
    const init = p.prices?.initialPrice;
    const url = p.pdpUrl?.url;
    if (!p.copy?.title || !url || !cur || !init || cur >= init) continue;
    const pct = p.prices?.discountPercentage ?? Math.round((1 - cur / init) * 100);
    deals.push({
      title: `${p.copy.title}${p.copy.subTitle ? ` (${p.copy.subTitle})` : ""} — ${usd(cur)} (was ${usd(init)}, ${pct}% off)`,
      url,
      source: "nike.com",
      category: "Clothing",
      store: "Nike",
      image_url: p.colorwayImages?.portraitURL ?? p.colorwayImages?.squarishURL ?? null,
      posted_at: null,
      discount_pct: pct,
    });
  }
  return deals;
}

export async function fetchNike() {
  const base = `https://api.nike.com/discover/product_wall/v1/marketplace/US/language/en/consumerChannelId/${CHANNEL}`;
  const deals = [];
  let path = `${base}?path=${WALL_PATH}&queryType=PRODUCTS`;
  for (let page = 0; page < 3 && path; page++) { // 3 pages ≈ 72 groupings
    const data = await getJSON(path, CALLER_ID);
    deals.push(...mapNike(data));
    path = data.pages?.next ? `https://api.nike.com${data.pages.next}` : null;
  }
  return deals;
}
