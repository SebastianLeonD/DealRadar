import DealCard from "./DealCard.jsx";

export default function DealGrid({ deals, loading, onOpen, savedSet, staleSet, onToggleSave, emptyMsg }) {
  if (loading) return <div className="grid"><div className="empty">SETTING THE PRESS…</div></div>;
  if (!deals.length) {
    return (
      <div className="grid">
        <div className="empty">{emptyMsg || "NOTHING FRESH ON THE WIRE — WIDEN THE TIME WINDOW OR REFRESH."}</div>
      </div>
    );
  }
  return (
    <div className="grid">
      {deals.map((d, i) => (
        <DealCard
          key={d.url}
          deal={d}
          index={i}
          onOpen={() => onOpen(i)}
          isSaved={savedSet?.has(d.url)}
          onToggleSave={onToggleSave}
          stale={staleSet?.has(d.url)}
        />
      ))}
    </div>
  );
}
