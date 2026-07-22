import { useState } from "react";
import { scoreClass, timeAgo } from "../api.js";

export function Thumb({ deal, big = false }) {
  const [broken, setBroken] = useState(false);
  if (!deal.image_url || broken) return <div className="noimg">🛍️</div>;
  return <img src={deal.image_url} alt="" loading={big ? undefined : "lazy"} onError={() => setBroken(true)} />;
}

export default function DealCard({ deal, onOpen }) {
  return (
    <div className="card" onClick={onOpen}>
      <div className="imgbox">
        <Thumb deal={deal} />
        {deal.ai_score ? <div className={`scorebadge ${scoreClass(deal.ai_score)}`}>★ {deal.ai_score}</div> : null}
        {deal.ai_score >= 9 ? <div className="hotbadge">HOT</div> : null}
      </div>
      <div className="cardinfo">
        <div className="cardtitle">{deal.title}</div>
        {deal.price != null ? <div className="cardprice">${deal.price}</div> : null}
        <div className="cardmeta">
          {deal.store ? <b>{deal.store} · </b> : null}
          {deal.category} · {timeAgo(deal.posted_at || deal.fetched_at)}
        </div>
      </div>
    </div>
  );
}
