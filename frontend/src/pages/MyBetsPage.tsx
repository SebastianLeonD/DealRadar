import { CheckCircle2, Loader2, Swords, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type Bet, type BetsResponse } from "../lib/api";
import { Badge, EmptyState, ET_TZ, MetricCard, PageHeader, SearchBox, statLabel } from "../components/ui";

function kickoff(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const when = date.toLocaleString("en-US", {
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: ET_TZ,
  });
  return `${when} ET`;
}

function resultVariant(result: Bet["result"]): "bet" | "skip" | "neutral" {
  if (result === "WIN") return "bet";
  if (result === "LOSS") return "skip";
  return "neutral";
}

/** Hit rate per engine verdict — does "YES" actually beat "MAYBE" on your bets? */
function verdictHitRates(summary: BetsResponse["summary"]) {
  return Object.entries(summary.by_verdict)
    .map(([verdict, b]) => {
      const decided = b.wins + b.losses;
      return {
        verdict,
        decided,
        wins: b.wins,
        rate: decided ? Math.round((b.wins / decided) * 100) : null,
      };
    })
    .filter((v) => v.decided > 0)
    .sort((a, b) => a.verdict.localeCompare(b.verdict));
}

function BetRow({ bet, onRemove }: { bet: Bet; onRemove: (id: number) => void }) {
  const settled = bet.result != null;
  return (
    <div className="flex items-center gap-4 border-b border-line px-4 py-3.5 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold text-ink">{bet.pp_player_name}</p>
        <p className="flex items-center gap-1.5 truncate text-xs text-ink-faint">
          <span className="truncate">{bet.team}</span>
          {bet.opponent && (
            <>
              <Swords size={11} className="shrink-0" />
              <span className="truncate">{bet.opponent}</span>
            </>
          )}
        </p>
      </div>

      <div className="hidden min-w-0 flex-1 sm:block">
        <p className="text-sm font-semibold text-ink">
          {bet.play === "OVER" ? "Over" : "Under"} <span className="tnum">{bet.pp_line}</span>{" "}
          {statLabel(bet.stat_type)}
        </p>
        <p className="text-xs text-ink-faint">
          {settled ? (
            <>actual {bet.actual_value}</>
          ) : (
            kickoff(bet.commence_time) || "upcoming"
          )}
          {bet.stake ? <> · ${bet.stake}</> : null}
        </p>
      </div>

      <div className="shrink-0">
        {settled ? (
          <Badge variant={resultVariant(bet.result)}>{bet.result}</Badge>
        ) : (
          <Badge variant="neutral">open</Badge>
        )}
      </div>

      <button
        onClick={() => onRemove(bet.id)}
        title="Remove from My Bets"
        className="shrink-0 rounded-md p-1.5 text-ink-faint transition-colors hover:bg-paper hover:text-skip"
      >
        <Trash2 size={15} />
      </button>
    </div>
  );
}

export function MyBetsPage() {
  const [data, setData] = useState<BetsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [settling, setSettling] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await api.getBets());
    } catch {
      setData({
        bets: [],
        summary: {
          total: 0, settled: 0, wins: 0, losses: 0, pushes: 0,
          hit_rate: null, total_staked: 0, by_verdict: {},
        },
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const settle = async () => {
    setSettling(true);
    setNote(null);
    try {
      const res = await api.settleBets();
      setNote(`Settled ${res.settled} bet(s).`);
      await load();
    } catch {
      setNote("Couldn't reach the settler.");
    } finally {
      setSettling(false);
    }
  };

  const remove = async (id: number) => {
    await api.removeBet(id);
    await load();
  };

  const summary = data?.summary;
  const q = query.trim().toLowerCase();
  const bets = (data?.bets ?? []).filter(
    (b) =>
      !q ||
      b.pp_player_name.toLowerCase().includes(q) ||
      (b.team ?? "").toLowerCase().includes(q) ||
      statLabel(b.stat_type).toLowerCase().includes(q),
  );
  const open = bets.filter((b) => b.result == null);
  const settled = bets.filter((b) => b.result != null);
  const totalOpen = summary ? summary.total - summary.settled : 0;
  const rates = summary ? verdictHitRates(summary) : [];

  return (
    <div>
      <PageHeader
        title="My Bets"
        subtitle="The picks you actually placed. Track a bet from any pick, then settle to see your real record — and whether the engine's YES calls hit more than its MAYBEs."
        action={
          <button
            onClick={settle}
            disabled={settling || !totalOpen}
            className="inline-flex items-center gap-2 rounded-md border border-line-strong bg-card px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-ink disabled:opacity-40"
          >
            {settling ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
            Settle results
          </button>
        }
      />

      {summary && !loading && (
        <div className="rise rise-1 mb-8 grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricCard label="Bets tracked" value={summary.total} hint={`${totalOpen} still open`} />
          <MetricCard label="Settled" value={summary.settled} hint="graded vs box scores" />
          <MetricCard
            label="Record"
            value={
              summary.settled
                ? `${summary.wins}–${summary.losses}${summary.pushes ? `–${summary.pushes}` : ""}`
                : "—"
            }
            hint="wins–losses–pushes"
          />
          <MetricCard
            label="Hit rate"
            value={summary.hit_rate != null ? `${summary.hit_rate}%` : "—"}
            hint="needs 54.25% to profit"
          />
        </div>
      )}

      {rates.length > 0 && (
        <div className="rise rise-2 mb-8 rounded-lg border border-line bg-card px-5 py-4">
          <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
            Hit rate by the engine's verdict
          </p>
          <div className="flex flex-wrap gap-6">
            {rates.map((r) => (
              <div key={r.verdict}>
                <p className="text-sm font-semibold text-ink">
                  {r.verdict}{" "}
                  <span className="tnum text-ink-faint">{r.rate}%</span>
                </p>
                <p className="tnum text-xs text-ink-faint">
                  {r.wins}/{r.decided} hit
                </p>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-ink-faint">
            This is the real trust test: if YES beats MAYBE here over time, the engine's
            confidence is earning its keep.
          </p>
        </div>
      )}

      {note && <p className="rise mb-4 text-sm text-ink-soft">{note}</p>}

      {(data?.bets.length ?? 0) > 0 && (
        <div className="rise mb-4 w-full sm:max-w-xs">
          <SearchBox value={query} onChange={setQuery} />
        </div>
      )}

      {loading ? (
        <EmptyState message="Loading your bets..." />
      ) : !bets.length ? (
        <EmptyState
          message={
            q
              ? `No bets match “${query}”.`
              : "No bets tracked yet. Hit “Track bet” on any pick to log it here."
          }
        />
      ) : (
        <div className="rise rise-3 space-y-8">
          {open.length > 0 && (
            <section>
              <h2 className="mb-3 text-lg font-semibold text-ink" style={{ fontFamily: "var(--font-display)" }}>
                Open ({open.length})
              </h2>
              <div className="overflow-hidden rounded-lg border border-line bg-card">
                {open.map((bet) => (
                  <BetRow key={bet.id} bet={bet} onRemove={remove} />
                ))}
              </div>
            </section>
          )}

          {settled.length > 0 && (
            <section>
              <h2 className="mb-3 text-lg font-semibold text-ink" style={{ fontFamily: "var(--font-display)" }}>
                Settled ({settled.length})
              </h2>
              <div className="overflow-hidden rounded-lg border border-line bg-card">
                {settled.map((bet) => (
                  <BetRow key={bet.id} bet={bet} onRemove={remove} />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
