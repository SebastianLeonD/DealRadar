export default function SubNav({
  categories, activeCategory, saleMode, savedView, savedCount, onCategory, onToggleSale, onSaved,
}) {
  return (
    <nav className="sections">
      <button
        className={`section ${!saleMode && !savedView && activeCategory === "All" ? "active" : ""}`}
        onClick={() => onCategory("All")}
      >
        All
      </button>
      {categories.map((c) => (
        <button
          key={c.category}
          className={`section ${!saleMode && !savedView && c.category === activeCategory ? "active" : ""}`}
          onClick={() => onCategory(c.category)}
        >
          {c.category}
          <sup>{c.n}</sup>
        </button>
      ))}
      <button className={`section hot ${saleMode ? "active" : ""}`} onClick={onToggleSale}>
        Hot&nbsp;List
      </button>
      <button className={`section saved ${savedView ? "active" : ""}`} onClick={onSaved}>
        ★&nbsp;Saved{savedCount ? <sup>{savedCount}</sup> : null}
      </button>
    </nav>
  );
}
