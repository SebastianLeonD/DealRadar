import { timeAgo } from "../api.js";

export default function Banners({ status }) {
  const live = status?.last_refresh_at
    ? `sources checked ${timeAgo(status.last_refresh_at)}`
    : "first check pending";
  const interval = status?.auto_refresh_minutes ?? "–";
  const ai = status?.ai_enabled;
  return (
    <div className="banners">
      <div className="banner blue">
        <b>{status ? `🟢 Live — ${live} · auto-refresh every ${interval} min` : "🟢 Live — connecting…"}</b>
        <span className="sub">sources re-checked automatically · board updates every 60s</span>
      </div>
      <div className="banner green">
        <b>{ai ? "AI deal scoring: ON" : "AI deal scoring: off"}</b>
        <span className="sub">
          {ai
            ? "every new deal rated 1–10 with a one-line verdict"
            : "set ANTHROPIC_API_KEY to rate every deal 1–10"}
        </span>
      </div>
    </div>
  );
}
