import { AlertTriangle, BookmarkPlus, Check, ChevronDown, Swords } from "lucide-react";
import { useEffect, useState } from "react";
import {
  api,
  type Edge,
  type PpBoardGame,
  type PpBoardGroup,
  type PpBoardProp,
  type PpEngine,
  type PpUnderdog,
  type RecordSummary,
} from "../lib/api";
import {
  Badge,
  EmptyState,
  MetricCard,
  PageHeader,
  SearchBox,
  statLabel,
  verdictWord,
  WinBar,
} from "../components/ui";
import { AiResult, type AiEntry, PromptBox, useAiAnalysis } from "../components/ai";

/** An Edge-shaped object for the AI call + bet tracking. Priced props carry the
 *  engine's read; plain props send just enough for a stats-only read. */
function toEdge(group: PpBoardGroup, prop: PpBoardProp, id: number): Edge {
  const e = prop.engine;
  return {
    id,
    player: prop.player,
    dk_player_name: prop.player,
    team: prop.team ?? "",
    opponent: prop.opponent ?? null,
    stat_type: group.mapped_stat ?? group.stat_type,
    pp_line: prop.line,
    play: e?.play ?? "OVER",
    win_prob: e?.win_prob ?? null,
    ev_percent: e?.ev_percent ?? null,
    verdict: e?.verdict ?? null,
    edge_type: e?.edge_type ?? null,
    book_count: e?.book_count ?? null,
    dk_line: e?.dk_line ?? null,
    commence_time: prop.start_time ?? null,
  } as unknown as Edge;
}

function groupLabel(group: PpBoardGroup): string {
  return group.mapped_stat ? statLabel(group.mapped_stat) : group.stat_type;
}

function kickoff(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" });
}

function verdictVariant(verdict: PpEngine["verdict"]): "bet" | "maybe" | "skip" | "neutral" {
  if (verdict === "YES") return "bet";
  if (verdict === "LEAN") return "maybe";
  if (verdict === "NO") return "skip";
  return "neutral";
}

const APP_NAME: Record<PpUnderdog["over_app"], string> = {
  UD: "Underdog",
  PP: "PrizePicks",
  EVEN: "either",
};

/* ---------- track bet ---------- */

function TrackBetButton({ edge }: { edge: Edge }) {
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

/* ---------- Underdog line-shop strip ---------- */

function UnderdogStrip({ ud }: { ud: PpUnderdog }) {
  if (ud.ud_delta === 0) {
    return (
      <div className="mt-2 flex items-center justify-between rounded-md border border-line bg-paper px-2.5 py-1.5 text-[11px] text-ink-faint">
        <span>Underdog · same line</span>
        {ud.ud_higher_multiplier != null && ud.ud_lower_multiplier != null && (
          <span className="tnum">
            ×{ud.ud_higher_multiplier} / ×{ud.ud_lower_multiplier}
          </span>
        )}
      </div>
    );
  }
  return (
    <div className="mt-2 rounded-md border border-bet/30 bg-bet-soft/40 px-2.5 py-1.5 text-[11px]">
      <div className="flex items-center justify-between">
        <span className="text-ink-faint">Underdog line</span>
        <span className="font-semibold text-ink">
          <span className="tnum">{ud.ud_line}</span>{" "}
          <span className="tnum text-ink-faint">
            ({ud.ud_delta > 0 ? "+" : ""}
            {ud.ud_delta})
          </span>
        </span>
      </div>
      <div className="mt-1 flex gap-3 text-ink-faint">
        <span>
          Over → <span className="font-semibold text-ink">{APP_NAME[ud.over_app]}</span>
        </span>
        <span>
          Under → <span className="font-semibold text-ink">{APP_NAME[ud.under_app]}</span>
        </span>
      </div>
    </div>
  );
}

/* ---------- a single prop, PrizePicks-style box ---------- */

function PlayerCard({
  group,
  prop,
  id,
  entry,
  onAnalyze,
  mode,
}: {
  group: PpBoardGroup;
  prop: PpBoardProp;
  id: number;
  entry: AiEntry | undefined;
  onAnalyze: (edge: Edge) => void;
  mode: "full" | "stats_only";
}) {
  const edge = toEdge(group, prop, id);
  const e = prop.engine;
  return (
    <div
      className={`flex flex-col rounded-lg border bg-card p-3 ${
        e?.verdict === "YES" ? "border-bet/40" : "border-line"
      }`}
    >
      <div className="flex items-start gap-2.5">
        {prop.image_url ? (
          <img
            src={prop.image_url}
            alt=""
            loading="lazy"
            className="h-11 w-11 shrink-0 rounded-full bg-paper object-cover"
            onError={(ev) => (ev.currentTarget.style.display = "none")}
          />
        ) : null}
        <div className="min-w-0 flex-1">
          <p className="truncate text-[11px] text-ink-faint">
            {[prop.team, prop.position].filter(Boolean).join(" · ")}
          </p>
          <p className="truncate text-sm font-semibold leading-tight text-ink">{prop.player}</p>
          {prop.opponent && (
            <p className="mt-0.5 truncate text-[11px] text-ink-faint">
              vs {prop.opponent} {kickoff(prop.start_time)}
            </p>
          )}
        </div>
        {e && <Badge variant={verdictVariant(e.verdict)}>{verdictWord(e.verdict)}</Badge>}
      </div>

      <div className="mt-2.5 border-t border-line pt-2.5">
        {e ? (
          <>
            <p className="text-sm font-semibold text-ink">
              {e.play === "OVER" ? "Over" : "Under"} <span className="tnum">{prop.line}</span>{" "}
              {groupLabel(group)}
            </p>
            <div className="mt-2 flex items-center gap-4">
              {e.win_prob != null && (
                <div>
                  <p className="tnum text-sm font-semibold text-ink">
                    {(e.win_prob * 100).toFixed(1)}%
                  </p>
                  <WinBar prob={e.win_prob} />
                  <p className="mt-1 text-[10px] uppercase tracking-wide text-ink-faint">
                    win chance
                  </p>
                </div>
              )}
              {e.ev_percent != null && (
                <div>
                  <p className="tnum text-sm font-semibold text-ink">
                    {e.ev_percent >= 0 ? "+" : ""}
                    {e.ev_percent.toFixed(1)}%
                  </p>
                  <p className="mt-1 text-[10px] uppercase tracking-wide text-ink-faint">edge</p>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex items-baseline gap-1.5">
            <span className="tnum text-lg font-semibold text-ink">{prop.line}</span>
            <span className="text-xs text-ink-soft">{groupLabel(group)}</span>
          </div>
        )}
      </div>

      {e?.flags && (
        <div className="mt-2 flex items-start gap-1.5 rounded-md border border-maybe/25 bg-maybe-soft px-2.5 py-1.5">
          <AlertTriangle size={12} className="mt-0.5 shrink-0 text-maybe" />
          <p className="text-[11px] leading-relaxed text-maybe">{e.flags}</p>
        </div>
      )}

      {prop.underdog && <UnderdogStrip ud={prop.underdog} />}

      <div className="mt-2 space-y-2">
        {e && <TrackBetButton edge={edge} />}
        <div>
          <AiResult edge={edge} entry={entry} onAnalyze={onAnalyze} />
          <PromptBox edge={edge} mode={mode} />
        </div>
      </div>
    </div>
  );
}

/* ---------- a matchup square ---------- */

function GameSquare({
  game,
  active,
  onClick,
}: {
  game: PpBoardGame;
  active: boolean;
  onClick: () => void;
}) {
  const live = (game.status ?? "").toLowerCase().includes("progress");
  return (
    <button
      onClick={onClick}
      className={`flex flex-col gap-1.5 rounded-lg border px-3 py-3 text-left transition-colors ${
        active ? "border-ink bg-ink text-paper" : "border-line bg-card hover:border-line-strong"
      }`}
    >
      <div className="flex items-center gap-1.5 text-sm font-semibold leading-tight">
        <span className="truncate">{game.away}</span>
        <Swords size={11} className="shrink-0 opacity-60" />
        <span className="truncate">{game.home}</span>
      </div>
      <div className={`flex items-center gap-2 text-[11px] ${active ? "text-paper/70" : "text-ink-faint"}`}>
        <span>{live ? "Live now" : kickoff(game.start_time)}</span>
        <span className="tnum">· {game.count} props</span>
      </div>
    </button>
  );
}

const VERDICTS: { value: "All" | "YES" | "LEAN"; label: string }[] = [
  { value: "All", label: "All" },
  { value: "YES", label: "Yes" },
  { value: "LEAN", label: "Maybe" },
];

export function PrizePicksBoardPage() {
  const [data, setData] = useState<{
    groups: PpBoardGroup[];
    games: PpBoardGame[];
  } | null>(null);
  const [record, setRecord] = useState<RecordSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [selectedGame, setSelectedGame] = useState<string | null>(null);
  const [gapsOnly, setGapsOnly] = useState(false);
  const [picksOnly, setPicksOnly] = useState(false);
  const [verdict, setVerdict] = useState<"All" | "YES" | "LEAN">("All");
  const [query, setQuery] = useState("");

  const fullAi = useAiAnalysis("full");
  const statsAi = useAiAnalysis("stats_only");

  useEffect(() => {
    api
      .getPrizePicksBoard()
      .then((d) => setData({ groups: d.groups, games: d.games }))
      .catch(() => setData({ groups: [], games: [] }))
      .finally(() => setLoading(false));
    api.getRecord().then(setRecord).catch(() => {});
  }, []);

  const toggle = (stat: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(stat) ? next.delete(stat) : next.add(stat);
      return next;
    });

  const games = data?.games ?? [];
  const groups = data?.groups ?? [];
  const q = query.trim().toLowerCase();

  const allProps = groups.flatMap((g) => g.props);
  const pricedCount = allProps.filter((p) => p.engine).length;
  const yesCount = allProps.filter((p) => p.engine?.verdict === "YES").length;
  const gapCount = allProps.filter((p) => p.underdog && p.underdog.ud_delta !== 0).length;

  const groupsView = groups
    .map((group, ogi) => ({
      group,
      ogi,
      props: group.props
        .map((prop, pi) => ({ prop, pi }))
        .filter(
          ({ prop }) =>
            (!selectedGame || prop.game_id === selectedGame) &&
            (!gapsOnly || (prop.underdog != null && prop.underdog.ud_delta !== 0)) &&
            (!picksOnly || prop.engine != null) &&
            (!picksOnly || verdict === "All" || prop.engine?.verdict === verdict) &&
            (!q ||
              prop.player.toLowerCase().includes(q) ||
              (prop.team ?? "").toLowerCase().includes(q)),
        ),
    }))
    .filter(({ props }) => props.length > 0);

  return (
    <div>
      <PageHeader
        title="The Board"
        subtitle="Every prop on your PrizePicks board, all in one place. Picks the engine likes show a verdict, win chance and edge; the rest get a stats-only read. Underdog's line sits on each card, and you can track what you bet."
      />

      {record && !loading && (
        <div className="rise rise-1 mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Bet-worthy" value={yesCount} hint="verdict: YES" />
          <MetricCard label="Engine picks" value={pricedCount} hint="priced, above break-even" />
          <MetricCard
            label="Record"
            value={
              record.settled
                ? `${record.wins}–${record.losses}${record.pushes ? `–${record.pushes}` : ""}`
                : "—"
            }
            hint="wins–losses–pushes"
          />
          <MetricCard
            label="Hit rate"
            value={record.hit_rate != null ? `${record.hit_rate}%` : "—"}
            hint="needs 54.25% to profit"
          />
        </div>
      )}

      <div className="rise rise-1 mb-6 w-full sm:max-w-xs">
        <SearchBox value={query} onChange={setQuery} />
      </div>

      {games.length > 0 && (
        <div className="rise rise-1 mb-6">
          <div className="mb-2 flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-soft">
              Games
            </span>
            {selectedGame && (
              <button
                onClick={() => setSelectedGame(null)}
                className="text-xs font-medium text-ink-faint underline hover:text-ink"
              >
                clear filter
              </button>
            )}
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {games.map((game) => (
              <GameSquare
                key={game.game_id}
                game={game}
                active={selectedGame === game.game_id}
                onClick={() =>
                  setSelectedGame((prev) => (prev === game.game_id ? null : game.game_id))
                }
              />
            ))}
          </div>
        </div>
      )}

      <div className="rise rise-1 mb-6 flex flex-wrap items-center gap-2">
        {pricedCount > 0 && (
          <button
            onClick={() => setPicksOnly((v) => !v)}
            className={`rounded-md border px-3 py-1.5 text-sm font-semibold transition-colors ${
              picksOnly
                ? "border-ink bg-ink text-paper"
                : "border-line-strong bg-card text-ink-soft hover:border-ink hover:text-ink"
            }`}
          >
            Engine picks only
            <span className={`tnum ml-1.5 text-xs ${picksOnly ? "text-paper/70" : "text-ink-faint"}`}>
              {pricedCount}
            </span>
          </button>
        )}
        {gapCount > 0 && (
          <button
            onClick={() => setGapsOnly((v) => !v)}
            className={`rounded-md border px-3 py-1.5 text-sm font-semibold transition-colors ${
              gapsOnly
                ? "border-ink bg-ink text-paper"
                : "border-line-strong bg-card text-ink-soft hover:border-ink hover:text-ink"
            }`}
          >
            Underdog gaps only
            <span className={`tnum ml-1.5 text-xs ${gapsOnly ? "text-paper/70" : "text-ink-faint"}`}>
              {gapCount}
            </span>
          </button>
        )}
        {picksOnly && (
          <div className="inline-flex items-center rounded-md border border-line-strong bg-card p-0.5">
            {VERDICTS.map((v) => {
              const active = verdict === v.value;
              const count =
                v.value === "All"
                  ? pricedCount
                  : allProps.filter((p) => p.engine?.verdict === v.value).length;
              return (
                <button
                  key={v.value}
                  onClick={() => setVerdict(v.value)}
                  className={`rounded px-3 py-1.5 text-sm font-semibold transition-colors ${
                    active ? "bg-ink text-paper" : "text-ink-soft hover:text-ink"
                  }`}
                >
                  {v.label}
                  <span className={`tnum ml-1.5 text-xs ${active ? "text-paper/70" : "text-ink-faint"}`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <p className="rise rise-1 mb-6 text-xs leading-relaxed text-ink-faint">
        Cards with a verdict are the engine's picks (priced against the books / Underdog). Where
        <span className="font-semibold text-ink-soft"> Underdog</span> posts a different line, take
        Over on the lower line, Under on the higher. Stats with no feed (passes, dribbles, fantasy
        score) get a general Claude read only.
      </p>

      {loading ? (
        <EmptyState message="Loading the board..." />
      ) : !groupsView.length ? (
        <EmptyState
          message={
            !groups.length
              ? "No PrizePicks board parsed. Go to Update Data and read your PrizePicks board."
              : q
                ? `No props match “${query}”.`
                : picksOnly
                  ? "No engine picks match these filters."
                  : gapsOnly
                    ? "No Underdog line gaps right now."
                    : "No props for that game. Clear the filter to see the rest of the board."
          }
        />
      ) : (
        <div className="rise rise-2 space-y-3">
          {groupsView.map(({ group, props, ogi }) => {
            const isOpen = open.has(group.stat_type) || gapsOnly || picksOnly || !!q;
            return (
              <div
                key={group.stat_type}
                className="overflow-hidden rounded-lg border border-line bg-card"
              >
                <button
                  onClick={() => toggle(group.stat_type)}
                  className="flex w-full items-center justify-between px-5 py-4 text-left hover:bg-paper"
                >
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-ink">{groupLabel(group)}</span>
                    <span className="tnum text-xs text-ink-faint">{props.length} props</span>
                    {group.has_form_data ? (
                      <Badge variant="info">form data</Badge>
                    ) : (
                      <Badge variant="neutral">no stats yet</Badge>
                    )}
                  </div>
                  <ChevronDown
                    size={16}
                    className={`shrink-0 text-ink-faint transition-transform ${isOpen ? "rotate-180" : ""}`}
                  />
                </button>

                {isOpen && (
                  <div className="grid grid-cols-1 gap-3 border-t border-line p-4 sm:grid-cols-2 lg:grid-cols-3">
                    {props.map(({ prop, pi }) => {
                      const id = ogi * 1000 + pi;
                      const priced = !!prop.engine;
                      return (
                        <PlayerCard
                          key={pi}
                          group={group}
                          prop={prop}
                          id={id}
                          entry={priced ? fullAi.ai[id] : statsAi.ai[id]}
                          onAnalyze={priced ? fullAi.analyze : statsAi.analyze}
                          mode={priced ? "full" : "stats_only"}
                        />
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
