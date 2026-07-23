import { useState } from "react";
import { scoreClass, timeAgo } from "../api.js";

export function Thumb({ deal, big = false, eager = false }) {
  const [broken, setBroken] = useState(false);
  if (!deal.image_url || broken) return <div className="noimg">◻</div>;
  return (
    <img
      src={deal.image_url}
      alt=""
      loading={big || eager ? undefined : "lazy"}
      onError={() => setBroken(true)}
    />
  );
}

export default function DealCard({ deal, index, onOpen, isSaved, onToggleSave, stale }) {
  return (
    <article
      className={`card ${stale ? "stale" : ""}`}
      onClick={onOpen}
      style={{ animationDelay: `${Math.min(index * 45, 500)}ms` }}
    >
      <div className="imgbox">
        <Thumb deal={deal} eager={index < 10} />
        {deal.ai_score ? (
          <div className={`scorebadge ${scoreClass(deal.ai_score)}`}>★ {deal.ai_score}</div>
        ) : null}
        {deal.ai_score >= 9 ? <div className="hotbadge">HOT</div> : null}
        {onToggleSave ? (
          <button
            className={`savebtn ${isSaved ? "on" : ""}`}
            title={isSaved ? "Remove from saved" : "Save"}
            onClick={(e) => { e.stopPropagation(); onToggleSave(deal); }}
          >
            {isSaved ? "★" : "☆"}
          </button>
        ) : null}
        {stale ? <div className="stalebanner">NO LONGER ON SALE</div> : null}
      </div>
      <div className="cardinfo">
        <div className="cardtitle">{deal.title}</div>
        <div className="cardfoot">
          {deal.price != null ? <span className="cardprice">${deal.price}</span> : <span className="cardprice dim">—</span>}
          <span className="cardmeta">
            {deal.store ? `[${deal.store.toUpperCase()}] ` : ""}
            {timeAgo(deal.posted_at || deal.fetched_at).toUpperCase()}
          </span>
        </div>
      </div>
    </article>
  );
}
