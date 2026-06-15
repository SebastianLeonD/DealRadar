import { ChevronDown, Swords } from "lucide-react";
import { useEffect, useState } from "react";
import {
  api,
  type Edge,
  type PpBoardGame,
  type PpBoardGroup,
  type PpBoardProp,
  type PpBoardResponse,
} from "../lib/api";
import { Badge, EmptyState, PageHeader, statLabel } from "../components/ui";
import { AiResult, PromptBox, useAiAnalysis } from "../components/ai";

/** Build an Edge-shaped object for the stats-only AI call. For mapped stats we
 *  send the engine key (so the analyst finds the player's form); for unmapped
 *  ones we send the raw PrizePicks name so it at least knows the stat. */
function toEdge(group: PpBoardGroup, prop: PpBoardProp, id: number): Edge {
  return {
    id,
    player: prop.player,
    dk_player_name: prop.player,
    team: prop.team ?? "",
    opponent: prop.opponent ?? null,
    stat_type: group.mapped_stat ?? group.stat_type,
    pp_line: prop.line,
  } as unknown as Edge;
}

function groupLabel(group: PpBoardGroup): string {
  return group.mapped_stat ? statLabel(group.mapped_stat) : group.stat_type;
}

function kickoff(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString([], {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
  });
}

/* ---------- a matchup square at the top of the board ---------- */

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
        active
          ? "border-ink bg-ink text-paper"
          : "border-line bg-card hover:border-line-strong"
      }`}
    >
      <div className="flex items-center gap-1.5 text-sm font-semibold leading-tight">
        <span className="truncate">{game.away}</span>
        <Swords size={11} className="shrink-0 opacity-60" />
        <span className="truncate">{game.home}</span>
      </div>
      <div
        className={`flex items-center gap-2 text-[11px] ${
          active ? "text-paper/70" : "text-ink-faint"
        }`}
      >
        <span>{live ? "Live now" : kickoff(game.start_time)}</span>
        <span className="tnum">· {game.count} props</span>
      </div>
    </button>
  );
}

/* ---------- a single prop, in a PrizePicks-style box ---------- */

function PlayerCard({
  group,
  prop,
  id,
  ai,
  analyze,
}: {
  group: PpBoardGroup;
  prop: PpBoardProp;
  id: number;
  ai: ReturnType<typeof useAiAnalysis>["ai"];
  analyze: ReturnType<typeof useAiAnalysis>["analyze"];
}) {
  const edge = toEdge(group, prop, id);
  return (
    <div className="flex flex-col rounded-lg border border-line bg-card p-3">
      <div className="flex items-start gap-2.5">
        {prop.image_url ? (
          <img
            src={prop.image_url}
            alt=""
            loading="lazy"
            className="h-11 w-11 shrink-0 rounded-full bg-paper object-cover"
            onError={(e) => (e.currentTarget.style.display = "none")}
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
      </div>

      <div className="mt-2.5 flex items-baseline gap-1.5 border-t border-line pt-2.5">
        <span className="tnum text-lg font-semibold text-ink">{prop.line}</span>
        <span className="text-xs text-ink-soft">{groupLabel(group)}</span>
      </div>

      <div className="mt-2">
        <AiResult edge={edge} entry={ai[edge.id]} onAnalyze={analyze} />
        <PromptBox edge={edge} mode="stats_only" />
      </div>
    </div>
  );
}

export function PrizePicksBoardPage() {
  const [data, setData] = useState<PpBoardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [selectedGame, setSelectedGame] = useState<string | null>(null);
  const { ai, analyze } = useAiAnalysis("stats_only");

  useEffect(() => {
    api
      .getPrizePicksBoard()
      .then(setData)
      .catch(() => setData({ total: 0, groups: [], games: [] }))
      .finally(() => setLoading(false));
  }, []);

  const toggle = (stat: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(stat) ? next.delete(stat) : next.add(stat);
      return next;
    });

  const games = data?.games ?? [];
  const groups = data?.groups ?? [];

  // Keep original prop indices stable for the AI map even when a game is picked.
  const groupsView = groups
    .map((group, ogi) => ({
      group,
      ogi,
      props: group.props
        .map((prop, pi) => ({ prop, pi }))
        .filter(({ prop }) => !selectedGame || prop.game_id === selectedGame),
    }))
    .filter(({ props }) => props.length > 0);

  return (
    <div>
      <PageHeader
        title="PrizePicks Board"
        subtitle="Every prop on your pasted PrizePicks board, including stats no sportsbook offers. Pick a game up top, then ask Claude for a stats-only read on any player — no bookmaker data, just the player's form and the matchup."
      />

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

      <p className="rise rise-1 mb-6 text-xs leading-relaxed text-ink-faint">
        The <span className="font-semibold text-ink-soft">form data</span> tag means we have
        this player's tournament numbers for that stat, so Claude reasons from real rates.
        Stats marked <span className="font-semibold text-ink-soft">no stats yet</span> (passes,
        dribbles, fantasy score, clearances) have no feed — Claude can only give a general read.
      </p>

      {loading ? (
        <EmptyState message="Loading the PrizePicks board..." />
      ) : !groupsView.length ? (
        <EmptyState
          message={
            groups.length
              ? "No props for that game. Clear the filter to see the rest of the board."
              : "No PrizePicks board parsed. Go to Update Data and read your PrizePicks board."
          }
        />
      ) : (
        <div className="rise rise-2 space-y-3">
          {groupsView.map(({ group, props, ogi }) => {
            const isOpen = open.has(group.stat_type);
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
                    {props.map(({ prop, pi }) => (
                      <PlayerCard
                        key={pi}
                        group={group}
                        prop={prop}
                        id={ogi * 1000 + pi}
                        ai={ai}
                        analyze={analyze}
                      />
                    ))}
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
