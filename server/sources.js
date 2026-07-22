// Deal feed fetchers. All sources are free public RSS/Atom feeds — no API keys.
import Parser from "rss-parser";

export const FEEDS = [
  {
    name: "slickdeals",
    url: "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
  },
  { name: "r/deals", url: "https://www.reddit.com/r/deals/.rss" },
  { name: "r/buildapcsales", url: "https://www.reddit.com/r/buildapcsales/.rss" },
  { name: "r/frugalmalefashion", url: "https://www.reddit.com/r/frugalmalefashion/.rss" },
  { name: "r/FrugalFemaleFashion", url: "https://www.reddit.com/r/FrugalFemaleFashion/.rss" },
  { name: "r/GameDeals", url: "https://www.reddit.com/r/GameDeals/.rss" },
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

/** Fetch every configured feed. Returns {deals, errors} — one source failing
    never blocks the rest. */
export async function fetchAll() {
  const results = await Promise.allSettled(FEEDS.map((f) => fetchFeed(f.name, f.url)));
  const deals = [];
  const errors = [];
  results.forEach((r, i) => {
    if (r.status === "fulfilled") deals.push(...r.value);
    else errors.push(`${FEEDS[i].name}: ${r.reason?.message ?? r.reason}`);
  });
  return { deals, errors };
}
