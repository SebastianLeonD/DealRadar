"""Deal categorization.

Two layers:
1. Keyword categorizer — instant, free, always on.
2. Claude scoring (optional) — if ANTHROPIC_API_KEY is set, batches of deals get
   a 1-10 quality score and a one-line verdict via structured outputs.
"""

import json
import os
import re
from urllib.parse import urlparse

CATEGORIES = [
    "Tech", "Clothing", "Gaming", "Home", "Beauty", "Food", "Sports", "Other",
]

_KEYWORDS = {
    "Tech": [
        "laptop", "monitor", "ssd", "gpu", "cpu", "ryzen", "intel", "nvidia",
        "rtx", "radeon", "tv", "oled", "headphone", "earbud", "airpods",
        "iphone", "ipad", "samsung", "pixel", "tablet", "router", "keyboard",
        "mouse", "webcam", "charger", "usb", "hdmi", "camera", "drone",
        "smartwatch", "kindle", "echo", "alexa", "speaker", "soundbar", "ram",
        "motherboard", "nas", "hard drive", "microsd", "power bank", "macbook",
    ],
    "Clothing": [
        "shirt", "tee", "hoodie", "jacket", "jeans", "pants", "chinos",
        "sneaker", "shoe", "boot", "sock", "underwear", "coat", "sweater",
        "levi", "nike", "adidas", "uniqlo", "polo", "dress", "shorts", "hat",
        "beanie", "flannel", "denim", "loafers", "apparel",
    ],
    "Gaming": [
        "game", "steam", "playstation", "ps5", "xbox", "nintendo", "switch",
        "controller", "dlc", "gog", "epic games", "console", "joy-con",
        "gamepass", "game pass", "psn",
    ],
    "Home": [
        "vacuum", "roomba", "air fryer", "instant pot", "mattress", "pillow",
        "blender", "coffee", "espresso", "cookware", "knife", "furniture",
        "desk", "chair", "lamp", "thermostat", "tool", "drill", "dewalt",
        "milwaukee", "ryobi", "storage", "sheets", "towel", "humidifier",
        "purifier", "grill", "mower",
    ],
    "Beauty": [
        "skincare", "moisturizer", "sunscreen", "shampoo", "razor", "trimmer",
        "electric toothbrush", "cologne", "perfume", "makeup", "serum",
    ],
    "Food": [
        "snack", "coffee beans", "protein", "cereal", "chocolate", "grocery",
        "pizza", "burger", "meal kit", "gift card",
    ],
    "Sports": [
        "bike", "bicycle", "dumbbell", "treadmill", "kayak", "tent", "camping",
        "hiking", "golf", "fitness", "yoga", "backpack", "cooler",
    ],
}


# Retailer detection — matched against title + URL, first hit wins.
# Longer/more specific names come before substrings that could collide.
STORES = [
    ("Abercrombie", ["abercrombie"]),
    ("Hollister", ["hollister"]),
    ("PacSun", ["pacsun"]),
    ("Ralph Lauren", ["ralph lauren", "ralphlauren", "polo rl"]),
    ("American Eagle", ["american eagle", "ae.com", "aerie"]),
    ("Urban Outfitters", ["urban outfitters", "urbanoutfitters"]),
    ("J.Crew", ["j.crew", "jcrew", "j crew"]),
    ("Banana Republic", ["banana republic", "bananarepublic"]),
    ("Vans", ["vans.com", " vans "]),
    ("Converse", ["converse"]),
    ("New Balance", ["new balance", "newbalance"]),
    ("Foot Locker", ["foot locker", "footlocker"]),
    ("ASOS", ["asos"]),
    ("Zara", ["zara"]),
    ("H&M", ["h&m", "hm.com"]),
    ("Uniqlo", ["uniqlo"]),
    ("Old Navy", ["old navy", "oldnavy"]),
    ("Gap", ["gap.com", " gap "]),
    ("Nike", ["nike"]),
    ("Adidas", ["adidas"]),
    ("Levi's", ["levi's", "levis", "levi.com"]),
    ("Amazon", ["amazon", "amzn.to"]),
    ("Walmart", ["walmart"]),
    ("Target", ["target.com", "target "]),
    ("Best Buy", ["best buy", "bestbuy"]),
    ("Costco", ["costco"]),
    ("eBay", ["ebay"]),
    ("Macy's", ["macy's", "macys"]),
    ("Nordstrom", ["nordstrom"]),
    ("Steam", ["steampowered", "steam "]),
    ("Woot", ["woot.com", "woot!"]),
]

_PRICE_RE = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)")


def extract_price(title: str) -> float | None:
    """Pull the deal price out of a title like 'Levi's 501 Jeans $39.99 (was $70)'.

    Uses the first dollar amount, which in deal titles is almost always the
    sale price (the original price comes after, e.g. 'was $70', 'reg. $100').
    """
    match = _PRICE_RE.search(title)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def detect_store(title: str, url: str = "") -> str | None:
    """Identify the retailer from the deal URL (preferred) or title.

    The URL wins because it names where you actually buy: "Levi's jeans at
    Amazon" linking to amazon.com is an Amazon deal, not a Levi's-store deal.
    """
    domain = urlparse(url).netloc.lower() if url else ""
    if domain:
        for store, needles in STORES:
            if any(n in domain for n in needles):
                return store
    title_hay = f" {title} ".lower()
    for store, needles in STORES:
        if any(n in title_hay for n in needles):
            return store
    return None


def categorize(title: str) -> str:
    """Keyword-based category for a deal title."""
    lower = title.lower()
    best, best_hits = "Other", 0
    for category, words in _KEYWORDS.items():
        hits = sum(1 for w in words if w in lower)
        if hits > best_hits:
            best, best_hits = category, hits
    return best


# ---------------------------------------------------------------------------
# Optional Claude scoring
# ---------------------------------------------------------------------------

AI_MODEL = os.environ.get("DEALRADAR_AI_MODEL", "claude-opus-4-8")

_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "deals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "score": {"type": "integer", "enum": list(range(1, 11))},
                    "take": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                },
                "required": ["id", "score", "take", "category"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["deals"],
    "additionalProperties": False,
}

_PROMPT = """You are the curator for a deals community (like the paid Discord \
deal-alert groups). For each deal below, judge how good it likely is for a \
regular shopper.

Score 1-10 (10 = exceptional all-time-low on something people actually want, \
5 = ordinary sale, 1 = junk or fake discount). Write a one-sentence "take" a \
group admin would post with it — blunt and useful, no hype. Also assign the \
best category.

Deals (JSON):
{deals_json}
"""


def ai_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def score_deals_with_ai(deals: list[dict]) -> list[dict]:
    """Score a batch of deals with Claude. Each input dict needs 'id' and 'title'.

    Returns a list of {id, score, take, category}. Raises on API errors —
    callers treat AI scoring as best-effort.
    """
    if not deals:
        return []

    import anthropic  # imported lazily so the app runs without the SDK key set

    client = anthropic.Anthropic()
    payload = json.dumps(
        [{"id": d["id"], "title": d["title"], "source": d["source"]} for d in deals],
        ensure_ascii=False,
    )
    response = client.messages.create(
        model=AI_MODEL,
        max_tokens=16000,
        output_config={"format": {"type": "json_schema", "schema": _SCORE_SCHEMA}},
        messages=[{"role": "user", "content": _PROMPT.format(deals_json=payload)}],
    )
    if response.stop_reason == "refusal":
        return []
    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)["deals"]
