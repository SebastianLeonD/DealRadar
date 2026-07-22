"""Discord webhook poster — pushes top deals to a channel, like the paid groups do."""

import os

import httpx


def webhook_configured() -> bool:
    return bool(os.environ.get("DISCORD_WEBHOOK_URL"))


def post_top_deals(deals: list[dict], limit: int = 5) -> int:
    """Post the top deals to the configured Discord webhook. Returns count posted."""
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        raise RuntimeError("DISCORD_WEBHOOK_URL is not set")

    top = deals[:limit]
    if not top:
        return 0

    lines = ["**🛰️ DealRadar — top deals right now**", ""]
    for d in top:
        score = f" `{d['ai_score']}/10`" if d.get("ai_score") else ""
        take = f"\n> {d['ai_take']}" if d.get("ai_take") else ""
        lines.append(f"**[{d['category']}]{score}** [{d['title']}]({d['url']}){take}")
        lines.append("")

    resp = httpx.post(url, json={"content": "\n".join(lines)[:2000]}, timeout=15.0)
    resp.raise_for_status()
    return len(top)
