import { ChevronDown, Eye, Loader2, Sparkles } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type AiRecommendation, type AnalysisMode, type Edge, type SentToAi } from "../lib/api";
import { Badge } from "./ui";

export type AiEntry = {
  status: "loading" | "done" | "error";
  rec?: AiRecommendation;
  error?: string;
  opponent?: string | null;
};

/** Shared AI state + analyze callback, parameterised by analysis mode. */
export function useAiAnalysis(mode: AnalysisMode) {
  const [ai, setAi] = useState<Record<number, AiEntry>>({});

  const analyze = useCallback(
    async (edge: Edge) => {
      setAi((prev) => ({ ...prev, [edge.id]: { status: "loading" } }));
      try {
        const res = await api.analyzeEdge(edge, mode);
        if (res.ok && res.recommendation) {
          setAi((prev) => ({
            ...prev,
            [edge.id]: { status: "done", rec: res.recommendation, opponent: res.opponent },
          }));
        } else {
          setAi((prev) => ({
            ...prev,
            [edge.id]: { status: "error", error: res.error ?? "Analysis failed." },
          }));
        }
      } catch {
        setAi((prev) => ({
          ...prev,
          [edge.id]: { status: "error", error: "Could not reach the analyst." },
        }));
      }
    },
    [mode],
  );

  return { ai, analyze };
}

/* ---------- transparency: exactly what we send Claude ---------- */

export function PromptBox({ edge, mode }: { edge: Edge; mode: AnalysisMode }) {
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState<SentToAi | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSent(null);
  }, [mode]);

  const toggle = useCallback(async () => {
    const next = !open;
    setOpen(next);
    if (next && !sent && !loading) {
      setLoading(true);
      setError(null);
      try {
        const res = await api.previewPrompt(edge, mode);
        if (res.ok) setSent(res.sent);
        else setError("Couldn't load the prompt.");
      } catch {
        setError("Couldn't load the prompt.");
      } finally {
        setLoading(false);
      }
    }
  }, [open, sent, loading, edge, mode]);

  return (
    <div className="mt-2">
      <button
        onClick={toggle}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-ink-faint hover:text-ink"
      >
        <Eye size={12} />
        What Claude sees
        <ChevronDown size={12} className={`transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div className="mt-2 space-y-3">
          {loading && (
            <p className="flex items-center gap-2 text-xs text-ink-faint">
              <Loader2 size={12} className="animate-spin" /> Loading…
            </p>
          )}
          {error && <p className="text-xs text-skip">{error}</p>}
          {sent && (
            <>
              <div>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-faint">
                  This play (the facts we hand it)
                </p>
                <pre className="max-h-60 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-card px-3 py-2 text-[11px] leading-relaxed text-ink-soft">
                  {sent.prompt}
                </pre>
              </div>
              <div>
                <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-faint">
                  Its instructions (how we ask it to think)
                </p>
                <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-card px-3 py-2 text-[11px] leading-relaxed text-ink-faint">
                  {sent.system}
                </pre>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ---------- the AI verdict, shown in full ---------- */

export function AiVerdict({ rec, edge }: { rec: AiRecommendation; edge?: Edge }) {
  const twoBooks =
    rec.underdog_pick != null &&
    edge?.ud_line != null &&
    edge.ud_line !== edge.pp_line;
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {twoBooks ? (
          <>
            <Badge variant={rec.pick === "PASS" ? "skip" : "bet"}>
              PrizePicks: {rec.pick} {edge!.pp_line}
            </Badge>
            <Badge variant={rec.underdog_pick === "PASS" ? "skip" : "bet"}>
              Underdog: {rec.underdog_pick} {edge!.ud_line}
            </Badge>
          </>
        ) : (
          <Badge variant={rec.pick === "PASS" ? "skip" : "bet"}>AI: {rec.pick}</Badge>
        )}
        <span className="tnum text-xs text-ink-faint">{rec.confidence}% confident</span>
        <Badge variant={rec.agrees_with_engine ? "info" : "maybe"}>
          {rec.agrees_with_engine ? "agrees with engine" : "differs from engine"}
        </Badge>
      </div>
      <p className="text-sm leading-relaxed text-ink-soft">{rec.reasoning}</p>
      {rec.key_factors.length > 0 && (
        <ul className="mt-2 space-y-1">
          {rec.key_factors.map((factor, i) => (
            <li key={i} className="flex gap-2 text-xs text-ink-faint">
              <span>•</span>
              <span>{factor}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The AI block: nothing runs until the user asks. */
export function AiResult({
  edge,
  entry,
  onAnalyze,
}: {
  edge: Edge;
  entry: AiEntry | undefined;
  onAnalyze: (edge: Edge) => void;
}) {
  if (!entry) {
    return (
      <button
        onClick={() => onAnalyze(edge)}
        className="inline-flex items-center gap-1.5 rounded-md border border-line-strong bg-card px-3 py-1.5 text-xs font-semibold text-ink-soft transition-colors hover:border-ink hover:text-ink"
      >
        <Sparkles size={13} />
        Ask Claude
      </button>
    );
  }
  if (entry.status === "loading") {
    return (
      <div className="flex items-center gap-2 text-sm text-ink-faint">
        <Loader2 size={14} className="animate-spin" />
        {edge.opponent ? `Reading the matchup vs ${edge.opponent}…` : "Asking Claude…"}
      </div>
    );
  }
  if (entry.status === "error") {
    return (
      <p className="text-sm text-skip">
        {entry.error}{" "}
        <button onClick={() => onAnalyze(edge)} className="underline hover:text-ink">
          retry
        </button>
      </p>
    );
  }
  return (
    <div>
      <AiVerdict rec={entry.rec!} edge={edge} />
      <button
        onClick={() => onAnalyze(edge)}
        className="mt-2 text-[11px] text-ink-faint underline hover:text-ink"
      >
        re-analyze
      </button>
    </div>
  );
}
