// GOG — public catalog API filtered to discounted games.
import { getJSON } from "./util.js";

const LIMIT = 48;

/** Pure mapper: GOG catalog JSON -> deals. */
export function mapGOG(data) {
  const deals = [];
  for (const p of data.products ?? []) {
    const final = p.price?.finalMoney?.amount;
    const base = p.price?.baseMoney?.amount;
    if (!p.title || !p.storeLink || !final || !base || Number(final) >= Number(base)) continue;
    const pct = Math.round((1 - Number(final) / Number(base)) * 100);
    deals.push({
      title: `${p.title} — $${final} (was $${base}, ${pct}% off)`,
      url: p.storeLink,
      source: "gog.com",
      category: "Gaming",
      store: "GOG",
      image_url: p.coverHorizontal ?? null,
      posted_at: null,
      discount_pct: pct,
    });
  }
  return deals;
}

export async function fetchGOG() {
  const data = await getJSON(
    `https://catalog.gog.com/v1/catalog?limit=${LIMIT}&order=desc:trending&discounted=eq:true&productType=in:game&countryCode=US&locale=en-US&currencyCode=USD`
  );
  return mapGOG(data);
}
