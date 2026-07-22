export default function SubNav({ categories, activeCategory, saleMode, onCategory, onToggleSale }) {
  return (
    <nav className="subnav">
      <div className="navrail">
        <button
          className={`navpill ${!saleMode && activeCategory === "All" ? "active" : ""}`}
          onClick={() => onCategory("All")}
        >
          All deals
        </button>
        {categories.map((c) => (
          <button
            key={c.category}
            className={`navpill ${!saleMode && c.category === activeCategory ? "active" : ""}`}
            onClick={() => onCategory(c.category)}
          >
            {c.category}
            <span className="navcount">{c.n}</span>
          </button>
        ))}
        <span className="navdivider" aria-hidden="true" />
        <button className={`navpill hot ${saleMode ? "active" : ""}`} onClick={onToggleSale}>
          🔥 Hot right now
        </button>
      </div>
    </nav>
  );
}
