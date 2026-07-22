// Discord webhook poster — pushes top deals to a channel, like the paid groups do.

export function webhookConfigured() {
  return Boolean(process.env.DISCORD_WEBHOOK_URL);
}

/** Post the top deals to the configured Discord webhook. Returns count posted. */
export async function postTopDeals(deals, limit = 5) {
  const url = process.env.DISCORD_WEBHOOK_URL;
  if (!url) throw new Error("DISCORD_WEBHOOK_URL is not set");
  const top = deals.slice(0, limit);
  if (!top.length) return 0;

  const lines = ["**🛰️ DealRadar — top deals right now**", ""];
  for (const d of top) {
    const score = d.ai_score ? ` \`${d.ai_score}/10\`` : "";
    const take = d.ai_take ? `\n> ${d.ai_take}` : "";
    lines.push(`**[${d.category}]${score}** [${d.title}](${d.url})${take}`, "");
  }

  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content: lines.join("\n").slice(0, 2000) }),
  });
  if (!resp.ok) throw new Error(`Discord webhook -> HTTP ${resp.status}`);
  return top.length;
}
