// Steam — official featured-categories endpoint, "specials" section.
// Prices are in cents.
import { getJSON, usd } from "./util.js";

/** Pure mapper: Steam featuredcategories JSON -> deals. */
export function mapSteam(data) {
  const deals = [];
  for (const p of data.specials?.items ?? []) {
    if (!p.name || !p.id || !p.discounted || !p.final_price || !p.original_price) continue;
    const price = p.final_price / 100;
    const was = p.original_price / 100;
    deals.push({
      title: `${p.name} — ${usd(price)} (was ${usd(was)}, ${p.discount_percent}% off)`,
      url: `https://store.steampowered.com/app/${p.id}`,
      source: "steampowered.com",
      category: "Gaming",
      store: "Steam",
      image_url: p.large_capsule_image ?? p.small_capsule_image ?? null,
      posted_at: null,
      discount_pct: p.discount_percent ?? null,
    });
  }
  return deals;
}

export async function fetchSteam() {
  const data = await getJSON("https://store.steampowered.com/api/featuredcategories?cc=US&l=english");
  return mapSteam(data);
}
