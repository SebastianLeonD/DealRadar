export const ITEM_TYPES = ["All", "Jeans", "Shorts", "Tee", "Hoodie", "Jacket", "Sneaker", "Shoe", "Sweater", "Pants"];
const DISCOUNTS = [
  { value: "", label: "Any" },
  { value: "25", label: "25%+" },
  { value: "50", label: "50%+" },
  { value: "70", label: "70%+" },
];

function Chips({ options, active, onPick, format = (v) => v }) {
  return (
    <div className="chips">
      {options.map((o) => (
        <span key={o} className={`chip ${o === active ? "active" : ""}`}
          onClick={() => onPick(o === active ? "All" : o)}>
          {format(o)}
        </span>
      ))}
    </div>
  );
}

/** Left filter rail, personalized per section: clothing gets item/size/color,
    other sections just store/discount/price/freshness. Size/color options come
    from /api/filters (only clothing sources carry them). */
export default function Sidebar({ filters, category = "All", stores, facets, saleMode, onChange }) {
  const set = (patch) => onChange(patch);
  const clothing = category === "Clothing" || category === "All";
  const colors = clothing ? facets?.colors ?? [] : [];
  const sizes = clothing ? facets?.sizes ?? [] : [];

  return (
    <aside className="sidebar">
      <div className="sideblock">
        <div className="sidehead">SORT</div>
        <select
          value={saleMode ? "best" : filters.order}
          onChange={(e) => set({ order: e.target.value, saleMode: false })}
        >
          <option value="new">Newest</option>
          <option value="best">Best score</option>
        </select>
      </div>

      {clothing && (
        <div className="sideblock">
          <div className="sidehead">ITEM</div>
          <Chips options={ITEM_TYPES.filter((t) => t !== "All")} active={filters.item}
            onPick={(item) => set({ item })} />
        </div>
      )}

      <div className="sideblock">
        <div className="sidehead">STORE</div>
        <select value={filters.store} onChange={(e) => set({ store: e.target.value })}>
          <option value="All">All stores</option>
          {stores.map((s) => (
            <option key={s.store} value={s.store}>{s.store} ({s.n})</option>
          ))}
        </select>
      </div>

      <div className="sideblock">
        <div className="sidehead">DISCOUNT</div>
        <div className="chips">
          {DISCOUNTS.map((d) => (
            <span key={d.value} className={`chip ${filters.minDiscount === d.value ? "active" : ""}`}
              onClick={() => set({ minDiscount: d.value })}>
              {d.label}
            </span>
          ))}
        </div>
      </div>

      <div className="sideblock">
        <div className="sidehead">PRICE</div>
        <div className="pricerow">
          <input type="number" min="0" placeholder="min" value={filters.minPrice}
            onChange={(e) => set({ minPrice: e.target.value })} />
          <span>—</span>
          <input type="number" min="0" placeholder="max" value={filters.maxPrice}
            onChange={(e) => set({ maxPrice: e.target.value })} />
        </div>
      </div>

      {sizes.length > 0 && (
        <div className="sideblock">
          <div className="sidehead">SIZE <span className="sidenote">(ZARA/H&M ITEMS)</span></div>
          <Chips options={sizes.map((s) => s.name)} active={filters.size}
            onPick={(size) => set({ size })} />
        </div>
      )}

      {colors.length > 0 && (
        <div className="sideblock">
          <div className="sidehead">COLOR</div>
          <Chips options={colors.map((c) => c.name)} active={filters.color}
            onPick={(color) => set({ color })}
            format={(c) => c.charAt(0).toUpperCase() + c.slice(1)} />
        </div>
      )}

      <div className="sideblock">
        <div className="sidehead">FRESH</div>
        <select value={filters.age} onChange={(e) => set({ age: e.target.value })}>
          <option value="24">Last 24h</option>
          <option value="48">Last 48h</option>
          <option value="168">Last 7d</option>
          <option value="">All time</option>
        </select>
      </div>

      <button className="clearbtn" onClick={() => set({
        item: "All", store: "All", color: "All", size: "All",
        minDiscount: "", minPrice: "", maxPrice: "", age: "48",
      })}>
        CLEAR FILTERS
      </button>
    </aside>
  );
}
