import DealCard from "./DealCard.jsx";

export default function DealGrid({ deals, loading, onOpen }) {
  if (loading) return <div className="grid"><div className="empty">SETTING THE PRESS…</div></div>;
  if (!deals.length) {
    return (
      <div className="grid">
        <div className="empty">NOTHING FRESH ON THE WIRE — WIDEN THE TIME WINDOW OR REFRESH.</div>
      </div>
    );
  }
  return (
    <div className="grid">
      {deals.map((d, i) => (
        <DealCard key={d.id} deal={d} index={i} onOpen={() => onOpen(i)} />
      ))}
    </div>
  );
}
