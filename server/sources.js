// Deal feed fetchers. All sources are free public RSS/Atom feeds — no API keys.
import Parser from "rss-parser";
import { SCRAPERS } from "./scrapers.js";

// Per-store Slickdeals search feeds cover retailers whose own sites block
// server-side requests (Akamai 403): Hollister, PacSun, ASOS — plus Amazon,
// where Slickdeals' human curation beats scraping anyway.
const sdSearch = (q) => ({
  name: `slickdeals:${q}`,
  url: `https://slickdeals.net/newsearch.php?q=${encodeURIComponent(q)}&searcharea=deals&searchin=first&rss=1`,
});

export const FEEDS = [
  {
    name: "slickdeals",
    url: "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
  },
  { name: "r/deals", url: "https://www.reddit.com/r/deals/.rss" },
  { name: "r/buildapcsales", url: "https://www.reddit.com/r/buildapcsales/.rss" },
  { name: "r/frugalmalefashion", url: "https://www.reddit.com/r/frugalmalefashion/.rss" },
  { name: "r/GameDeals", url: "https://www.reddit.com/r/GameDeals/.rss" },
  sdSearch("hollister"),
  sdSearch("pacsun"),
  sdSearch("asos"),
  sdSearch("amazon"),
];

/** Every source — RSS feeds and direct retailer scrapers — as {name, fetch}. */
export const ALL_SOURCES = [
  ...FEEDS.map((f) => ({ name: f.name, fetch: () => fetchFeed(f.name, f.url) })),
  ...SCRAPERS,
];

const parser = new Parser({
  timeout: 15000,
  headers: { "User-Agent": "DealRadar/0.4 (personal deal aggregator)" },
  customFields: {
    item: [
      ["media:thumbnail", "mediaThumbnail", { keepArray: true }],
      ["media:content", "mediaContent", { keepArray: true }],
    ],
  },
});

const IMG_RE = /<img[^>]+src=["']([^"']+)["']/i;

function unescapeHtml(s) {
  return s
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#0?39;/g, "'");
}

/** Best product image for a feed entry: media:thumbnail / media:content on
    Reddit Atom entries, else the first <img> in the entry's HTML body
    (Slickdeals and Reddit link posts embed one). */
export function entryImage(item) {
  for (const key of ["mediaThumbnail", "mediaContent"]) {
    for (const m of item[key] ?? []) {
      const url = m?.$?.url;
      if (url && url.startsWith("http")) return unescapeHtml(url);
    }
  }
  for (const html of [item.content, item["content:encoded"], item.summary]) {
    if (!html) continue;
    const m = IMG_RE.exec(html);
    if (m) {
      const url = unescapeHtml(m[1]);
      if (url.startsWith("http")) return url;
    }
  }
  return null;
}

export async function fetchFeed(name, url) {
  const feed = await parser.parseURL(url);
  const deals = [];
  for (const item of feed.items ?? []) {
    const title = (item.title ?? "").trim();
    const link = (item.link ?? "").trim();
    if (!title || !link) continue;
    deals.push({
      title,
      url: link,
      source: name,
      image_url: entryImage(item),
      posted_at: item.isoDate ?? null,
    });
  }
  return deals;
}

/** Fetch every source (feeds + scrapers). Returns {deals, errors, health} —
    one source failing never blocks the rest; health has a row per source. */
export async function fetchAll() {
  const deals = [];
  const errors = [];
  const health = [];
  await Promise.all(
    ALL_SOURCES.map(async (s) => {
      const started = Date.now();
      try {
        const d = await s.fetch();
        deals.push(...d);
        health.push({ source: s.name, ok: true, count: d.length, ms: Date.now() - started });
      } catch (e) {
        const error = String(e?.message ?? e);
        errors.push(`${s.name}: ${error}`);
        health.push({ source: s.name, ok: false, count: 0, error, ms: Date.now() - started });
      }
    })
  );
  health.sort((a, b) => a.source.localeCompare(b.source));
  return { deals, errors, health };
}
