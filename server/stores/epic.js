// Epic Games — weekly free games from the freeGamesPromotions endpoint.
// Only games free RIGHT NOW (active promotionalOffers + $0 discount price).
import { getJSON, usd } from "./util.js";

/** Pure mapper: Epic freeGamesPromotions JSON -> deals. */
export function mapEpic(data) {
  const deals = [];
  for (const el of data.data?.Catalog?.searchStore?.elements ?? []) {
    const active = el.promotions?.promotionalOffers?.length > 0;
    const priceInfo = el.price?.totalPrice;
    if (!el.title || !active || priceInfo?.discountPrice !== 0) continue;
    const slug =
      el.offerMappings?.[0]?.pageSlug ?? el.catalogNs?.mappings?.[0]?.pageSlug ?? el.productSlug;
    if (!slug) continue;
    const was = (priceInfo.originalPrice ?? 0) / 100;
    const img = (el.keyImages ?? []).find((i) => i.type === "OfferImageWide")?.url
      ?? el.keyImages?.[0]?.url ?? null;
    deals.push({
      title: `${el.title} — FREE this week${was ? ` (was ${usd(was)}, 100% off)` : ""}`,
      url: `https://store.epicgames.com/en-US/p/${slug}`,
      source: "epicgames.com",
      category: "Gaming",
      store: "Epic Games",
      price: 0,
      image_url: img,
      posted_at: null,
      discount_pct: 100,
    });
  }
  return deals;
}

export async function fetchEpic() {
  const data = await getJSON(
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US"
  );
  return mapEpic(data);
}
