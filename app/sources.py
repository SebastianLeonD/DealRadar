"""Deal feed fetchers. All sources are free public RSS/Atom feeds — no API keys."""

import re
import time
from html import unescape

import feedparser
import httpx

FEEDS = [
    {
        "name": "slickdeals",
        "url": "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1",
    },
    {"name": "r/deals", "url": "https://www.reddit.com/r/deals/.rss"},
    {"name": "r/buildapcsales", "url": "https://www.reddit.com/r/buildapcsales/.rss"},
    {"name": "r/frugalmalefashion", "url": "https://www.reddit.com/r/frugalmalefashion/.rss"},
    {"name": "r/FrugalFemaleFashion", "url": "https://www.reddit.com/r/FrugalFemaleFashion/.rss"},
    {"name": "r/GameDeals", "url": "https://www.reddit.com/r/GameDeals/.rss"},
]

HEADERS = {"User-Agent": "DealRadar/0.1 (personal deal aggregator)"}


_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)


def _entry_image(entry) -> str | None:
    """Best product image for a feed entry.

    Reddit Atom feeds expose media:thumbnail / media:content; Slickdeals (and
    Reddit link posts) embed an <img> inside the entry's HTML body.
    """
    for key in ("media_thumbnail", "media_content"):
        for item in getattr(entry, key, None) or []:
            url = item.get("url")
            if url and url.startswith("http"):
                return unescape(url)

    html_parts = [getattr(entry, "summary", "") or ""]
    for content in getattr(entry, "content", None) or []:
        html_parts.append(content.get("value", "") if isinstance(content, dict)
                          else getattr(content, "value", ""))
    for html in html_parts:
        match = _IMG_RE.search(html)
        if match:
            url = unescape(match.group(1))
            if url.startswith("http"):
                return url
    return None


def _entry_posted_at(entry) -> str | None:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", parsed)
    return None


def fetch_feed(name: str, url: str, timeout: float = 15.0) -> list[dict]:
    resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.content)
    deals = []
    for entry in parsed.entries:
        title = (getattr(entry, "title", "") or "").strip()
        link = (getattr(entry, "link", "") or "").strip()
        if not title or not link:
            continue
        deals.append({
            "title": title,
            "url": link,
            "source": name,
            "image_url": _entry_image(entry),
            "posted_at": _entry_posted_at(entry),
        })
    return deals


def fetch_all() -> tuple[list[dict], list[str]]:
    """Fetch every configured feed. Returns (deals, errors) — one source failing
    never blocks the rest."""
    all_deals: list[dict] = []
    errors: list[str] = []
    for feed in FEEDS:
        try:
            all_deals.extend(fetch_feed(feed["name"], feed["url"]))
        except Exception as exc:  # noqa: BLE001 — surface per-source failures to the caller
            errors.append(f"{feed['name']}: {exc}")
    return all_deals, errors
