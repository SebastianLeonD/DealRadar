// Gap + Old Navy — same commerce search gateway (api.gap.com), no auth. cid is
// the men's-sale category id per brand. Prices/percentages come back as strings.
// Image /webcontent paths are served from each brand's own site host.
import { getJSON, usd } from "./util.js";

const num = (x) => Number(x);

/** Pure mapper: gap search JSON -> deals. Takes the first discounted styleColor
    per style (effectivePrice < regularPrice). */
export function mapGapBrand(data, { store, urlBase, imgHost }) {
  const deals = [];
  for (const p of data.products ?? []) {
    const sc = (p.styleColors ?? []).find(
      (c) => num(c.effectivePrice) > 0 && num(c.effectivePrice) < num(c.regularPrice)
    );
    if (!sc || !p.styleName) continue;
    const price = num(sc.effectivePrice);
    const was = num(sc.regularPrice);
    const pct = num(sc.percentageOff) || Math.round((1 - price / was) * 100);
    const path = sc.images?.[0]?.path;
    const img = path ? `${imgHost}${path.startsWith("/") ? "" : "/"}${path}` : null;
    deals.push({
      title: `${p.styleName} — ${usd(price)} (was ${usd(was)}, ${pct}% off)`,
      url: `${urlBase}${sc.ccId}`,
      source: store === "Gap" ? "gap.com" : "oldnavy.com",
      category: "Clothing",
      store,
      image_url: img,
      posted_at: null,
      colors: sc.ccName ? sc.ccName.toLowerCase() : null,
      sizes: null, // this endpoint has no size-level data
      discount_pct: pct,
    });
  }
  return deals;
}

const API = "https://api.gap.com/commerce/search/products/v2/cc";

export async function fetchGap() {
  const data = await getJSON(`${API}?cid=65289&brand=gap&market=us&locale=en_US&pageSize=90`);
  return mapGapBrand(data, {
    store: "Gap",
    urlBase: "https://www.gap.com/browse/product.do?pid=",
    imgHost: "https://www.gap.com",
  });
}

export async function fetchOldNavy() {
  // ~1979 items; page 1 only (~90 cap) keeps the board balanced.
  const data = await getJSON(`${API}?cid=26061&brand=on&market=us&locale=en_US&pageSize=90`);
  return mapGapBrand(data, {
    store: "Old Navy",
    urlBase: "https://oldnavy.gap.com/browse/product.do?pid=",
    imgHost: "https://oldnavy.gap.com",
  });
}
