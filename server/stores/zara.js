// Zara — category products endpoint, prices in cents. Category ids come from
// zara.com/us/en/categories?ajax=true (names like MAN>SALE>SHOP ALL) and
// rotate occasionally; update here when this source starts failing.
import { getJSON, usd } from "./util.js";

export const ZARA_SALE_CATEGORIES = [
  { id: 2439352, label: "men" }, // MAN > SALE > SHOP ALL (top-level MAN SALE id returns empty)
];
const PER_CATEGORY = 120; // keep the board from becoming all-Zara

/** Pure mapper: Zara category-products JSON -> deals, biggest discounts first. */
export function mapZara(data, limit = PER_CATEGORY) {
  const products = [];
  for (const g of data.productGroups ?? [])
    for (const el of g.elements ?? [])
      for (const p of el.commercialComponents ?? []) {
        if (!p?.name || !p.price || !p.oldPrice || !p.seo?.keyword || !p.seo?.seoProductId) continue;
        products.push(p);
      }
  products.sort((a, b) => (b.displayDiscountPercentage ?? 0) - (a.displayDiscountPercentage ?? 0));
  return products.slice(0, limit).map((p) => {
    const price = p.price / 100;
    const was = p.oldPrice / 100;
    const pct = p.displayDiscountPercentage ?? Math.round((1 - price / was) * 100);
    const img =
      p.xmedia?.[0]?.extraInfo?.deliveryUrl ??
      p.detail?.colors?.[0]?.xmedia?.[0]?.extraInfo?.deliveryUrl ?? null;
    const colors = (p.availableColors ?? [])
      .map((c) => c.colorName?.toLowerCase())
      .filter(Boolean)
      .join(",");
    return {
      title: `${p.name} — ${usd(price)} (was ${usd(was)}, ${pct}% off)`,
      url: `https://www.zara.com/us/en/${p.seo.keyword}-p${p.seo.seoProductId}.html`,
      source: "zara.com",
      category: "Clothing",
      image_url: img ? `${img}${img.includes("?") ? "&" : "?"}w=560` : null,
      posted_at: null,
      colors: colors || null,
      sizes: null, // Zara's listing endpoint has no size data
      discount_pct: pct,
    };
  });
}

export async function fetchZara() {
  const deals = [];
  for (const cat of ZARA_SALE_CATEGORIES) {
    const data = await getJSON(`https://www.zara.com/us/en/category/${cat.id}/products?ajax=true`);
    deals.push(...mapZara(data));
  }
  return deals;
}
