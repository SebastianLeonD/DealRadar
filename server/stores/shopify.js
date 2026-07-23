// Generic Shopify markdown fetcher. Every Shopify storefront exposes
// /collections/{handle}/products.json; a markdown = variant with
// compare_at_price > price > 0. One mapper, one fetcher factory, per-store cfg.
import { getJSON, usd } from "./util.js";

const num = (x) => Number(x) || 0;

// index of an option by name (case-insensitive) within a product's options[]
const optIndex = (product, name) =>
  (product.options ?? []).findIndex((o) => o.name?.toLowerCase() === name.toLowerCase());

// variant.option1/2/3 value for a given option index (0-based)
const optValue = (variant, idx) => (idx < 0 ? null : variant[`option${idx + 1}`]);

/** Pure mapper: Shopify products.json -> deals.
    cfg: { domain, store, source, category?, keep?(product) } */
export function mapShopify(data, cfg) {
  const category = cfg.category ?? "Clothing";
  const deals = [];
  for (const p of data.products ?? []) {
    if (cfg.keep && !cfg.keep(p)) continue;
    const variant = (p.variants ?? []).find(
      (v) => num(v.compare_at_price) > num(v.price) && num(v.price) > 0
    );
    if (!variant) continue;
    const price = num(variant.price);
    const was = num(variant.compare_at_price);
    const pct = Math.round((1 - price / was) * 100);

    const sizeIdx = optIndex(p, "Size");
    const colorIdx = optIndex(p, "Color");
    const sizes =
      sizeIdx < 0
        ? null
        : [...new Set(
            (p.variants ?? [])
              .filter((v) => v.available && optValue(v, sizeIdx))
              .map((v) => optValue(v, sizeIdx))
          )].join(",") || null;
    const colors =
      colorIdx < 0
        ? null
        : [...new Set(
            (p.variants ?? [])
              .map((v) => optValue(v, colorIdx))
              .filter(Boolean)
              .map((c) => c.toLowerCase())
          )].join(",") || null;

    deals.push({
      title: `${p.title} — ${usd(price)} (was ${usd(was)}, ${pct}% off)`,
      url: `https://${cfg.domain}/products/${p.handle}`,
      source: cfg.source,
      category,
      store: cfg.store,
      image_url: p.images?.[0]?.src ?? null,
      posted_at: null,
      colors,
      sizes,
      discount_pct: pct,
    });
  }
  return deals;
}

export function makeShopifyFetcher(cfg) {
  return async () => {
    const data = await getJSON(
      `https://${cfg.domain}/collections/${cfg.handle}/products.json?limit=100`
    );
    return mapShopify(data, cfg);
  };
}

// Gymshark's outlet is mixed; a "Mens" tag (and no "Womens") is the reliable signal.
const gymsharkMens = (p) => {
  const tags = (p.tags ?? []).map((t) => t.toLowerCase());
  return tags.includes("mens") && !tags.includes("womens");
};

export const fetchGymshark = makeShopifyFetcher({
  domain: "gymshark.com", handle: "outlet",
  store: "Gymshark", source: "gymshark.com", keep: gymsharkMens,
});
export const fetchParachute = makeShopifyFetcher({
  domain: "www.parachutehome.com", handle: "all-sale",
  store: "Parachute", source: "parachutehome.com", category: "Home",
});

// Quality home brands, no gender filter — mixed price bands (user filters by price).
export const fetchCoyuchi = makeShopifyFetcher({
  domain: "coyuchi.com", handle: "sale",
  store: "Coyuchi", source: "coyuchi.com", category: "Home",
});
export const fetchBrooklinen = makeShopifyFetcher({
  domain: "brooklinen.com", handle: "last-call",
  store: "Brooklinen", source: "brooklinen.com", category: "Home",
});
export const fetchOurPlace = makeShopifyFetcher({
  domain: "fromourplace.com", handle: "sale",
  store: "Our Place", source: "fromourplace.com", category: "Home",
});

// "For Your Room" — small room upgrades (lights, rugs, decor, air/scent). Own
// tab via the distinct category; mixed prices, user filters with the <$100 cap.
export const fetchMitzi = makeShopifyFetcher({
  domain: "mitzi.com", handle: "sale",
  store: "Mitzi", source: "mitzi.com", category: "For Your Room",
});
export const fetchColorCord = makeShopifyFetcher({
  domain: "colorcord.com", handle: "sale",
  store: "Color Cord", source: "colorcord.com", category: "For Your Room",
});
export const fetchVitruvi = makeShopifyFetcher({
  domain: "vitruvi.com", handle: "sale",
  store: "Vitruvi", source: "vitruvi.com", category: "For Your Room",
});
export const fetchJonathanY = makeShopifyFetcher({
  domain: "jonathany.com", handle: "deals",
  store: "Jonathan Y", source: "jonathany.com", category: "For Your Room",
});
export const fetchLuluGeorgia = makeShopifyFetcher({
  domain: "luluandgeorgia.com", handle: "sale",
  store: "Lulu and Georgia", source: "luluandgeorgia.com", category: "For Your Room",
});
