import { Download, Filter } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type Edge, type EdgesResponse } from "../lib/api";
import { Badge, EmptyState, formatTime, MetricCard, PageHeader } from "../components/ui";

function edgeBadgeVariant(
  edgeType: string,
): "cyan" | "purple" {
  return edgeType === "Line Discrepancy" ? "cyan" : "purple";
}

function rowBorderClass(edgeType: string): string {
  return edgeType === "Line Discrepancy"
    ? "border-cyan-500/30 shadow-[inset_0_0_0_1px_rgba(34,211,238,0.06),0_0_20px_rgba(34,211,238,0.04)]"
    : "border-purple-500/30 shadow-[inset_0_0_0_1px_rgba(192,132,252,0.06),0_0_20px_rgba(192,132,252,0.04)]";
}

function EdgeRow({ edge }: { edge: Edge }) {
  return (
    <div
      className={`grid grid-cols-[1.4fr_1fr_0.7fr_0.7fr_0.7fr_1.2fr_0.9fr] items-center gap-4 rounded-xl border bg-surface-card px-4 py-3.5 ${rowBorderClass(edge.edge_type)}`}
    >
      <div>
        <p className="font-semibold text-text">{edge.player}</p>
        <p className="text-xs text-text-dim">{edge.team}</p>
      </div>
      <div>
        <Badge variant={edgeBadgeVariant(edge.edge_type)}>{edge.edge_type}</Badge>
      </div>
      <div>
        <Badge variant={edge.play === "OVER" ? "over" : "under"}>
          {edge.play}
        </Badge>
      </div>
      <div>
        <Badge variant="orange">{edge.pp_line}</Badge>
      </div>
      <div>
        <Badge variant="cyan">{edge.dk_line}</Badge>
      </div>
      <p className="truncate text-xs text-text-dim">{edge.probability_text}</p>
      <p className="text-xs text-text-dim">{formatTime(edge.flagged_at)}</p>
    </div>
  );
}

export function OpportunitiesPage() {
  const [stat, setStat] = useState("player_points");
  const [edgeType, setEdgeType] = useState("All");
  const [data, setData] = useState<EdgesResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.getEdges(stat, edgeType));
    } catch {
      setData({ edges: [], summary: { unique: 0, line_discrepancy: 0, ev_juice: 0 } });
    } finally {
      setLoading(false);
    }
  }, [stat, edgeType]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div>
      <PageHeader
        title="Active Opportunities"
        subtitle="Deduped edge list sorted by value."
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
        <div className="mb-6 grid grid-cols-3 gap-3">
          <MetricCard label="Unique Signals" value={data.summary.unique} />
          <MetricCard
            label="Line Discrepancy"
            value={data.summary.line_discrepancy}
          />
          <MetricCard label="+EV Juice" value={data.summary.ev_juice} />
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
          <option value="player_points">Stat: player_points</option>
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
        <div className="grid grid-cols-[1.4fr_1fr_0.7fr_0.7fr_0.7fr_1.2fr_0.9fr] gap-4 border-b border-border px-4 py-3 text-xs font-semibold uppercase tracking-widest text-text-dim">
          <span>Player</span>
          <span>Edge Type</span>
          <span>Play</span>
          <span>PP Line</span>
          <span>DK Line</span>
          <span>Detail</span>
          <span>Flagged at</span>
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
