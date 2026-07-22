import { useState } from "react";

export const ITEM_TYPES = ["All", "Jeans", "Shorts", "Tee", "Hoodie", "Jacket", "Sneaker", "Shoe", "Dress", "Sweater"];

export default function FilterBar({ filters, stores, saleMode, onChange }) {
  const [open, setOpen] = useState(false);
  const set = (patch) => onChange(patch);

  return (
    <div className="controls">
      <div className="pill" title="Sort order">
        <span className="icon">⇅</span>
        <select
          value={saleMode ? "best" : filters.order}
          onChange={(e) => set({ order: e.target.value, saleMode: false })}
        >
          <option value="new">Sort: Newest</option>
          <option value="best">Sort: Best score</option>
        </select>
      </div>
      <button className="pill" onClick={() => setOpen(!open)}>
        <span className="icon">⚟</span> Filter
      </button>
      <div className={`filterpanel ${open ? "open" : ""}`}>
        <label>Item</label>
        <span>
          {ITEM_TYPES.map((t) => (
            <span
              key={t}
              className={`chip ${t === filters.item ? "active" : ""}`}
              onClick={() => set({ item: t })}
            >
              {t}
            </span>
          ))}
        </span>
        <label>Store</label>
        <select value={filters.store} onChange={(e) => set({ store: e.target.value })}>
          <option value="All">All stores</option>
          {stores.map((s) => (
            <option key={s.store} value={s.store}>
              {s.store} ({s.n})
            </option>
          ))}
        </select>
        <label>Max $</label>
        <input
          type="number"
          min="0"
          step="1"
          placeholder="any"
          value={filters.maxPrice}
          onChange={(e) => set({ maxPrice: e.target.value })}
        />
        <label>Fresh</label>
        <select value={filters.age} onChange={(e) => set({ age: e.target.value })}>
          <option value="24">Last 24h</option>
          <option value="48">Last 48h</option>
          <option value="168">Last 7d</option>
          <option value="">All time</option>
        </select>
      </div>
    </div>
  );
}
