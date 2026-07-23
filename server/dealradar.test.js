import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { beforeEach, describe, expect, it } from "vitest";

import { categorize, detectStore, extractPrice } from "./categorize.js";
import * as db from "./db.js";
import { mapHM } from "./stores/hm.js";
import { mapIkea } from "./stores/ikea.js";
import { mapNike } from "./stores/nike.js";
import { mapZara } from "./stores/zara.js";

describe("categorize", () => {
  it("buckets tech and clothing", () => {
    expect(categorize('Samsung 55" OLED TV + soundbar bundle $899')).toBe("Tech");
    expect(categorize("Levi's 501 jeans 40% off at Amazon")).toBe("Clothing");
  });
  it("falls back to Other", () => {
    expect(categorize("zzz completely unrelated thing")).toBe("Other");
  });
  it("matches whole words only — 'Steel' is not 'tee'", () => {
    expect(categorize("20-Piece Oneida Stainless Steel Flatware Set $35")).not.toBe("Clothing");
    expect(categorize("Disney Tron Steelbook (4K UHD) $26.70")).not.toBe("Clothing");
    expect(categorize("Nike graphic tees 2 for $30")).toBe("Clothing");
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

describe("scraper mappers", () => {
  it("maps Zara products, biggest discount first", () => {
    const data = {
      productGroups: [{
        elements: [{
          commercialComponents: [
            { name: "BOMBER JACKET", price: 1548, oldPrice: 12900, displayDiscountPercentage: 88,
              seo: { keyword: "bomber-jacket", seoProductId: "02969241" },
              xmedia: [{ extraInfo: { deliveryUrl: "https://static.zara.net/x.jpg" } }] },
            { name: "PLAIN TEE", price: 990, oldPrice: 1990, displayDiscountPercentage: 50,
              seo: { keyword: "plain-tee", seoProductId: "111" } },
            { name: "NO PRICE, SKIPPED", seo: { keyword: "x", seoProductId: "2" } },
          ],
        }],
      }],
    };
    const deals = mapZara(data);
    expect(deals).toHaveLength(2);
    expect(deals[0].title).toBe("BOMBER JACKET — $15.48 (was $129, 88% off)");
    expect(deals[0].url).toBe("https://www.zara.com/us/en/bomber-jacket-p02969241.html");
    expect(deals[0].image_url).toBe("https://static.zara.net/x.jpg?w=560");
    expect(extractPrice(deals[0].title)).toBe(15.48);
    expect(detectStore(deals[0].title, deals[0].url)).toBe("Zara");
  });

  it("maps men's H&M sale items, skips full-price and non-men's", () => {
    const data = {
      searchHits: {
        productList: [
          { productName: "Loose Jeans", url: "/en_us/productpage.1.html", productImage: "https://image.hm.com/a.jpg",
            mainCatCode: "men_jeans_loose",
            prices: [{ priceType: "redPrice", price: 3.99 }, { priceType: "whitePrice", price: 9.99 }] },
          { productName: "Full Price Jeans", url: "/en_us/productpage.2.html", mainCatCode: "men_jeans_loose",
            prices: [{ priceType: "whitePrice", price: 19.99 }] },
          { productName: "Ruffle Dress", url: "/en_us/productpage.3.html", mainCatCode: "ladies_dresses_mididresses",
            prices: [{ priceType: "redPrice", price: 3.99 }, { priceType: "whitePrice", price: 9.99 }] },
        ],
      },
    };
    const deals = mapHM(data);
    expect(deals).toHaveLength(1);
    expect(deals[0].title).toBe("Loose Jeans — $3.99 (was $9.99, 60% off)");
    expect(deals[0].url).toBe("https://www2.hm.com/en_us/productpage.1.html");
    expect(detectStore(deals[0].title, deals[0].url)).toBe("H&M");
  });
});

describe("nike mapper", () => {
  it("maps discounted groupings, skips full-price", () => {
    const data = {
      productGroupings: [
        { products: [{ copy: { title: "Nike C1TY", subTitle: "Shoes" },
          prices: { currentPrice: 82.97, initialPrice: 105, discountPercentage: 21 },
          pdpUrl: { url: "https://www.nike.com/t/c1ty-shoes/FZ3863-106" },
          colorwayImages: { portraitURL: "https://static.nike.com/x.jpg" } }] },
        { products: [{ copy: { title: "Full Price" },
          prices: { currentPrice: 100, initialPrice: 100 },
          pdpUrl: { url: "https://www.nike.com/t/full" } }] },
      ],
    };
    const deals = mapNike(data);
    expect(deals).toHaveLength(1);
    expect(deals[0].title).toBe("Nike C1TY (Shoes) — $82.97 (was $105, 21% off)");
    expect(deals[0].store).toBe("Nike");
    expect(deals[0].discount_pct).toBe(21);
  });
});

describe("ikea mapper", () => {
  it("parses JSON-LD with and without strikethrough price", () => {
    const ld = JSON.stringify({
      "@type": "ItemList",
      itemListElement: [
        { "@type": "ListItem", item: { "@type": "Product", name: "BAGGMUCK, Shoe tray",
          url: "https://www.ikea.com/us/en/p/baggmuck-70600287/", image: "https://ikea.com/b.jpg",
          offers: { priceSpecification: [
            { price: 3.99, priceCurrency: "USD" },
            { priceType: "https://schema.org/StrikethroughPrice", price: 4.99 },
          ] } } },
        { "@type": "ListItem", item: { "@type": "Product", name: "GÖRSNYGG, Storage case",
          url: "https://www.ikea.com/us/en/p/goersnygg-40504193/",
          offers: { priceSpecification: [{ price: 2.99 }] } } },
      ],
    });
    const deals = mapIkea(`<html><script type="application/ld+json">${ld}</script></html>`);
    expect(deals).toHaveLength(2);
    expect(deals[0].title).toBe("BAGGMUCK, Shoe tray — $3.99 (was $4.99, 20% off)");
    expect(deals[0].discount_pct).toBe(20);
    expect(deals[1].title).toBe("GÖRSNYGG, Storage case — $2.99 (last chance)");
    expect(deals[1].category).toBe("Home");
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
    expect(db.listDeals({ items: ["jeans"], maxPrice: 30 }).map((d) => d.store)).toEqual(["ASOS"]);
    expect(db.listDeals({ store: "Hollister" })).toHaveLength(1);
    expect(db.countDeals({ items: ["jeans"] })).toBe(2);
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

  it("item filter matches whole words, not substrings", () => {
    db.upsertDeals([
      { title: "Disney Tron Steelbook $26.70", url: "https://x.test/s1", source: "t", category: "Other" },
      { title: "Graphic Tee 2-pack $15", url: "https://x.test/s2", source: "t", category: "Clothing" },
      { title: "Plain tees $12", url: "https://x.test/s3", source: "t", category: "Clothing" },
    ]);
    expect(db.listDeals({ items: ["Tee"] }).map((d) => d.url)).toEqual(
      expect.arrayContaining(["https://x.test/s2", "https://x.test/s3"])
    );
    expect(db.listDeals({ items: ["Tee"] })).toHaveLength(2);
  });

  it("multiselect items ORs word-boundary matches, still excludes substrings", () => {
    db.upsertDeals([
      { title: "Disney Tron Steelbook $26.70", url: "https://x.test/m1", source: "t", category: "Other" },
      { title: "Graphic Tee 2-pack $15", url: "https://x.test/m2", source: "t", category: "Clothing" },
      { title: "Fleece Hoodie $30", url: "https://x.test/m3", source: "t", category: "Clothing" },
    ]);
    expect(db.listDeals({ items: ["Tee", "Hoodie"] }).map((d) => d.url).sort()).toEqual(
      ["https://x.test/m2", "https://x.test/m3"]
    );
  });

  it("refreshes scraped rows and prunes vanished ones", () => {
    db.upsertDeals([
      { title: "Jacket — $20 (was $100, 80% off)", url: "https://z.test/1", source: "zara.com", category: "Clothing", price: 20 },
      { title: "Tee — $5", url: "https://z.test/2", source: "zara.com", category: "Clothing", price: 5 },
    ]);
    db.refreshDealData([{ title: "Jacket — $25 (was $100, 75% off)", url: "https://z.test/1", price: 25 }]);
    expect(db.pruneMissing("zara.com", ["https://z.test/1"])).toBe(1);
    const rows = db.listDeals();
    expect(rows).toHaveLength(1);
    expect(rows[0].price).toBe(25);
    expect(rows[0].title).toContain("75% off");
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
