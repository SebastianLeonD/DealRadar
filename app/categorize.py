"""Deal categorization.

Two layers:
1. Keyword categorizer — instant, free, always on.
2. Claude scoring (optional) — if ANTHROPIC_API_KEY is set, batches of deals get
   a 1-10 quality score and a one-line verdict via structured outputs.
"""

import json
import os

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
