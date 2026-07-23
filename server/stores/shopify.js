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

// Marine Layer's outlet is mixed; product_type is prefixed "Mens"/"Womens".
const mensProductType = (p) => (p.product_type ?? "").toLowerCase().startsWith("mens");
// Gymshark's outlet is mixed; a "Mens" tag (and no "Womens") is the reliable signal.
const gymsharkMens = (p) => {
  const tags = (p.tags ?? []).map((t) => t.toLowerCase());
  return tags.includes("mens") && !tags.includes("womens");
};

export const fetchTaylorStitch = makeShopifyFetcher({
  domain: "www.taylorstitch.com", handle: "mens-last-call",
  store: "Taylor Stitch", source: "taylorstitch.com",
});
export const fetchMarineLayer = makeShopifyFetcher({
  domain: "www.marinelayer.com", handle: "last-call",
  store: "Marine Layer", source: "marinelayer.com", keep: mensProductType,
});
export const fetchChubbies = makeShopifyFetcher({
  domain: "chubbiesshorts.com", handle: "clearance",
  store: "Chubbies", source: "chubbiesshorts.com",
});
export const fetchGymshark = makeShopifyFetcher({
  domain: "gymshark.com", handle: "outlet",
  store: "Gymshark", source: "gymshark.com", keep: gymsharkMens,
});
export const fetchParachute = makeShopifyFetcher({
  domain: "www.parachutehome.com", handle: "all-sale",
  store: "Parachute", source: "parachutehome.com", category: "Home",
});
