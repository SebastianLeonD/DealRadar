import {
  AlertTriangle,
  ArrowRightLeft,
  BookmarkPlus,
  Check,
  ChevronDown,
  Download,
  Loader2,
  Sparkles,
  Swords,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type Edge, type EdgesResponse, type RecordSummary } from "../lib/api";
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

/** A filter pill showing a stat and how many picks we have for it. */
function StatChip({
  label,
  count,
  active,
  onClick,
}: {
  label: string;
  count: number;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm font-semibold transition-colors ${
        active
          ? "border-ink bg-ink text-paper"
          : "border-line-strong bg-card text-ink-soft hover:border-ink hover:text-ink"
      }`}
    >
      <span className="truncate">{label}</span>
      <span className={`tnum shrink-0 text-xs ${active ? "text-paper/70" : "text-ink-faint"}`}>
        {count}
      </span>
    </button>
  );
}

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

/** Logs a pick as a bet you actually placed. */
function TrackBetButton({ edge, compact = false }: { edge: Edge; compact?: boolean }) {
  const [state, setState] = useState<"idle" | "saving" | "done">("idle");

  const track = async () => {
    setState("saving");
    try {
      await api.trackBet(edge);
      setState("done");
    } catch {
      setState("idle");
    }
  };

  const done = state === "done";
  if (compact) {
    return (
      <button
        onClick={track}
        disabled={state !== "idle"}
        title={done ? "Tracked in My Bets" : "Track this bet"}
        className={`rounded-md border p-1.5 transition-colors ${
          done
            ? "border-bet/40 bg-bet-soft text-bet"
            : "border-line-strong bg-card text-ink-soft hover:border-ink hover:text-ink"
        }`}
      >
        {done ? <Check size={13} /> : <BookmarkPlus size={13} />}
      </button>
    );
  }
  return (
    <button
      onClick={track}
      disabled={state !== "idle"}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors ${
        done
          ? "border-bet/40 bg-bet-soft text-bet"
          : "border-line-strong bg-card text-ink-soft hover:border-ink hover:text-ink"
      }`}
    >
      {done ? <Check size={13} /> : <BookmarkPlus size={13} />}
      {done ? "Tracked" : "Track bet"}
    </button>
  );
}

/** Where to bet the engine's chosen side: Underdog when its line is softer. */
function UnderdogPick({ edge }: { edge: Edge }) {
  const ud = edge.underdog;
  if (!ud) return null;
  const side = edge.play === "OVER" ? "Over" : "Under";

  if (ud.bet_on_underdog) {
    return (
      <div className="mt-2 flex items-start gap-2 rounded-md border border-bet/30 bg-bet-soft/50 px-3 py-2">
        <ArrowRightLeft size={14} className="mt-0.5 shrink-0 text-bet" />
        <p className="text-xs leading-relaxed text-ink">
          Bet the {side} on <span className="font-semibold">Underdog</span> — softer line at{" "}
          <span className="tnum font-semibold">{ud.ud_line}</span> vs PrizePicks'{" "}
          <span className="tnum">{edge.pp_line}</span>
          {ud.play_price ? <span className="text-ink-faint"> ({ud.play_price})</span> : null}
        </p>
      </div>
    );
  }
  return (
    <p className="mt-2 flex items-center gap-1.5 text-xs text-ink-faint">
      <ArrowRightLeft size={12} className="shrink-0" />
      {ud.best_app === "EVEN"
        ? `Underdog has the same line (${ud.ud_line}) — bet either.`
        : `PrizePicks has the better ${side.toLowerCase()} line (Underdog ${ud.ud_line}).`}
    </p>
  );
}

/* ---------- featured card for a play the engine likes ---------- */

function StrongPickCard({
  edge,
  entry,
  onAnalyze,
}: {
  edge: Edge;
  entry: AiEntry | undefined;
  onAnalyze: (edge: Edge) => void;
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
        <UnderdogPick edge={edge} />
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
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
            <Sparkles size={12} />
            Claude's read
          </div>
          <TrackBetButton edge={edge} />
        </div>
        <AiResult edge={edge} entry={entry} onAnalyze={onAnalyze} />
        <PromptBox edge={edge} mode="full" />
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
}: {
  edge: Edge;
  entry: AiEntry | undefined;
  onAnalyze: (edge: Edge) => void;
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
            {edge.underdog?.bet_on_underdog && <Badge variant="bet">UD line</Badge>}
          </div>
          {edge.ev_percent != null && (
            <p className="tnum mt-1 text-xs text-ink-faint">
              edge {edge.ev_percent >= 0 ? "+" : ""}
              {edge.ev_percent.toFixed(1)}%
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-1.5">
          <TrackBetButton edge={edge} compact />
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
          <UnderdogPick edge={edge} />
          <AiResult edge={edge} entry={entry} onAnalyze={onAnalyze} />
          <PromptBox edge={edge} mode="full" />
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
  const { ai, analyze } = useAiAnalysis("full");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.getEdges("All", "All"));
    } catch {
      setData({
        edges: [],
        summary: { unique: 0, line_discrepancy: 0, ev_juice: 0, yes_count: 0, stats: [] },
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.getRecord().then(setRecord).catch(() => {});
  }, []);

  // Fetch every stat once, then filter in the browser so the stat chips can
  // show a live pick count per stat.
  const allEdges = data?.edges ?? [];
  const statCounts: Record<string, number> = {};
  for (const e of allEdges) statCounts[e.stat_type] = (statCounts[e.stat_type] ?? 0) + 1;
  const statList = Object.keys(statCounts).sort();

  const byStat = stat === "All" ? allEdges : allEdges.filter((e) => e.stat_type === stat);
  const edges = verdict === "All" ? byStat : byStat.filter((e) => e.verdict === verdict);
  const strong = edges.filter(isStrong); // featured cards respect both filters

  return (
    <div>
      <PageHeader
        title="Upcoming Picks"
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
          <MetricCard label="Bet-worthy" value={data.summary.yes_count} hint="verdict: YES" />
          <MetricCard label="Upcoming picks" value={data.summary.unique} hint="above break-even" />
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

      <div className="flex flex-col gap-6 lg:flex-row">
        {/* filter sidebar */}
        <aside className="rise rise-2 shrink-0 lg:w-56">
          <div className="space-y-6 lg:sticky lg:top-4">
            <div>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
                Verdict
              </h3>
              <div className="flex flex-col gap-1.5">
                {VERDICT_FILTERS.map((f) => (
                  <StatChip
                    key={f.value}
                    label={f.label}
                    count={
                      f.value === "All"
                        ? byStat.length
                        : byStat.filter((e) => e.verdict === f.value).length
                    }
                    active={verdict === f.value}
                    onClick={() => setVerdict(f.value)}
                  />
                ))}
              </div>
            </div>

            <div>
              <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
                Stat
              </h3>
              <div className="flex flex-col gap-1.5">
                <StatChip
                  label="All stats"
                  count={allEdges.length}
                  active={stat === "All"}
                  onClick={() => setStat("All")}
                />
                {statList.map((s) => (
                  <StatChip
                    key={s}
                    label={statLabel(s)}
                    count={statCounts[s]}
                    active={stat === s}
                    onClick={() => setStat(s)}
                  />
                ))}
              </div>
            </div>
          </div>
        </aside>

        {/* picks */}
        <div className="min-w-0 flex-1 space-y-8">
          {!loading && strong.length > 0 && (
            <section className="rise rise-2">
              <div className="mb-3 flex items-center gap-2">
                <Sparkles size={16} className="text-ink" />
                <h2 className="text-lg font-semibold text-ink" style={{ fontFamily: "var(--font-display)" }}>
                  Worth a look
                </h2>
                <span className="text-xs text-ink-faint">
                  {strong.length} pick{strong.length > 1 ? "s" : ""} the engine likes — ask Claude on the ones you care about
                </span>
              </div>
              <div className="grid gap-4 xl:grid-cols-2">
                {strong.map((edge) => (
                  <StrongPickCard
                    key={edge.id}
                    edge={edge}
                    entry={ai[edge.id]}
                    onAnalyze={analyze}
                  />
                ))}
              </div>
            </section>
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
                      ? `No "${VERDICT_FILTERS.find((f) => f.value === verdict)?.label}" picks right now.`
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
                />
              ))
            )}
          </div>

          <p className="rise rise-4 text-xs leading-relaxed text-ink-faint">
            The small tick on each win-chance bar marks 54.25% — the break-even point. Picks below it
            lose money long-term, so they never appear here. Claude's read is an on-demand second
            opinion that weighs the opponent and any warnings; it is not financial advice.
          </p>
        </div>
      </div>
    </div>
  );
}
