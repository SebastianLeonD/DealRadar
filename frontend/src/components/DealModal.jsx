import { useEffect } from "react";
import { scoreClass, timeAgo } from "../api.js";
import { Thumb } from "./DealCard.jsx";

export default function DealModal({ deal, onClose, isSaved, onToggleSave, stale }) {
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
          {deal.ai_score ? (
            <div className={`stamp ${scoreClass(deal.ai_score)}`}>
              <span>RATED</span>
              <b>{deal.ai_score}/10</b>
            </div>
          ) : null}
        </div>
        <div className="modalbody">
          <button className="close" onClick={onClose} title="Close">✕</button>
          <div className="modalkicker">
            {deal.store ? `[${deal.store.toUpperCase()}]` : "[UNLISTED]"} · {deal.category.toUpperCase()} · VIA{" "}
            {deal.source.toUpperCase()} · {timeAgo(deal.posted_at || deal.fetched_at).toUpperCase()}
          </div>
          <h2>{deal.title}</h2>
          {stale ? <div className="stalenote">⚠ NO LONGER ON SALE — LINK STILL WORKS</div> : null}
          {deal.price != null ? <div className="bigprice">${deal.price}</div> : null}
          {deal.ai_take ? <div className="take">“{deal.ai_take}”</div> : null}
          <div className="modalactions">
            <a className="gobtn" href={deal.url} target="_blank" rel="noopener noreferrer">
              OPEN DEAL ↗
            </a>
            {onToggleSave ? (
              <button className={`savebtn wide ${isSaved ? "on" : ""}`} onClick={() => onToggleSave(deal)}>
                {isSaved ? "★ SAVED" : "☆ SAVE"}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
