export default function SubNav({ categories, activeCategory, saleMode, onCategory, onToggleSale }) {
  return (
    <div className="subnav">
      <div
        className={`navitem trend ${!saleMode && activeCategory === "All" ? "active" : ""}`}
        onClick={() => onCategory("All")}
      >
        Trending
      </div>
      {categories.map((c) => (
        <div
          key={c.category}
          className={`navitem ${!saleMode && c.category === activeCategory ? "active" : ""}`}
          onClick={() => onCategory(c.category)}
        >
          {c.category}
        </div>
      ))}
      <div className={`navitem sale ${saleMode ? "active" : ""}`} onClick={onToggleSale}>
        Hot 🔥
      </div>
    </div>
  );
}
