export default function SubNav({ categories, activeCategory, saleMode, onCategory, onToggleSale }) {
  return (
    <nav className="sections">
      <button
        className={`section ${!saleMode && activeCategory === "All" ? "active" : ""}`}
        onClick={() => onCategory("All")}
      >
        All
      </button>
      {categories.map((c) => (
        <button
          key={c.category}
          className={`section ${!saleMode && c.category === activeCategory ? "active" : ""}`}
          onClick={() => onCategory(c.category)}
        >
          {c.category}
          <sup>{c.n}</sup>
        </button>
      ))}
      <button className={`section hot ${saleMode ? "active" : ""}`} onClick={onToggleSale}>
        Hot&nbsp;List
      </button>
    </nav>
  );
}
