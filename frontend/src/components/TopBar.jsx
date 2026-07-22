export default function TopBar({ query, onQuery, onRefresh, onNotify, refreshing }) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="logo">
          deal<span>radar</span><i className="ping" aria-hidden="true" />
        </div>
        <div className="tagline">live deals, curated by AI</div>
      </div>
      <div className="searchwrap">
        <div className="searchbox">
          <span className="mag">⌕</span>
          <input
            type="search"
            placeholder="Search deals, items and brands"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
          />
        </div>
      </div>
      <button className="actionbtn" onClick={onRefresh} disabled={refreshing} title="Refresh deals now">
        ⟳ {refreshing ? "Refreshing…" : "Refresh"}
      </button>
      <button className="actionbtn ghost" onClick={onNotify} title="Post top 5 deals to Discord">
        Post to Discord
      </button>
    </header>
  );
}
