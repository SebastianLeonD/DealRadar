export default function TopBar({ query, onQuery, onRefresh, onNotify, refreshing }) {
  return (
    <div className="topbar">
      <div className="logo">dealradar</div>
      <div className="tab">DEALS</div>
      <div className="searchwrap">
        <div className="searchbox">
          <input
            type="search"
            placeholder="Search for deals, items and brands"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
          />
          <span className="mag">⌕</span>
        </div>
      </div>
      <button className="iconbtn" title="Refresh deals now" onClick={onRefresh} disabled={refreshing}>
        ⟳
      </button>
      <button className="iconbtn" title="Post top 5 deals to Discord" onClick={onNotify}>
        🖈
      </button>
    </div>
  );
}
