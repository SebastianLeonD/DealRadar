import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Edge, type PpBoardGroup, type PpBoardResponse } from "../lib/api";
import { Badge, EmptyState, PageHeader, statLabel } from "../components/ui";
import { AiResult, PromptBox, useAiAnalysis } from "../components/ai";

/** Build an Edge-shaped object for the stats-only AI call. For mapped stats we
 *  send the engine key (so the analyst finds the player's form); for unmapped
 *  ones we send the raw PrizePicks name so it at least knows the stat. */
function toEdge(group: PpBoardGroup, prop: PpBoardGroup["props"][number], id: number): Edge {
  return {
    id,
    player: prop.player,
    dk_player_name: prop.player,
    team: prop.team ?? "",
    stat_type: group.mapped_stat ?? group.stat_type,
    pp_line: prop.line,
  } as unknown as Edge;
}

function groupLabel(group: PpBoardGroup): string {
  return group.mapped_stat ? statLabel(group.mapped_stat) : group.stat_type;
}

export function PrizePicksBoardPage() {
  const [data, setData] = useState<PpBoardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const { ai, analyze } = useAiAnalysis("stats_only");

  useEffect(() => {
    api
      .getPrizePicksBoard()
      .then(setData)
      .catch(() => setData({ total: 0, groups: [] }))
      .finally(() => setLoading(false));
  }, []);

  const toggle = (stat: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(stat) ? next.delete(stat) : next.add(stat);
      return next;
    });

  const groups = data?.groups ?? [];

  return (
    <div>
      <PageHeader
        title="PrizePicks Board"
        subtitle="Every prop on your pasted PrizePicks board, including stats no sportsbook offers. Ask Claude for a stats-only read on any of them — no bookmaker data, just the player's form and the matchup."
      />

      <p className="rise rise-1 mb-6 text-xs leading-relaxed text-ink-faint">
        The <span className="font-semibold text-ink-soft">form data</span> tag means we have
        this player's tournament numbers for that stat, so Claude reasons from real rates.
        Stats marked <span className="font-semibold text-ink-soft">no stats yet</span> (passes,
        dribbles, fantasy score, clearances) have no feed — Claude can only give a general read.
      </p>

      {loading ? (
        <EmptyState message="Loading the PrizePicks board..." />
      ) : !groups.length ? (
        <EmptyState message="No PrizePicks board parsed. Go to Update Data and read your PrizePicks board." />
      ) : (
        <div className="rise rise-2 space-y-3">
          {groups.map((group, gi) => {
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
                    <span className="tnum text-xs text-ink-faint">{group.count} props</span>
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
                  <div className="border-t border-line">
                    {group.props.map((prop, pi) => {
                      const edge = toEdge(group, prop, gi * 1000 + pi);
                      return (
                        <div key={pi} className="border-b border-line px-5 py-4 last:border-b-0">
                          <div className="flex items-baseline justify-between gap-3">
                            <div className="min-w-0">
                              <p className="truncate font-semibold text-ink">{prop.player}</p>
                              <p className="truncate text-xs text-ink-faint">{prop.team}</p>
                            </div>
                            <p className="shrink-0 text-sm font-semibold text-ink">
                              <span className="tnum">{prop.line}</span> {groupLabel(group)}
                            </p>
                          </div>
                          <div className="mt-2">
                            <AiResult edge={edge} entry={ai[edge.id]} onAnalyze={analyze} />
                            <PromptBox edge={edge} mode="stats_only" />
                          </div>
                        </div>
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
