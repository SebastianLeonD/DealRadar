// Direct retailer scrapers — the same unofficial JSON endpoints each store's
// own site calls. These break silently when a retailer changes endpoints or
// bot rules; per-source health in /api/status is how you notice.
// ponytail: Hollister/PacSun/ASOS reject non-browser traffic (Akamai 403) —
// they're covered by Slickdeals search feeds in sources.js instead.

const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
  Accept: "application/json",
};

async function getJSON(url) {
  const resp = await fetch(url, { headers: HEADERS, signal: AbortSignal.timeout(20000) });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

const usd = (n) => (Number.isInteger(n) ? `$${n}` : `$${n.toFixed(2)}`);

// ---------------------------------------------------------------------------
// Zara — category products endpoint, prices in cents. Category ids come from
// zara.com/us/en/categories?ajax=true (names WOMAN>SALE / MAN>SALE) and
// rotate occasionally; update here when the source starts failing.
// ---------------------------------------------------------------------------

export const ZARA_SALE_CATEGORIES = [
  { id: 2418848, label: "women" }, // WOMAN > SALE
  { id: 2439352, label: "men" },   // MAN > SALE > SHOP ALL (top-level MAN SALE id returns empty)
];
const ZARA_PER_CATEGORY = 60; // keep the board from becoming all-Zara

/** Pure mapper: Zara category-products JSON -> deals, biggest discounts first. */
export function mapZara(data, limit = ZARA_PER_CATEGORY) {
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
    return {
      title: `${p.name} — ${usd(price)} (was ${usd(was)}, ${pct}% off)`,
      url: `https://www.zara.com/us/en/${p.seo.keyword}-p${p.seo.seoProductId}.html`,
      source: "zara.com",
      image_url: img ? `${img}${img.includes("?") ? "&" : "?"}w=560` : null,
      posted_at: null,
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

// ---------------------------------------------------------------------------
// H&M — search API with the sale facet. There's no browsable "all sale"
// endpoint reachable server-side, so a few broad queries approximate it.
// redPrice = sale price, whitePrice = original.
// ---------------------------------------------------------------------------

const HM_QUERIES = ["dress", "jeans", "shirt", "jacket", "shoes", "hoodie"];
const HM_PAGE_SIZE = 30;

/** Pure mapper: H&M search-results JSON -> deals (sale items only). */
export function mapHM(data) {
  const deals = [];
  for (const p of data.searchHits?.productList ?? []) {
    const red = p.prices?.find((x) => x.priceType === "redPrice")?.price;
    const white = p.prices?.find((x) => x.priceType === "whitePrice")?.price;
    if (!p.productName || !p.url || !red || !white || red >= white) continue;
    const pct = Math.round((1 - red / white) * 100);
    deals.push({
      title: `${p.productName} — ${usd(red)} (was ${usd(white)}, ${pct}% off)`,
      url: `https://www2.hm.com${p.url}`,
      source: "hm.com",
      image_url: p.productImage ?? p.modelImage ?? null,
      posted_at: null,
    });
  }
  return deals;
}

export async function fetchHM() {
  const seen = new Set();
  const deals = [];
  for (const q of HM_QUERIES) {
    const params = new URLSearchParams({
      query: q, page: "1", sort: "RELEVANCE", "page-size": String(HM_PAGE_SIZE),
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

/** All direct scrapers, in the same {name, fetch} shape sources.js uses. */
export const SCRAPERS = [
  { name: "zara.com", fetch: fetchZara },
  { name: "hm.com", fetch: fetchHM },
];
