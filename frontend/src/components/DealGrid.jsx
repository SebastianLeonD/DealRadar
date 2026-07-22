import DealCard from "./DealCard.jsx";

export default function DealGrid({ deals, loading, onOpen }) {
  if (loading) return <div className="grid"><div className="empty">Loading…</div></div>;
  if (!deals.length) {
    return (
      <div className="grid">
        <div className="empty">Nothing fresh matches — widen the time window or hit ⟳ to refresh.</div>
      </div>
    );
  }
  return (
    <div className="grid">
      {deals.map((d, i) => (
        <DealCard key={d.id} deal={d} onOpen={() => onOpen(i)} />
      ))}
    </div>
  );
}
