import { AlertTriangle, ChevronDown, Download, Loader2, Sparkles, Swords } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  api,
  type AnalysisMode,
  type Edge,
  type EdgesResponse,
  type RecordSummary,
} from "../lib/api";
import {
  Badge,
  EmptyState,
  MetricCard,
  PageHeader,
  statLabel,
  verdictWord,
  WinBar,
} from "../components/ui";
import { AiResult, type AiEntry, PromptBox, useAiAnalysis } from "../components/ai";

function verdictVariant(verdict: Edge["verdict"]): "bet" | "maybe" | "skip" | "neutral" {
  if (verdict === "YES") return "bet";
  if (verdict === "LEAN") return "maybe";
  if (verdict === "NO") return "skip";
  return "neutral";
}

function isStrong(edge: Edge): boolean {
  return edge.verdict === "YES" || edge.verdict === "LEAN";
}

type VerdictFilter = "All" | "YES" | "LEAN" | "NO";

const VERDICT_FILTERS: { value: VerdictFilter; label: string }[] = [
  { value: "All", label: "All" },
  { value: "YES", label: "Yes" },
  { value: "LEAN", label: "Maybe" },
  { value: "NO", label: "No" },
];

function matchupLabel(edge: Edge): string | null {
  if (edge.opponent) return `vs ${edge.opponent}`;
  if (edge.game) return edge.game;
  return null;
}

function isModeled(edge: Edge): boolean {
  return edge.edge_type === "Form Model";
}

/** "books say 1.5 · 3 books" for market plays, "our model · 5.0/game" for modeled. */
function LineSource({ edge }: { edge: Edge }) {
  if (isModeled(edge)) {
    return (
      <p className="mt-0.5 text-xs text-ink-faint">
        our model · <span className="tnum">{edge.dk_line}</span>/game avg
      </p>
    );
  }
  return (
    <p className="mt-0.5 text-xs text-ink-faint">
      books say <span className="tnum">{edge.dk_line}</span>
      {edge.book_count ? ` · ${edge.book_count} book${edge.book_count > 1 ? "s" : ""}` : ""}
    </p>
  );
}

/* ---------- featured card for a play the engine likes ---------- */

function StrongPickCard({
  edge,
  entry,
  onAnalyze,
  mode,
}: {
  edge: Edge;
  entry: AiEntry | undefined;
  onAnalyze: (edge: Edge) => void;
  mode: AnalysisMode;
}) {
  const word = verdictWord(edge.verdict);
  const matchup = matchupLabel(edge);

  return (
    <div className="rise flex flex-col overflow-hidden rounded-lg border border-line bg-card">
      <div
        className={`flex items-start justify-between gap-3 px-5 pt-4 ${
          word === "YES" ? "border-l-2 border-bet" : "border-l-2 border-maybe"
        }`}
      >
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold leading-tight text-ink">{edge.player}</p>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-ink-faint">
            <span className="truncate">{edge.team}</span>
            {matchup && (
              <>
                <Swords size={11} className="shrink-0" />
                <span className="truncate">{matchup}</span>
              </>
            )}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Badge variant={verdictVariant(edge.verdict)}>{word}</Badge>
          {isModeled(edge) && <Badge variant="info">modeled</Badge>}
        </div>
      </div>

      <div className="px-5 pt-3">
        <p className="text-sm font-semibold text-ink">
          {edge.play === "OVER" ? "Over" : "Under"}{" "}
          <span className="tnum">{edge.pp_line}</span> {statLabel(edge.stat_type)}
        </p>
        <LineSource edge={edge} />
      </div>

      <div className="mt-3 flex items-center gap-5 px-5">
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
          <p className="mt-1 text-[11px] uppercase tracking-wide text-ink-faint">win chance</p>
        </div>
        {edge.ev_percent != null && (
          <div>
            <p className="tnum text-sm font-semibold text-ink">
              {edge.ev_percent >= 0 ? "+" : ""}
              {edge.ev_percent.toFixed(1)}%
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-wide text-ink-faint">edge</p>
          </div>
        )}
      </div>

      {edge.flags && (
        <div className="mx-5 mt-3 flex items-start gap-2 rounded-md border border-maybe/25 bg-maybe-soft px-3 py-2">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-maybe" />
          <p className="text-xs leading-relaxed text-maybe">{edge.flags}</p>
        </div>
      )}

      <div className="mt-3 border-t border-line bg-paper px-5 py-4">
        <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
          <Sparkles size={12} />
          Claude's read
        </div>
        <AiResult edge={edge} entry={entry} onAnalyze={onAnalyze} />
        <PromptBox edge={edge} mode={mode} />
      </div>
    </div>
  );
}

/* ---------- compact row for the full board ---------- */

const GRID = "grid-cols-[1.8fr_1.7fr_1fr_1fr_0.7fr]";

function BoardRow({
  edge,
  entry,
  onAnalyze,
  mode,
}: {
  edge: Edge;
  entry: AiEntry | undefined;
  onAnalyze: (edge: Edge) => void;
  mode: AnalysisMode;
}) {
  const word = verdictWord(edge.verdict);
  const [open, setOpen] = useState(false);

  return (
    <div
      className={`border-b border-line transition-colors last:border-b-0 hover:bg-paper ${
        word === "YES" ? "bg-bet-soft/30" : ""
      }`}
    >
      <div className={`grid ${GRID} items-center gap-4 px-4 py-3.5`}>
        <div className="flex min-w-0 items-center gap-2">
          <div className="min-w-0">
            <p className="truncate font-semibold text-ink">{edge.player}</p>
            <p className="truncate text-xs text-ink-faint">
              {edge.team}
              {edge.opponent ? ` · vs ${edge.opponent}` : ""}
            </p>
          </div>
          {edge.flags && (
            <span title={edge.flags} className="shrink-0 cursor-help">
              <AlertTriangle size={15} className="text-maybe" />
            </span>
          )}
        </div>

        <div>
          <p className="text-sm font-semibold text-ink">
            {edge.play === "OVER" ? "Over" : "Under"}{" "}
            <span className="tnum">{edge.pp_line}</span> {statLabel(edge.stat_type)}
          </p>
          <LineSource edge={edge} />
        </div>

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

        <div>
          <div className="flex flex-wrap items-center gap-1">
            <Badge variant={verdictVariant(edge.verdict)}>{word}</Badge>
            {isModeled(edge) && <Badge variant="info">modeled</Badge>}
          </div>
          {edge.ev_percent != null && (
            <p className="tnum mt-1 text-xs text-ink-faint">
              edge {edge.ev_percent >= 0 ? "+" : ""}
              {edge.ev_percent.toFixed(1)}%
            </p>
          )}
        </div>

        <div className="flex justify-end">
          <button
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1 rounded-md border border-line-strong bg-card px-2 py-1 text-xs font-semibold text-ink-soft transition-colors hover:border-ink hover:text-ink"
          >
            {entry?.status === "loading" ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Sparkles size={12} />
            )}
            {entry?.status === "done" ? entry.rec!.pick : "AI"}
            <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : ""}`} />
          </button>
        </div>
      </div>

      {open && (
        <div className="border-t border-line bg-paper px-4 py-3">
          <AiResult edge={edge} entry={entry} onAnalyze={onAnalyze} />
          <PromptBox edge={edge} mode={mode} />
        </div>
      )}
    </div>
  );
}

export function OpportunitiesPage() {
  const [stat, setStat] = useState("All");
  const [verdict, setVerdict] = useState<VerdictFilter>("All");
  const [data, setData] = useState<EdgesResponse | null>(null);
  const [record, setRecord] = useState<RecordSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<AnalysisMode>("full");
  const { ai, analyze } = useAiAnalysis(mode);

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

  const allEdges = data?.edges ?? [];
  const edges =
    verdict === "All" ? allEdges : allEdges.filter((e) => e.verdict === verdict);
  const strong = allEdges.filter(isStrong);

  return (
    <div>
      <PageHeader
        title="Today's Picks"
        subtitle="Upcoming PrizePicks lines, priced against the bookmakers. YES means bet it. MAYBE means read the warning first. Ask Claude on any pick for a matchup-aware second opinion."
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
          <MetricCard label="Picks today" value={data.summary.unique} hint="upcoming, above break-even" />
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

      {!loading && strong.length > 0 && (
        <section className="rise rise-2 mb-10">
          <div className="mb-3 flex items-center gap-2">
            <Sparkles size={16} className="text-ink" />
            <h2 className="text-lg font-semibold text-ink" style={{ fontFamily: "var(--font-display)" }}>
              Worth a look
            </h2>
            <span className="text-xs text-ink-faint">
              {strong.length} pick{strong.length > 1 ? "s" : ""} the engine likes — ask Claude on the ones you care about
            </span>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {strong.map((edge) => (
              <StrongPickCard
                key={edge.id}
                edge={edge}
                entry={ai[edge.id]}
                onAnalyze={analyze}
                mode={mode}
              />
            ))}
          </div>
        </section>
      )}

      <div className="rise rise-3 mb-4 flex flex-wrap items-center gap-3">
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

        <div className="inline-flex items-center rounded-md border border-line-strong bg-card p-0.5">
          {VERDICT_FILTERS.map((f) => {
            const active = verdict === f.value;
            const count =
              f.value === "All"
                ? allEdges.length
                : allEdges.filter((e) => e.verdict === f.value).length;
            return (
              <button
                key={f.value}
                onClick={() => setVerdict(f.value)}
                className={`rounded px-3 py-1.5 text-sm font-semibold transition-colors ${
                  active ? "bg-ink text-paper" : "text-ink-soft hover:text-ink"
                }`}
              >
                {f.label}
                <span className={`tnum ml-1.5 text-xs ${active ? "text-paper/70" : "text-ink-faint"}`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-ink-faint">AI read:</span>
          <div className="inline-flex items-center rounded-md border border-line-strong bg-card p-0.5">
            {([
              { value: "full", label: "Full" },
              { value: "stats_only", label: "PrizePicks-only" },
            ] as { value: AnalysisMode; label: string }[]).map((m) => {
              const active = mode === m.value;
              return (
                <button
                  key={m.value}
                  onClick={() => setMode(m.value)}
                  title={
                    m.value === "stats_only"
                      ? "Ask Claude using player + matchup form only — no sportsbook data"
                      : "Ask Claude with the full sharp-book read"
                  }
                  className={`rounded px-3 py-1.5 text-sm font-semibold transition-colors ${
                    active ? "bg-ink text-paper" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {m.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {mode === "stats_only" && (
        <p className="rise rise-3 -mt-2 mb-4 text-xs text-ink-faint">
          PrizePicks-only mode: Claude judges each play from the player's form and the
          matchup alone — no sportsbook lines. The stats half of the analysis.
        </p>
      )}

      <div className="rise rise-3 overflow-hidden rounded-lg border border-line bg-card">
        <div
          className={`grid ${GRID} gap-4 border-b-2 border-ink px-4 py-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-soft`}
        >
          <span>Player</span>
          <span>The bet</span>
          <span>Win chance</span>
          <span>Verdict</span>
          <span className="text-right">Claude</span>
        </div>

        {loading ? (
          <div className="p-4">
            <EmptyState message="Loading picks..." />
          </div>
        ) : !edges.length ? (
          <div className="p-4">
            <EmptyState
              message={
                allEdges.length
                  ? `No "${VERDICT_FILTERS.find((f) => f.value === verdict)?.label}" picks today.`
                  : "No upcoming picks. Go to Update Data and run the pipeline."
              }
            />
          </div>
        ) : (
          edges.map((edge) => (
            <BoardRow
              key={edge.id}
              edge={edge}
              entry={ai[edge.id]}
              onAnalyze={analyze}
              mode={mode}
            />
          ))
        )}
      </div>

      <p className="rise rise-4 mt-4 text-xs leading-relaxed text-ink-faint">
        The small tick on each win-chance bar marks 54.25% — the break-even point. Picks below it
        lose money long-term, so they never appear here. Claude's read is an on-demand second
        opinion that weighs the opponent and any warnings; it is not financial advice.
      </p>
    </div>
  );
}
