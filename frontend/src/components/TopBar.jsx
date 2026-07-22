import { timeAgo } from "../api.js";

export default function TopBar({ query, onQuery, onRefresh, onNotify, refreshing, status }) {
  const live = status?.last_refresh_at
    ? `SOURCES CHECKED ${timeAgo(status.last_refresh_at).toUpperCase()}`
    : "FIRST CHECK PENDING";
  return (
    <header className="masthead">
      <div className="wire">
        <span className="wireitem">
          <i className="ping" aria-hidden="true" /> LIVE FEED — {live}
        </span>
        <span className="wireitem right">
          AI SCORING: {status?.ai_enabled ? "ON" : "OFF"} · AUTO-REFRESH {status?.auto_refresh_minutes ?? "—"} MIN
        </span>
      </div>
      <div className="mastrow">
        <h1 className="wordmark">
          DealRadar<span className="dot">.</span>
        </h1>
        <div className="searchbox">
          <span className="mag">⌕</span>
          <input
            type="search"
            placeholder="SEARCH THE BULLETIN…"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
          />
        </div>
        <button className="actionbtn" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? "REFRESHING…" : "⟳ REFRESH"}
        </button>
        <button className="actionbtn ghost" onClick={onNotify}>
          → DISCORD
        </button>
      </div>
      <div className="rule double" />
    </header>
  );
}
