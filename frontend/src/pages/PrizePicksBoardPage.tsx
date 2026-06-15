import { ChevronDown, Swords } from "lucide-react";
import { useEffect, useState } from "react";
import {
  api,
  type Edge,
  type PpBoardGame,
  type PpBoardGroup,
  type PpBoardProp,
  type PpBoardResponse,
  type PpUnderdog,
} from "../lib/api";
import { Badge, EmptyState, PageHeader, SearchBox, statLabel } from "../components/ui";
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

const APP_NAME: Record<PpUnderdog["over_app"], string> = {
  UD: "Underdog",
  PP: "PrizePicks",
  EVEN: "either",
};

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

      {prop.underdog && <UnderdogStrip ud={prop.underdog} />}

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
  const [gapsOnly, setGapsOnly] = useState(false);
  const [query, setQuery] = useState("");
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
  const gapCount = groups.reduce(
    (n, g) => n + g.props.filter((p) => p.underdog && p.underdog.ud_delta !== 0).length,
    0,
  );

  const q = query.trim().toLowerCase();
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
            (!q ||
              prop.player.toLowerCase().includes(q) ||
              (prop.team ?? "").toLowerCase().includes(q)),
        ),
    }))
    .filter(({ props }) => props.length > 0);

  return (
    <div>
      <PageHeader
        title="PrizePicks Board"
        subtitle="Every prop on your pasted PrizePicks board, including stats no sportsbook offers. Pick a game up top, then ask Claude for a stats-only read on any player — no bookmaker data, just the player's form and the matchup."
      />

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

      <div className="rise rise-1 mb-6 flex flex-wrap items-center gap-3">
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
        <p className="text-xs leading-relaxed text-ink-faint">
          Where <span className="font-semibold text-ink-soft">Underdog</span> posts a different
          line, take Over on the lower line, Under on the higher — even a 0.5 gap settles
          differently (PrizePicks whole-number lines push on a tie; Underdog half-lines don't).
        </p>
      </div>

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
            !groups.length
              ? "No PrizePicks board parsed. Go to Update Data and read your PrizePicks board."
              : q
                ? `No props match “${query}”.`
                : gapsOnly
                  ? "No Underdog line gaps right now. Turn off the filter to see the full board."
                  : "No props for that game. Clear the filter to see the rest of the board."
          }
        />
      ) : (
        <div className="rise rise-2 space-y-3">
          {groupsView.map(({ group, props, ogi }) => {
            const isOpen = open.has(group.stat_type) || gapsOnly || !!q;
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
