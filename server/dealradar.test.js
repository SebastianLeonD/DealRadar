import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import Parser from "rss-parser";
import { beforeEach, describe, expect, it } from "vitest";

import { categorize, detectStore, extractPrice } from "./categorize.js";
import * as db from "./db.js";
import { entryImage } from "./sources.js";

describe("categorize", () => {
  it("buckets tech, clothing, gaming", () => {
    expect(categorize('Samsung 55" OLED TV + soundbar bundle $899')).toBe("Tech");
    expect(categorize("Levi's 501 jeans 40% off at Amazon")).toBe("Clothing");
    expect(categorize("PS5 DualSense controller $49")).toBe("Gaming");
  });
  it("falls back to Other", () => {
    expect(categorize("zzz completely unrelated thing")).toBe("Other");
  });
});

describe("extractPrice", () => {
  it("takes the first (sale) price", () => {
    expect(extractPrice("Levi's 501 Jeans $39.99 (was $70)")).toBe(39.99);
    expect(extractPrice("Hollister shorts $ 15 reg. $40")).toBe(15);
  });
  it("handles thousands separators", () => {
    expect(extractPrice('LG C4 65" OLED $1,299.99')).toBe(1299.99);
  });
  it("returns null when no price", () => {
    expect(extractPrice("50% off everything at ASOS")).toBeNull();
  });
});

describe("detectStore", () => {
  it("detects from title", () => {
    expect(detectStore("Hollister jeans BOGO 50% off")).toBe("Hollister");
    expect(detectStore("PacSun: all shorts 2 for $40")).toBe("PacSun");
    expect(detectStore("Ralph Lauren polo sale 40% off")).toBe("Ralph Lauren");
    expect(detectStore("New Balance 574 $59.99")).toBe("New Balance");
  });
  it("prefers the link domain over brand names in the title", () => {
    expect(detectStore("Levi's 501 Jeans $39.99 at Amazon", "https://www.amazon.com/levis501")).toBe("Amazon");
  });
  it("ignores non-store domains like reddit", () => {
    expect(detectStore("ASOS extra 20% off", "https://www.reddit.com/r/fmf/comments/x")).toBe("ASOS");
  });
  it("returns null when unknown", () => {
    expect(detectStore("Random local shop clearance")).toBeNull();
  });
});

describe("entryImage", () => {
  const parser = new Parser({
    customFields: { item: [["media:thumbnail", "mediaThumbnail", { keepArray: true }]] },
  });

  it("reads media:thumbnail from reddit-style atom", async () => {
    const atom = `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">
  <entry>
    <title>Nike Killshot 2 $63.71</title>
    <link href="https://www.reddit.com/r/frugalmalefashion/comments/abc/x/"/>
    <updated>2099-01-01T00:00:00+00:00</updated>
    <media:thumbnail url="https://external-preview.redd.it/killshot.jpg?width=640&amp;s=tok"/>
  </entry>
</feed>`;
    const feed = await parser.parseString(atom);
    expect(entryImage(feed.items[0])).toBe("https://external-preview.redd.it/killshot.jpg?width=640&s=tok");
  });

  it("reads the first <img> from slickdeals-style html descriptions", async () => {
    const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Slickdeals</title>
  <item>
    <title>LG C4 65" OLED TV $1,299.99</title>
    <link>https://slickdeals.net/f/123-lg-c4</link>
    <description>&lt;img src="https://static.slickdealscdn.com/attachment/lgc4.jpg" /&gt; great TV deal</description>
  </item>
</channel></rss>`;
    const feed = await parser.parseString(rss);
    expect(entryImage(feed.items[0])).toBe("https://static.slickdealscdn.com/attachment/lgc4.jpg");
  });

  it("returns null when there is no image", async () => {
    const rss = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>x</title>
  <item><title>Plain deal $5</title><link>https://x.test/plain</link>
  <description>no picture here</description></item>
</channel></rss>`;
    const feed = await parser.parseString(rss);
    expect(entryImage(feed.items[0])).toBeNull();
  });
});

describe("db", () => {
  beforeEach(() => {
    process.env.DEALRADAR_DB = path.join(mkdtempSync(path.join(tmpdir(), "dr-")), "test.db");
    db.resetForTests();
  });

  it("dedupes by url and stores fields", () => {
    const deal = {
      title: "RTX 4070 $499", url: "https://x.test/1", source: "t",
      category: "Tech", store: "Amazon", price: 499, image_url: "https://img.test/a.jpg",
    };
    expect(db.upsertDeals([deal])).toBe(1);
    expect(db.upsertDeals([deal])).toBe(0);
    const rows = db.listDeals();
    expect(rows).toHaveLength(1);
    expect(rows[0].image_url).toBe("https://img.test/a.jpg");
  });

  it("filters by item, store, and price", () => {
    db.upsertDeals([
      { title: "Levi's jeans $39.99", url: "https://x.test/1", source: "t", category: "Clothing", store: "Amazon", price: 39.99 },
      { title: "ASOS jeans $25", url: "https://x.test/2", source: "t", category: "Clothing", store: "ASOS", price: 25 },
      { title: "Hollister shorts, no price listed", url: "https://x.test/3", source: "t", category: "Clothing", store: "Hollister" },
    ]);
    expect(db.listDeals({ item: "jeans", maxPrice: 30 }).map((d) => d.store)).toEqual(["ASOS"]);
    expect(db.listDeals({ store: "Hollister" })).toHaveLength(1);
    expect(db.listDeals({ maxPrice: 1000 })).toHaveLength(2); // no-price deals excluded
    expect(new Set(db.storeCounts().map((s) => s.store))).toEqual(new Set(["Amazon", "ASOS", "Hollister"]));
  });

  it("applies the freshness window and ordering", () => {
    db.upsertDeals([
      { title: "fresh deal $10", url: "https://x.test/f", source: "t", category: "Other", posted_at: "2099-01-01T00:00:00Z" },
      { title: "ancient deal $10", url: "https://x.test/o", source: "t", category: "Other", posted_at: "2001-01-01T00:00:00Z" },
    ]);
    expect(db.listDeals({ maxAgeHours: 48 }).map((d) => d.title)).toEqual(["fresh deal $10"]);
    expect(db.listDeals({ order: "new" })[0].title).toBe("fresh deal $10");
    expect(db.listDeals()).toHaveLength(2);
  });

  it("counts categories", () => {
    db.upsertDeals([
      { title: "RTX 4070 $499", url: "https://x.test/1", source: "t", category: "Tech" },
      { title: "Nike hoodie $30", url: "https://x.test/2", source: "t", category: "Clothing" },
    ]);
    const counts = Object.fromEntries(db.categoryCounts().map((c) => [c.category, c.n]));
    expect(counts).toEqual({ Tech: 1, Clothing: 1 });
  });
});
