// H&M — search API with the sale facet. There's no browsable "all sale"
// endpoint reachable server-side, so a few broad queries approximate it.
// redPrice = sale price, whitePrice = original.
import { getJSON, usd } from "./util.js";

const QUERIES = ["men jeans", "men shirt", "men jacket", "men shoes", "men hoodie", "men pants"];
const PAGE_SIZE = 30;

/** Pure mapper: H&M search-results JSON -> deals (men's sale items only —
    mainCatCode prefixes are ladies_/men_/kids_/divided_). */
export function mapHM(data) {
  const deals = [];
  for (const p of data.searchHits?.productList ?? []) {
    const red = p.prices?.find((x) => x.priceType === "redPrice")?.price;
    const white = p.prices?.find((x) => x.priceType === "whitePrice")?.price;
    if (!p.productName || !p.url || !red || !white || red >= white) continue;
    if (!p.mainCatCode?.startsWith("men_")) continue;
    const pct = Math.round((1 - red / white) * 100);
    // colorWithNames is "blue_0000ff"-style; take the base color word
    const colors = [...new Set(
      [p.colorWithNames, ...(p.colors && Array.isArray(p.colors) ? p.colors : [])]
        .filter((c) => typeof c === "string" && c.includes("_"))
        .map((c) => c.split("_")[0].toLowerCase())
    )].join(",");
    const sizes = [...new Set(
      (p.sizes ?? []).filter((s) => s.stock > 0).map((s) => s.label)
    )].join(",");
    deals.push({
      title: `${p.productName} — ${usd(red)} (was ${usd(white)}, ${pct}% off)`,
      url: `https://www2.hm.com${p.url}`,
      source: "hm.com",
      category: "Clothing",
      image_url: p.productImage ?? p.modelImage ?? null,
      posted_at: null,
      colors: colors || null,
      sizes: sizes || null,
      discount_pct: pct,
    });
  }
  return deals;
}

export async function fetchHM() {
  const seen = new Set();
  const deals = [];
  for (const q of QUERIES) {
    const params = new URLSearchParams({
      query: q, page: "1", sort: "RELEVANCE", "page-size": String(PAGE_SIZE),
      touchPoint: "DESKTOP", facets: "sale:true",
    });
    const data = await getJSON(`https://api.hm.com/search-services/v1/en_us/search/resultpage?${params}`);
    for (const d of mapHM(data)) {
      if (seen.has(d.url)) continue;
      seen.add(d.url);
      deals.push(d);
    }
  }
  return deals;
}
