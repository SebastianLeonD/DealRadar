// Deal categorization: keyword categories (always on), store detection,
// price extraction, and optional Claude scoring when ANTHROPIC_API_KEY is set.

export const CATEGORIES = ["Tech", "Clothing", "Gaming", "Home", "Beauty", "Food", "Sports", "Other"];

const KEYWORDS = {
  Tech: [
    "laptop", "monitor", "ssd", "gpu", "cpu", "ryzen", "intel", "nvidia", "rtx",
    "radeon", "tv", "oled", "headphone", "earbud", "airpods", "iphone", "ipad",
    "samsung", "pixel", "tablet", "router", "keyboard", "mouse", "webcam",
    "charger", "usb", "hdmi", "camera", "drone", "smartwatch", "kindle", "echo",
    "alexa", "speaker", "soundbar", "ram", "motherboard", "nas", "hard drive",
    "microsd", "power bank", "macbook",
  ],
  Clothing: [
    "shirt", "tee", "hoodie", "jacket", "jeans", "pants", "chinos", "sneaker",
    "shoe", "boot", "sock", "underwear", "coat", "sweater", "levi", "nike",
    "adidas", "uniqlo", "polo", "dress", "shorts", "hat", "beanie", "flannel",
    "denim", "loafers", "apparel",
  ],
  Gaming: [
    "game", "steam", "playstation", "ps5", "xbox", "nintendo", "switch",
    "controller", "dlc", "gog", "epic games", "console", "joy-con", "gamepass",
    "game pass", "psn",
  ],
  Home: [
    "vacuum", "roomba", "air fryer", "instant pot", "mattress", "pillow",
    "blender", "coffee", "espresso", "cookware", "knife", "furniture", "desk",
    "chair", "lamp", "thermostat", "tool", "drill", "dewalt", "milwaukee",
    "ryobi", "storage", "sheets", "towel", "humidifier", "purifier", "grill", "mower",
  ],
  Beauty: [
    "skincare", "moisturizer", "sunscreen", "shampoo", "razor", "trimmer",
    "electric toothbrush", "cologne", "perfume", "makeup", "serum",
  ],
  Food: [
    "snack", "coffee beans", "protein", "cereal", "chocolate", "grocery",
    "pizza", "burger", "meal kit", "gift card",
  ],
  Sports: [
    "bike", "bicycle", "dumbbell", "treadmill", "kayak", "tent", "camping",
    "hiking", "golf", "fitness", "yoga", "backpack", "cooler",
  ],
};

// Retailer detection — matched against link domain first, then title.
const STORES = [
  ["Abercrombie", ["abercrombie"]],
  ["Hollister", ["hollister"]],
  ["PacSun", ["pacsun"]],
  ["Ralph Lauren", ["ralph lauren", "ralphlauren", "polo rl"]],
  ["American Eagle", ["american eagle", "ae.com", "aerie"]],
  ["Urban Outfitters", ["urban outfitters", "urbanoutfitters"]],
  ["J.Crew", ["j.crew", "jcrew", "j crew"]],
  ["Banana Republic", ["banana republic", "bananarepublic"]],
  ["Vans", ["vans.com", " vans "]],
  ["Converse", ["converse"]],
  ["New Balance", ["new balance", "newbalance"]],
  ["Foot Locker", ["foot locker", "footlocker"]],
  ["ASOS", ["asos"]],
  ["Zara", ["zara"]],
  ["H&M", ["h&m", "hm.com"]],
  ["Uniqlo", ["uniqlo"]],
  ["Old Navy", ["old navy", "oldnavy"]],
  ["Gap", ["gap.com", " gap "]],
  ["Nike", ["nike"]],
  ["Adidas", ["adidas"]],
  ["Levi's", ["levi's", "levis", "levi.com"]],
  ["Amazon", ["amazon", "amzn.to"]],
  ["Walmart", ["walmart"]],
  ["Target", ["target.com", "target "]],
  ["Best Buy", ["best buy", "bestbuy"]],
  ["Costco", ["costco"]],
  ["eBay", ["ebay"]],
  ["Macy's", ["macy's", "macys"]],
  ["Nordstrom", ["nordstrom"]],
  ["Steam", ["steampowered", "steam "]],
  ["Woot", ["woot.com", "woot!"]],
];

const PRICE_RE = /\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)/;

/** Keyword-based category for a deal title. */
export function categorize(title) {
  const lower = title.toLowerCase();
  let best = "Other";
  let bestHits = 0;
  for (const [category, words] of Object.entries(KEYWORDS)) {
    const hits = words.reduce((n, w) => n + (lower.includes(w) ? 1 : 0), 0);
    if (hits > bestHits) { best = category; bestHits = hits; }
  }
  return best;
}

/** Pull the sale price out of a title like "Levi's 501 Jeans $39.99 (was $70)".
    The first dollar amount in a deal title is almost always the sale price. */
export function extractPrice(title) {
  const m = PRICE_RE.exec(title);
  return m ? parseFloat(m[1].replace(/,/g, "")) : null;
}

/** Identify the retailer from the deal URL domain (preferred) or title.
    The domain wins: "Levi's jeans at Amazon" linking to amazon.com is an
    Amazon deal, not a Levi's-store deal. */
export function detectStore(title, url = "") {
  let domain = "";
  try { domain = url ? new URL(url).hostname.toLowerCase() : ""; } catch { /* bad url */ }
  if (domain) {
    for (const [store, needles] of STORES) {
      if (needles.some((n) => domain.includes(n))) return store;
    }
  }
  const hay = ` ${title} `.toLowerCase();
  for (const [store, needles] of STORES) {
    if (needles.some((n) => hay.includes(n))) return store;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Optional Claude scoring
// ---------------------------------------------------------------------------

export const AI_MODEL = process.env.DEALRADAR_AI_MODEL || "claude-opus-4-8";

export function aiAvailable() {
  return Boolean(process.env.ANTHROPIC_API_KEY);
}

const SCORE_SCHEMA = {
  type: "object",
  properties: {
    deals: {
      type: "array",
      items: {
        type: "object",
        properties: {
          id: { type: "string" },
          score: { type: "integer", enum: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] },
          take: { type: "string" },
          category: { type: "string", enum: CATEGORIES },
        },
        required: ["id", "score", "take", "category"],
        additionalProperties: false,
      },
    },
  },
  required: ["deals"],
  additionalProperties: false,
};

const PROMPT = `You are the curator for a deals community (like the paid Discord \
deal-alert groups). For each deal below, judge how good it likely is for a \
regular shopper.

Score 1-10 (10 = exceptional all-time-low on something people actually want, \
5 = ordinary sale, 1 = junk or fake discount). Write a one-sentence "take" a \
group admin would post with it — blunt and useful, no hype. Also assign the \
best category.

Deals (JSON):
`;

/** Score a batch of deals with Claude. Each input needs {id, title, source}.
    Returns [{id, score, take, category}]. Throws on API errors — callers
    treat AI scoring as best-effort. */
export async function scoreDealsWithAI(deals) {
  if (!deals.length) return [];
  const { default: Anthropic } = await import("@anthropic-ai/sdk");
  const client = new Anthropic();
  const payload = JSON.stringify(
    deals.map((d) => ({ id: d.id, title: d.title, source: d.source }))
  );
  const response = await client.messages.create({
    model: AI_MODEL,
    max_tokens: 16000,
    output_config: { format: { type: "json_schema", schema: SCORE_SCHEMA } },
    messages: [{ role: "user", content: PROMPT + payload }],
  });
  if (response.stop_reason === "refusal") return [];
  const text = response.content.find((b) => b.type === "text")?.text ?? '{"deals":[]}';
  return JSON.parse(text).deals;
}
