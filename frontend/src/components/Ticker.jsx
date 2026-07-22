// Stock-ticker strip of the highest-scored deals — pure CSS marquee.
export default function Ticker({ deals }) {
  const top = [...deals]
    .filter((d) => d.ai_score)
    .sort((a, b) => b.ai_score - a.ai_score)
    .slice(0, 8);
  const items = top.length
    ? top
    : deals.slice(0, 8);
  if (!items.length) return null;

  const cell = (d, i) => (
    <span className="tickeritem" key={i}>
      {d.ai_score ? <b className="tickscore">★{d.ai_score}</b> : null}
      <span className="ticktitle">{d.title}</span>
      {d.store ? <span className="tickstore">[{d.store.toUpperCase()}]</span> : null}
      <span className="tickersep" aria-hidden="true">◆</span>
    </span>
  );

  return (
    <div className="ticker" aria-hidden="true">
      <div className="tickertrack">
        {items.map(cell)}
        {items.map((d, i) => cell(d, i + 100))}
      </div>
    </div>
  );
}
