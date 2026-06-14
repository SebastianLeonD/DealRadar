import { AlertTriangle, Download, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AiRecommendation,
  type Edge,
  type EdgesResponse,
  type RecordSummary,
} from "../lib/api";
import {
  Badge,
  EmptyState,
  formatTime,
  MetricCard,
  PageHeader,
  statLabel,
  verdictWord,
  WinBar,
} from "../components/ui";

function verdictVariant(verdict: Edge["verdict"]): "bet" | "maybe" | "skip" | "neutral" {
  if (verdict === "YES") return "bet";
  if (verdict === "LEAN") return "maybe";
  if (verdict === "NO") return "skip";
  return "neutral";
}

const GRID = "grid-cols-[1.5fr_1.6fr_0.9fr_1.1fr_0.8fr_0.7fr]";

function AiPanel({ edge }: { edge: Edge }) {
  const [loading, setLoading] = useState(false);
  const [rec, setRec] = useState<AiRecommendation | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.analyzeEdge(edge);
      if (res.ok && res.recommendation) {
        setRec(res.recommendation);
      } else {
        setError(res.error ?? "Analysis failed.");
      }
    } catch {
      setError("Could not reach the analyst.");
    } finally {
      setLoading(false);
    }
  }, [edge]);

  return (
    <div className="px-4 pb-3">
      {!rec && (
        <button
          onClick={ask}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-card px-2.5 py-1 text-xs font-semibold text-ink-soft transition-colors hover:border-ink hover:text-ink disabled:opacity-50"
        >
          <Sparkles size={12} />
          {loading ? "Asking Claude…" : "Ask AI"}
        </button>
      )}
      {error && (
        <p className="mt-1 text-xs text-skip">
          AI: {error}{" "}
          <button onClick={ask} className="underline hover:text-ink">
            retry
          </button>
        </p>
      )}
      {rec && (
        <div className="rounded-md border border-line bg-paper px-3 py-2.5">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <Badge variant={rec.pick === "PASS" ? "skip" : "bet"}>{rec.pick}</Badge>
            <span className="tnum text-xs text-ink-faint">{rec.confidence}% confidence</span>
            <Badge variant={rec.agrees_with_engine ? "info" : "maybe"}>
              {rec.agrees_with_engine ? "agrees with engine" : "differs from engine"}
            </Badge>
          </div>
          <p className="text-sm text-ink-soft">{rec.reasoning}</p>
          {rec.key_factors.length > 0 && (
            <ul className="mt-1.5 list-disc pl-4 text-xs text-ink-faint">
              {rec.key_factors.map((factor, i) => (
                <li key={i}>{factor}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function PickRow({ edge }: { edge: Edge }) {
  const word = verdictWord(edge.verdict);
  return (
    <div
      className={`border-b border-line transition-colors last:border-b-0 hover:bg-paper ${
        word === "YES" ? "bg-bet-soft/30" : ""
      }`}
    >
      <div className={`grid ${GRID} items-center gap-4 px-4 py-4`}>
      {/* who */}
      <div className="flex min-w-0 items-center gap-2">
        <div className="min-w-0">
          <p className="truncate font-semibold text-ink">{edge.player}</p>
          <p className="truncate text-xs text-ink-faint">{edge.team}</p>
        </div>
        {edge.flags && (
          <span title={edge.flags} className="shrink-0 cursor-help">
            <AlertTriangle size={15} className="text-maybe" />
          </span>
        )}
      </div>

      {/* the bet, in words */}
      <div>
        <p className="text-sm font-semibold text-ink">
          {edge.play === "OVER" ? "Over" : "Under"}{" "}
          <span className="tnum">{edge.pp_line}</span> {statLabel(edge.stat_type)}
        </p>
        <p className="text-xs text-ink-faint">
          books say <span className="tnum">{edge.dk_line}</span>
          {edge.book_count ? ` · ${edge.book_count} book${edge.book_count > 1 ? "s" : ""}` : ""}
        </p>
      </div>

      {/* win chance */}
      <div>
        {edge.win_prob != null ? (
          <>
            <p className="tnum text-sm font-semibold text-ink">
              {(edge.win_prob * 100).toFixed(1)}%
            </p>
            <WinBar prob={edge.win_prob} />
          </>
        ) : (
          <p className="text-xs text-ink-faint">—</p>
        )}
      </div>

      {/* verdict */}
      <div>
        <Badge variant={verdictVariant(edge.verdict)}>{word}</Badge>
        {edge.ev_percent != null && (
          <p className="tnum mt-1 text-xs text-ink-faint">
            edge {edge.ev_percent >= 0 ? "+" : ""}
            {edge.ev_percent.toFixed(1)}%
          </p>
        )}
      </div>

      {/* result */}
      <div>
        {edge.result ? (
          <Badge variant={edge.result === "WIN" ? "bet" : edge.result === "LOSS" ? "skip" : "neutral"}>
            {edge.result === "WIN" ? "Won" : edge.result === "LOSS" ? "Lost" : "Push"}
            {edge.actual_value != null ? ` · ${edge.actual_value}` : ""}
          </Badge>
        ) : (
          <span className="text-xs text-ink-faint">not played yet</span>
        )}
      </div>

        <p className="tnum text-right text-xs text-ink-faint">{formatTime(edge.flagged_at)}</p>
      </div>
      <AiPanel edge={edge} />
    </div>
  );
}

export function OpportunitiesPage() {
  const [stat, setStat] = useState("All");
  const [data, setData] = useState<EdgesResponse | null>(null);
  const [record, setRecord] = useState<RecordSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.getEdges(stat, "All"));
    } catch {
      setData({
        edges: [],
        summary: { unique: 0, line_discrepancy: 0, ev_juice: 0, yes_count: 0, stats: [] },
      });
    } finally {
      setLoading(false);
    }
  }, [stat]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.getRecord().then(setRecord).catch(() => {});
  }, []);

  return (
    <div>
      <PageHeader
        title="Today's Picks"
        subtitle="Every PrizePicks line, priced against the bookmakers. YES means bet it. MAYBE means read the warning first."
        action={
          <a
            href={api.exportEdgesUrl(stat, "All")}
            download="picks.csv"
            className="inline-flex items-center gap-2 rounded-md border border-line-strong bg-card px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-ink"
          >
            <Download size={15} />
            Export
          </a>
        }
      />

      {data && !loading && (
        <div className="rise rise-1 mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Bet-worthy today" value={data.summary.yes_count} hint="verdict: YES" />
          <MetricCard label="Picks found" value={data.summary.unique} hint="above break-even" />
          <MetricCard
            label="Lifetime record"
            value={
              record?.settled
                ? `${record.wins}–${record.losses}${record.pushes ? `–${record.pushes}` : ""}`
                : "—"
            }
            hint="wins–losses–pushes"
          />
          <MetricCard
            label="Hit rate"
            value={record?.hit_rate != null ? `${record.hit_rate}%` : "—"}
            hint="needs 54.25% to profit"
          />
        </div>
      )}

      <div className="rise rise-2 mb-4 flex items-center justify-between">
        <select
          value={stat}
          onChange={(e) => setStat(e.target.value)}
          className="rounded-md border border-line-strong bg-card px-3 py-2 text-sm font-medium text-ink outline-none focus:border-ink"
        >
          <option value="All">All stats</option>
          {(data?.summary.stats ?? []).map((s) => (
            <option key={s} value={s}>
              {statLabel(s)}
            </option>
          ))}
        </select>
        <p className="text-xs text-ink-faint">
          Hover the <AlertTriangle size={11} className="inline text-maybe" /> icon to read a
          pick's warning
        </p>
      </div>

      <div className="rise rise-3 overflow-hidden rounded-lg border border-line bg-card">
        <div
          className={`grid ${GRID} gap-4 border-b-2 border-ink px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-soft`}
        >
          <span>Player</span>
          <span>The bet</span>
          <span>Win chance</span>
          <span>Verdict</span>
          <span>Result</span>
          <span className="text-right">Found</span>
        </div>

        {loading ? (
          <div className="p-4">
            <EmptyState message="Loading picks..." />
          </div>
        ) : !data?.edges.length ? (
          <div className="p-4">
            <EmptyState message="No picks yet. Go to Update Data and run the pipeline." />
          </div>
        ) : (
          data.edges.map((edge) => <PickRow key={edge.id} edge={edge} />)
        )}
      </div>

      <p className="rise rise-4 mt-4 text-xs leading-relaxed text-ink-faint">
        The small tick on each win-chance bar marks 54.25% — the break-even point. Picks below
        it lose money long-term, so they never appear here.
      </p>
    </div>
  );
}
