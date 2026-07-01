import { AlertTriangle, BookmarkPlus, Check, Sparkles, Wand2 } from "lucide-react";
import { type ReactNode, useState } from "react";
import { api, type Edge, type Slip, type SlipLeg } from "../lib/api";
import { Badge, EmptyState, PageHeader, statLabel, verdictWord, WinBar } from "../components/ui";

const PROVIDERS: { value: "PP" | "UD"; label: string }[] = [
  { value: "PP", label: "PrizePicks" },
  { value: "UD", label: "Underdog" },
];
const METRICS: { value: "ev" | "win"; label: string }[] = [
  { value: "ev", label: "Edge" },
  { value: "win", label: "Win %" },
];
const SIZES = [2, 3, 4, 5, 6];
const PROVIDER_NAME: Record<"PP" | "UD", string> = { PP: "PrizePicks", UD: "Underdog" };

function verdictVariant(v: SlipLeg["verdict"]): "bet" | "maybe" | "skip" | "neutral" {
  if (v === "YES") return "bet";
  if (v === "LEAN") return "maybe";
  if (v === "NO") return "skip";
  return "neutral";
}

/* ---------- track a single leg ---------- */

function TrackLeg({ leg }: { leg: SlipLeg }) {
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");
  const track = async () => {
    setState("saving");
    try {
      const res = await api.trackBet({
        player: leg.player,
        dk_player_name: leg.player,
        team: leg.team,
        opponent: leg.opponent,
        stat_type: leg.stat_type,
        play: leg.side,
        pp_line: leg.pp_line ?? leg.line,
        win_prob: leg.win_prob,
        ev_percent: leg.ev_percent,
        verdict: leg.verdict,
        edge_type: leg.edge_type,
        commence_time: leg.commence_time,
      } as unknown as Edge);
      setState(res.ok ? "done" : "error");
    } catch {
      setState("error");
    }
  };
  const done = state === "done";
  const failed = state === "error";
  return (
    <button
      onClick={track}
      disabled={state === "saving" || done}
      className={`inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-semibold transition-colors ${
        done
          ? "border-bet/40 bg-bet-soft text-bet"
          : failed
            ? "border-skip/40 bg-skip-soft text-skip"
            : "border-line-strong bg-card text-ink-soft hover:border-ink hover:text-ink"
      }`}
    >
      {done ? <Check size={13} /> : <BookmarkPlus size={13} />}
      {done ? "Tracked" : failed ? "Failed — retry" : "Track"}
    </button>
  );
}

/* ---------- one leg of the slip ---------- */

function LegCard({ leg, index }: { leg: SlipLeg; index: number }) {
  const word = leg.side === "OVER" ? "Over" : "Under";
  return (
    <div className="rounded-lg border border-line bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-[11px] text-ink-faint">
            <span className="tnum mr-1.5 font-semibold text-ink">{index + 1}.</span>
            {[leg.team, leg.opponent ? `vs ${leg.opponent}` : null].filter(Boolean).join(" ")}
          </p>
          <p className="truncate text-sm font-semibold leading-tight text-ink">{leg.player}</p>
        </div>
        <Badge variant={verdictVariant(leg.verdict)}>{verdictWord(leg.verdict)}</Badge>
      </div>

      <p className="mt-2 text-sm font-semibold text-ink">
        {word} <span className="tnum">{leg.line}</span> {statLabel(leg.stat_type)}
      </p>

      <div className="mt-2 flex items-center gap-4">
        {leg.win_prob != null && (
          <div>
            <p className="tnum text-sm font-semibold text-ink">{(leg.win_prob * 100).toFixed(1)}%</p>
            <WinBar prob={leg.win_prob} />
            <p className="mt-1 text-[10px] uppercase tracking-wide text-ink-faint">win chance</p>
          </div>
        )}
        {leg.ev_percent != null && (
          <div>
            <p className="tnum text-sm font-semibold text-ink">
              {leg.ev_percent >= 0 ? "+" : ""}
              {leg.ev_percent.toFixed(1)}%
            </p>
            <p className="mt-1 text-[10px] uppercase tracking-wide text-ink-faint">edge</p>
          </div>
        )}
      </div>

      {leg.ai.reasoning && (
        <div className="mt-2 rounded-md border border-line bg-paper px-2.5 py-1.5">
          <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-faint">
            <Sparkles size={11} /> Claude
            {leg.ai.confidence != null && (
              <span className="tnum font-normal normal-case tracking-normal">
                · {leg.ai.confidence}% sure
              </span>
            )}
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-soft">{leg.ai.reasoning}</p>
        </div>
      )}

      <div className="mt-2">
        <TrackLeg leg={leg} />
      </div>
    </div>
  );
}

/* ---------- the slip result ---------- */

function SlipView({ slip }: { slip: Slip }) {
  if (!slip.legs.length) {
    return (
      <EmptyState
        message={
          slip.eligible === 0
            ? "The engine has no qualifying picks right now. Run the matcher on Update Data, then try again."
            : "Claude didn't agree with any of the engine's top picks this time — nothing worth a slip."
        }
      />
    );
  }
  const metricWord = slip.metric === "ev" ? "edge" : "win chance";
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold text-ink">
          {slip.legs.length}-leg {PROVIDER_NAME[slip.provider]} slip
        </span>
        <span className="text-ink-faint">· ranked by {metricWord} · engine + Claude agree</span>
        {slip.valid && (
          <span className="inline-flex items-center gap-1 text-bet">
            <Check size={13} /> valid lineup
          </span>
        )}
      </div>

      {slip.short && (
        <div className="flex items-start gap-1.5 rounded-md border border-maybe/25 bg-maybe-soft px-3 py-2">
          <AlertTriangle size={13} className="mt-0.5 shrink-0 text-maybe" />
          <p className="text-[12px] leading-relaxed text-maybe">
            You asked for {slip.requested}, but only {slip.agreed} pick
            {slip.agreed === 1 ? "" : "s"} cleared both the engine and Claude. No padding — a thin
            leg only drags a slip down.
          </p>
        </div>
      )}

      {slip.legs.length >= 2 && !slip.valid && (
        <div className="flex items-start gap-1.5 rounded-md border border-skip/30 bg-skip-soft px-3 py-2">
          <AlertTriangle size={13} className="mt-0.5 shrink-0 text-skip" />
          <p className="text-[12px] leading-relaxed text-skip">
            Heads up: these legs are all from one team. PrizePicks needs at least two
            different teams in a lineup — add a leg from another team before submitting.
          </p>
        </div>
      )}

      {slip.correlations.length > 0 && (
        <div className="flex items-start gap-1.5 rounded-md border border-line-strong bg-paper px-3 py-2">
          <AlertTriangle size={13} className="mt-0.5 shrink-0 text-ink-soft" />
          <p className="text-[12px] leading-relaxed text-ink-soft">
            Same-game legs (their outcomes move together, which concentrates risk on a parlay):{" "}
            {slip.correlations
              .map((c) => `${c.players.join(" + ")} in ${c.game}`)
              .join("; ")}
            .
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {slip.legs.map((leg, i) => (
          <LegCard key={`${leg.player}-${leg.stat_type}-${i}`} leg={leg} index={i} />
        ))}
      </div>

      <p className="text-xs text-ink-faint">
        From {slip.eligible} engine pick{slip.eligible === 1 ? "" : "s"}, Claude reviewed the top{" "}
        {slip.considered} and backed {slip.agreed}.
      </p>
    </div>
  );
}

export function SlipBuilderPage() {
  const [n, setN] = useState(3);
  const [provider, setProvider] = useState<"PP" | "UD">("PP");
  const [metric, setMetric] = useState<"ev" | "win">("ev");
  const [loading, setLoading] = useState(false);
  const [slip, setSlip] = useState<Slip | null>(null);
  const [error, setError] = useState<string | null>(null);

  const build = async () => {
    setLoading(true);
    setError(null);
    setSlip(null);
    try {
      const res = await api.buildSlip(n, provider, metric);
      if (res.ok) setSlip(res.slip);
      else setError(res.error || "Couldn't build a slip.");
    } catch {
      setError("Couldn't reach the engine. Is the API running on :8800?");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="Build a Slip"
        subtitle="Pick how many legs and where you're betting. The engine ranks its best picks; Claude reviews the top ones and only legs they both back make the slip — never padded to hit your number. Every slip is a valid PrizePicks lineup: one leg per player, at least two teams, no combos."
      />

      <div className="rise rise-1 mb-6 space-y-4 rounded-lg border border-line bg-card p-4">
        <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
          <Control label="Legs">
            <div className="inline-flex items-center rounded-md border border-line-strong bg-paper p-0.5">
              {SIZES.map((s) => (
                <Pill key={s} active={n === s} onClick={() => setN(s)}>
                  {s}
                </Pill>
              ))}
            </div>
          </Control>
          <Control label="Betting on">
            <div className="inline-flex items-center rounded-md border border-line-strong bg-paper p-0.5">
              {PROVIDERS.map((p) => (
                <Pill key={p.value} active={provider === p.value} onClick={() => setProvider(p.value)}>
                  {p.label}
                </Pill>
              ))}
            </div>
          </Control>
          <Control label="Rank by">
            <div className="inline-flex items-center rounded-md border border-line-strong bg-paper p-0.5">
              {METRICS.map((m) => (
                <Pill key={m.value} active={metric === m.value} onClick={() => setMetric(m.value)}>
                  {m.label}
                </Pill>
              ))}
            </div>
          </Control>
        </div>

        <button
          onClick={build}
          disabled={loading}
          className="inline-flex items-center gap-2 rounded-md border-2 border-ink bg-ink px-4 py-2 text-sm font-semibold text-paper transition-opacity hover:opacity-90 disabled:opacity-60"
        >
          <Wand2 size={15} />
          {loading ? "Claude is reviewing the board…" : `Build my ${n}-leg slip`}
        </button>
      </div>

      {error && (
        <div className="rise rise-1 mb-6 flex items-start gap-2 rounded-md border border-skip/30 bg-skip-soft px-3 py-2.5">
          <AlertTriangle size={14} className="mt-0.5 shrink-0 text-skip" />
          <p className="text-sm text-skip">{error}</p>
        </div>
      )}

      <div className="rise rise-2">
        {loading ? (
          <EmptyState message="Engine ranked its picks — Claude is vetting them one by one. This takes a few seconds." />
        ) : slip ? (
          <SlipView slip={slip} />
        ) : (
          !error && (
            <EmptyState message="Set your legs and provider, then build a slip. Each leg is double-checked by Claude before it makes the cut." />
          )
        )}
      </div>
    </div>
  );
}

function Control({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
        {label}
      </p>
      {children}
    </div>
  );
}

function Pill({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`tnum rounded px-3 py-1.5 text-sm font-semibold transition-colors ${
        active ? "bg-ink text-paper" : "text-ink-soft hover:text-ink"
      }`}
    >
      {children}
    </button>
  );
}
