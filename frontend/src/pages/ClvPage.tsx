import { Loader2, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, type ClvResponse, type ClvRow } from "../lib/api";
import { Badge, EmptyState, formatDate, MetricCard, PageHeader } from "../components/ui";

function edgeBadgeVariant(edgeType: string): "cyan" | "purple" {
  return edgeType === "Line Discrepancy" ? "cyan" : "purple";
}

function ClvRowItem({ row }: { row: ClvRow }) {
  const clvVariant =
    row.clv > 0 ? "over" : row.clv < 0 ? "under" : "neutral";

  return (
    <div className="grid grid-cols-[1.2fr_1fr_0.7fr_0.7fr_0.7fr_0.7fr_0.7fr_0.7fr] items-center gap-4 rounded-xl border border-border bg-surface-card px-4 py-3.5">
      <p className="font-semibold text-text">{row.player}</p>
      <Badge variant={edgeBadgeVariant(row.edge_type)}>{row.edge_type}</Badge>
      <Badge variant={row.play === "OVER" ? "over" : "under"}>{row.play}</Badge>
      <Badge variant="orange">{row.original_line}</Badge>
      <Badge variant="cyan">{row.dk_line_at_flag}</Badge>
      <Badge variant="cyan">{row.dk_line_now}</Badge>
      <Badge variant="purple">{row.movement}</Badge>
      <Badge variant={clvVariant}>
        {row.clv > 0 ? "+" : ""}
        {row.clv}
      </Badge>
    </div>
  );
}

export function ClvPage() {
  const [data, setData] = useState<ClvResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    try {
      setData(refresh ? await api.refreshClv() : await api.getClv());
    } catch {
      setData({
        rows: [],
        summary: { unique: 0, positive_rate: 0, positive_count: 0, avg_clv: 0 },
        daily: [],
      });
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const chartData =
    data?.daily.map((d) => ({
      date: formatDate(d.date),
      avg_clv: d.avg_clv,
    })) ?? [];

  return (
    <div>
      <PageHeader
        title="CLV Performance"
        subtitle="Track Closing Line Value against DraftKings live movement."
        action={
          <button
            type="button"
            disabled={refreshing}
            onClick={() => load(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-accent/40 bg-accent/10 px-4 py-2 text-sm font-medium text-accent hover:bg-accent/15 disabled:opacity-50"
          >
            {refreshing ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <RefreshCw size={16} />
            )}
            Refresh CLV
          </button>
        }
      />

      {data && !loading && (
        <div className="mb-6 grid grid-cols-3 gap-3">
          <MetricCard label="Unique Edges Monitored" value={data.summary.unique} />
          <MetricCard
            label="Positive CLV Rate"
            value={`${data.summary.positive_rate}%`}
          />
          <MetricCard
            label="Average CLV (pts)"
            value={`${data.summary.avg_clv > 0 ? "+" : ""}${data.summary.avg_clv} pts`}
          />
        </div>
      )}

      <div className="mb-6 rounded-xl border border-border bg-surface-card p-5">
        <h3 className="mb-4 text-sm font-semibold text-text">
          Average CLV (Last 7 Days)
        </h3>
        {chartData.length === 0 ? (
          <EmptyState message="No CLV history yet." />
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="clvGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00ff88" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#00ff88" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: "#64748b", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#64748b", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                domain={["auto", "auto"]}
              />
              <Tooltip
                contentStyle={{
                  background: "#1a1a1a",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                labelStyle={{ color: "#94a3b8" }}
                itemStyle={{ color: "#00ff88" }}
              />
              <Area
                type="monotone"
                dataKey="avg_clv"
                stroke="#00ff88"
                strokeWidth={2}
                fill="url(#clvGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-surface-raised">
        <div className="grid grid-cols-[1.2fr_1fr_0.7fr_0.7fr_0.7fr_0.7fr_0.7fr_0.7fr] gap-4 border-b border-border px-4 py-3 text-xs font-semibold uppercase tracking-widest text-text-dim">
          <span>Player</span>
          <span>Edge</span>
          <span>Play</span>
          <span>Orig PP</span>
          <span>DK @ Flag</span>
          <span>DK Now</span>
          <span>Movement</span>
          <span>CLV</span>
        </div>

        <div className="space-y-2 p-3">
          {loading ? (
            <EmptyState message="Loading CLV data..." />
          ) : !data?.rows.length ? (
            <EmptyState message="No CLV data yet. Log edges, re-scrape DK, then refresh." />
          ) : (
            data.rows.map((row, i) => (
              <ClvRowItem key={`${row.pp_player_name}-${row.flagged_at}-${i}`} row={row} />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
