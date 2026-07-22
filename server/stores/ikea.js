// IKEA — "Last chance to buy" pages are server-rendered with schema.org
// JSON-LD ItemLists (name, url, image, price, strikethrough was-price).
// No JSON API needed; parse the embedded structured data.
import { getText, usd } from "./util.js";

const PAGES = [
  "https://www.ikea.com/us/en/cat/last-chance/",
  "https://www.ikea.com/us/en/cat/last-chance/?page=2",
];

/** Pure mapper: page HTML -> deals from the embedded JSON-LD ItemList. */
export function mapIkea(html) {
  const deals = [];
  for (const m of html.matchAll(/<script type="application\/ld\+json">(.*?)<\/script>/gs)) {
    let ld;
    try { ld = JSON.parse(m[1]); } catch { continue; }
    const nodes = ld["@graph"] ?? (Array.isArray(ld) ? ld : [ld]);
    for (const node of nodes) {
      // the ItemList sits at top level or under a CollectionPage's mainEntity
      const l = node["@type"] === "ItemList" ? node
        : node.mainEntity?.["@type"] === "ItemList" ? node.mainEntity : null;
      if (!l) continue;
      for (const el of l.itemListElement ?? []) {
        const it = el.item;
        if (!it?.name || !it.url) continue;
        const specs = it.offers?.priceSpecification ?? [];
        const now = specs.find((s) => !s.priceType)?.price;
        const was = specs.find((s) => s.priceType?.includes("Strikethrough"))?.price;
        if (!now) continue;
        const pct = was && was > now ? Math.round((1 - now / was) * 100) : null;
        deals.push({
          title: pct
            ? `${it.name} — ${usd(now)} (was ${usd(was)}, ${pct}% off)`
            : `${it.name} — ${usd(now)} (last chance)`,
          url: it.url,
          source: "ikea.com",
          category: "Home",
          store: "IKEA",
          image_url: it.image ?? null,
          posted_at: null,
          discount_pct: pct,
        });
      }
    }
  }
  return deals;
}

export async function fetchIkea() {
  const seen = new Set();
  const deals = [];
  for (const page of PAGES) {
    for (const d of mapIkea(await getText(page))) {
      if (seen.has(d.url)) continue;
      seen.add(d.url);
      deals.push(d);
    }
  }
  return deals;
}
