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
import { api, type ClvResponse, type ClvRow, type RecordSummary } from "../lib/api";
import { Badge, EmptyState, formatDate, MetricCard, PageHeader } from "../components/ui";

const GRID = "grid-cols-[1.4fr_1fr_0.8fr_0.8fr_0.8fr_1fr]";

function MovementRow({ row }: { row: ClvRow }) {
  const good = row.clv > 0;
  const flat = row.clv === 0;
  return (
    <div className={`grid ${GRID} items-center gap-4 border-b border-line px-4 py-3.5 last:border-b-0`}>
      <p className="truncate font-semibold text-ink">{row.player}</p>
      <p className="text-sm text-ink-soft">
        {row.play === "OVER" ? "Over" : "Under"}{" "}
        <span className="tnum">{row.original_line}</span>
      </p>
      <p className="tnum text-sm text-ink-soft">{row.dk_line_at_flag}</p>
      <p className="tnum text-sm text-ink-soft">{row.dk_line_now}</p>
      <p className={`tnum text-sm font-semibold ${flat ? "text-ink-faint" : good ? "text-bet" : "text-skip"}`}>
        {row.clv > 0 ? "+" : ""}
        {row.clv}
      </p>
      <div>
        <Badge variant={flat ? "neutral" : good ? "bet" : "skip"}>
          {flat ? "No move" : good ? "Moved your way" : "Moved against you"}
        </Badge>
      </div>
    </div>
  );
}

export function ClvPage() {
  const [data, setData] = useState<ClvResponse | null>(null);
  const [record, setRecord] = useState<RecordSummary | null>(null);
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
    api.getRecord().then(setRecord).catch(() => {});
  }, [load]);

  const chartData =
    data?.daily.map((d) => ({ date: formatDate(d.date), avg_clv: d.avg_clv })) ?? [];

  return (
    <div>
      <PageHeader
        title="Results"
        subtitle="Two scoreboards: did your picks actually win, and did the betting market drift toward your number after you picked?"
        action={
          <button
            type="button"
            disabled={refreshing}
            onClick={() => load(true)}
            className="inline-flex items-center gap-2 rounded-md border border-line-strong bg-card px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-ink disabled:opacity-40"
          >
            {refreshing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            Refresh
          </button>
        }
      />

      <div className="rise rise-1 mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="Record"
          value={
            record?.settled
              ? `${record.wins}–${record.losses}${record.pushes ? `–${record.pushes}` : ""}`
              : "—"
          }
          hint="graded picks, counted once"
        />
        <MetricCard
          label="Hit rate"
          value={record?.hit_rate != null ? `${record.hit_rate}%` : "—"}
          hint="break-even is 54.25%"
        />
        <MetricCard
          label="Market agreed"
          value={`${data?.summary.positive_rate ?? 0}%`}
          hint="lines drifted your way"
        />
        <MetricCard
          label="Avg drift"
          value={`${(data?.summary.avg_clv ?? 0) > 0 ? "+" : ""}${data?.summary.avg_clv ?? 0}`}
          hint="points, after you picked"
        />
      </div>

      <div className="rise rise-2 mb-8 rounded-lg border border-line bg-card p-5">
        <h3 className="mb-1 text-sm font-semibold text-ink">Line drift, last 7 days</h3>
        <p className="mb-4 text-xs text-ink-faint">
          Above zero = the bookmakers kept moving toward your picks after you found them. A
          good long-term sign even on losing nights.
        </p>
        {chartData.length === 0 ? (
          <EmptyState message="No history yet — picks need a re-scrape after you find them." />
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="clvGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#0c7a43" stopOpacity={0.18} />
                  <stop offset="100%" stopColor="#0c7a43" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#e9e6de" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: "#9aa1a9", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: "#9aa1a9", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                domain={["auto", "auto"]}
              />
              <Tooltip
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid #d8d4c8",
                  borderRadius: 8,
                  fontSize: 12,
                  color: "#191b1f",
                }}
                labelStyle={{ color: "#565d66" }}
                itemStyle={{ color: "#0c7a43" }}
              />
              <Area
                type="monotone"
                dataKey="avg_clv"
                stroke="#0c7a43"
                strokeWidth={2}
                fill="url(#clvGradient)"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      <div className="rise rise-3 overflow-hidden rounded-lg border border-line bg-card">
        <div
          className={`grid ${GRID} gap-4 border-b-2 border-ink px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-soft`}
        >
          <span>Player</span>
          <span>Your pick</span>
          <span>Books then</span>
          <span>Books now</span>
          <span>Drift</span>
          <span>Verdict on the market</span>
        </div>

        {loading ? (
          <div className="p-4">
            <EmptyState message="Loading..." />
          </div>
        ) : !data?.rows.length ? (
          <div className="p-4">
            <EmptyState message="Nothing tracked yet. Find picks first, then re-run step 1 later." />
          </div>
        ) : (
          data.rows.map((row, i) => (
            <MovementRow key={`${row.pp_player_name}-${row.flagged_at}-${i}`} row={row} />
          ))
        )}
      </div>
    </div>
  );
}
