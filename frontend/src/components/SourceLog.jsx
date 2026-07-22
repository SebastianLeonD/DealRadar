import { useState } from "react";
import { timeAgo } from "../api.js";

/** Per-source health strip: one chip per source from the latest refresh,
    expandable into a log of recent refreshes with error details. */
export default function SourceLog({ status }) {
  const [open, setOpen] = useState(false);
  const log = status?.refresh_log ?? [];
  const latest = log[0];
  if (!latest?.sources?.length) return null;

  const failing = latest.sources.filter((s) => !s.ok);
  return (
    <div className="sourcelog">
      <button className="sourcelog-head" onClick={() => setOpen((o) => !o)}>
        <span>
          SOURCE WIRE — {latest.sources.length - failing.length}/{latest.sources.length} OK
          {failing.length ? ` · FAILING: ${failing.map((s) => s.source).join(", ")}` : ""}
        </span>
        <span>{open ? "▴ HIDE LOG" : "▾ VIEW LOG"}</span>
      </button>
      {open && (
        <div className="sourcelog-body">
          {log.map((r) => (
            <div className="sourcelog-refresh" key={r.at}>
              <div className="sourcelog-when">
                {timeAgo(r.at).toUpperCase()} — {r.fetched} FETCHED, {r.new} NEW
              </div>
              {r.sources.map((s) => (
                <div className={`sourcelog-row ${s.ok ? "ok" : s.skipped ? "skip" : "fail"}`} key={s.source}>
                  <span className="dotmark">{s.ok ? "●" : s.skipped ? "○" : "✕"}</span>
                  <span className="srcname">{s.source}</span>
                  <span className="srcinfo">
                    {s.ok ? `${s.count} items` : s.error} · {s.ms}ms
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
