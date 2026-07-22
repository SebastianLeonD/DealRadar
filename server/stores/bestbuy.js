// Best Buy — official developer API (free key from developer.bestbuy.com).
// Only registered in SCRAPERS when BESTBUY_API_KEY is set in .env.
import { getJSON, usd } from "./util.js";

/** Pure mapper: Best Buy products JSON -> deals. */
export function mapBestBuy(data) {
  const deals = [];
  for (const p of data.products ?? []) {
    if (!p.name || !p.url || !p.salePrice || !p.regularPrice || p.salePrice >= p.regularPrice) continue;
    const pct = Math.round((p.percentSavings ?? (1 - p.salePrice / p.regularPrice) * 100));
    deals.push({
      title: `${p.name} — ${usd(p.salePrice)} (was ${usd(p.regularPrice)}, ${pct}% off)`,
      url: p.url,
      source: "bestbuy.com",
      category: "Tech",
      store: "Best Buy",
      image_url: p.image ?? null,
      posted_at: null,
      discount_pct: pct,
    });
  }
  return deals;
}

export async function fetchBestBuy() {
  const key = process.env.BESTBUY_API_KEY;
  const params = new URLSearchParams({
    apiKey: key, format: "json", pageSize: "60",
    sort: "percentSavings.dsc",
    show: "name,salePrice,regularPrice,percentSavings,url,image",
  });
  const data = await getJSON(
    `https://api.bestbuy.com/v1/products((salePrice<regularPrice)&onlineAvailability=true)?${params}`
  );
  return mapBestBuy(data);
}
