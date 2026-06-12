import { AlertTriangle, Download, Filter } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type Edge, type EdgesResponse, type RecordSummary } from "../lib/api";
import { Badge, EmptyState, formatTime, MetricCard, PageHeader } from "../components/ui";

function verdictVariant(verdict: Edge["verdict"]): "over" | "orange" | "under" | "neutral" {
  if (verdict === "YES") return "over";
  if (verdict === "LEAN") return "orange";
  if (verdict === "NO") return "under";
  return "neutral";
}

function resultVariant(result: Edge["result"]): "over" | "under" | "neutral" {
  if (result === "WIN") return "over";
  if (result === "LOSS") return "under";
  return "neutral";
}

function rowBorderClass(verdict: Edge["verdict"]): string {
  if (verdict === "YES")
    return "border-emerald-500/30 shadow-[inset_0_0_0_1px_rgba(52,211,153,0.06),0_0_20px_rgba(52,211,153,0.04)]";
  if (verdict === "LEAN")
    return "border-amber-500/30 shadow-[inset_0_0_0_1px_rgba(251,191,36,0.06),0_0_20px_rgba(251,191,36,0.04)]";
  return "border-border";
}

const GRID =
  "grid-cols-[1.3fr_0.6fr_0.55fr_0.5fr_0.5fr_0.7fr_0.9fr_0.6fr_0.7fr]";

function EdgeRow({ edge }: { edge: Edge }) {
  return (
    <div
      className={`grid ${GRID} items-center gap-3 rounded-xl border bg-surface-card px-4 py-3.5 ${rowBorderClass(edge.verdict)}`}
    >
      <div className="flex items-center gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-text">{edge.player}</p>
          <p className="truncate text-xs text-text-dim">{edge.team}</p>
        </div>
        {edge.flags && (
          <span title={edge.flags}>
            <AlertTriangle size={14} className="shrink-0 text-amber-400" />
          </span>
        )}
      </div>
      <div>
        <Badge variant={verdictVariant(edge.verdict)}>{edge.verdict ?? "—"}</Badge>
      </div>
      <div>
        <Badge variant={edge.play === "OVER" ? "over" : "under"}>{edge.play}</Badge>
      </div>
      <div>
        <Badge variant="orange">{edge.pp_line}</Badge>
      </div>
      <div>
        <Badge variant="cyan">{edge.dk_line}</Badge>
      </div>
      <div>
        {edge.win_prob != null ? (
          <>
            <p className="text-sm font-semibold text-text">
              {(edge.win_prob * 100).toFixed(1)}%
            </p>
            <p className="text-xs text-text-dim">
              {edge.ev_percent != null && edge.ev_percent >= 0 ? "+" : ""}
              {edge.ev_percent?.toFixed(1)}% EV
              {edge.book_count ? ` · ${edge.book_count} bk` : ""}
            </p>
          </>
        ) : (
          <p className="text-xs text-text-dim">—</p>
        )}
      </div>
      <div>
        <Badge variant={edge.edge_type === "Line Discrepancy" ? "cyan" : "purple"}>
          {edge.edge_type}
        </Badge>
      </div>
      <div>
        {edge.result ? (
          <Badge variant={resultVariant(edge.result)}>
            {edge.result}
            {edge.actual_value != null ? ` ${edge.actual_value}` : ""}
          </Badge>
        ) : (
          <span className="text-xs text-text-dim">open</span>
        )}
      </div>
      <p className="text-xs text-text-dim">{formatTime(edge.flagged_at)}</p>
    </div>
  );
}

export function OpportunitiesPage() {
  const [stat, setStat] = useState("All");
  const [edgeType, setEdgeType] = useState("All");
  const [data, setData] = useState<EdgesResponse | null>(null);
  const [record, setRecord] = useState<RecordSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.getEdges(stat, edgeType));
    } catch {
      setData({
        edges: [],
        summary: { unique: 0, line_discrepancy: 0, ev_juice: 0, yes_count: 0, stats: [] },
      });
    } finally {
      setLoading(false);
    }
  }, [stat, edgeType]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.getRecord().then(setRecord).catch(() => {});
  }, []);

  const recordLabel = record?.settled
    ? `${record.wins}W - ${record.losses}L${record.pushes ? ` - ${record.pushes}P` : ""}`
    : "—";

  return (
    <div>
      <PageHeader
        title="Active Opportunities"
        subtitle="Every play priced against sharp consensus. YES = bet it, LEAN = your call, flag = trap risk."
        action={
          <a
            href={api.exportEdgesUrl(stat, edgeType)}
            download="edges.csv"
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface-card px-4 py-2 text-sm font-medium text-text hover:bg-surface-hover"
          >
            <Download size={16} />
            Download CSV
          </a>
        }
      />

      {data && !loading && (
        <div className="mb-6 grid grid-cols-4 gap-3">
          <MetricCard label="YES Plays" value={data.summary.yes_count} />
          <MetricCard label="Unique Signals" value={data.summary.unique} />
          <MetricCard label="Settled Record" value={recordLabel} />
          <MetricCard
            label="Hit Rate"
            value={record?.hit_rate != null ? `${record.hit_rate}%` : "—"}
          />
        </div>
      )}

      <div className="mb-4 flex items-center gap-3">
        <Filter size={16} className="text-text-dim" />
        <select
          value={stat}
          onChange={(e) => setStat(e.target.value)}
          className="rounded-lg border border-border bg-surface-card px-3 py-2 text-sm text-text outline-none focus:border-accent/40"
        >
          <option value="All">Stat: All</option>
          {(data?.summary.stats ?? []).map((s) => (
            <option key={s} value={s}>
              Stat: {s.replace("player_", "")}
            </option>
          ))}
        </select>
        <select
          value={edgeType}
          onChange={(e) => setEdgeType(e.target.value)}
          className="rounded-lg border border-border bg-surface-card px-3 py-2 text-sm text-text outline-none focus:border-accent/40"
        >
          <option value="All">All Edge Types</option>
          <option value="Line Discrepancy">Line Discrepancy</option>
          <option value="+EV Odds Juice">+EV Odds Juice</option>
        </select>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
        <div
          className={`grid ${GRID} gap-3 border-b border-border px-4 py-3 text-xs font-semibold uppercase tracking-widest text-text-dim`}
        >
          <span>Player</span>
          <span>Verdict</span>
          <span>Play</span>
          <span>PP</span>
          <span>Sharp</span>
          <span>Win % / EV</span>
          <span>Edge Type</span>
          <span>Result</span>
          <span>Flagged</span>
        </div>

        <div className="space-y-2 p-3">
          {loading ? (
            <EmptyState message="Loading opportunities..." />
          ) : !data?.edges.length ? (
            <EmptyState message="No active opportunities yet. Run edge detection first." />
          ) : (
            data.edges.map((edge) => <EdgeRow key={edge.id} edge={edge} />)
          )}
        </div>
      </div>
    </div>
  );
}
