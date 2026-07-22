import { useEffect } from "react";
import { scoreClass, timeAgo } from "../api.js";
import { Thumb } from "./DealCard.jsx";

export default function DealModal({ deal, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!deal) return null;
  return (
    <div className="overlay open" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <div className="modalimg">
          <Thumb deal={deal} big />
        </div>
        <div className="modalbody">
          <button className="close" onClick={onClose} title="Close">✕</button>
          <h2>{deal.title}</h2>
          {deal.price != null ? <div className="bigprice">${deal.price}</div> : null}
          <div className="modalmeta">
            {deal.store ? <span><b>{deal.store}</b> ·</span> : null}
            <span>{deal.category}</span> ·
            <span>via {deal.source}</span> ·
            <span>{timeAgo(deal.posted_at || deal.fetched_at)}</span>
          </div>
          {deal.ai_score ? (
            <div className="scoreline">
              AI deal score: <b className={scoreClass(deal.ai_score)}>{deal.ai_score}/10</b>
            </div>
          ) : null}
          {deal.ai_take ? <div className="take">“{deal.ai_take}”</div> : null}
          <a className="gobtn" href={deal.url} target="_blank" rel="noopener noreferrer">
            Open deal ↗
          </a>
        </div>
      </div>
    </div>
  );
}
