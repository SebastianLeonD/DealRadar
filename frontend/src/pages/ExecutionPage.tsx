import { CheckCircle2, ChevronDown, Circle, Loader2, Zap } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type FeedsResponse, type PipelineResult } from "../lib/api";
import { PageHeader } from "../components/ui";

type ActionKey = "fetch_sharp" | "parse_pp" | "run_matcher" | "run_full" | "settle_results";

const STEPS: {
  key: ActionKey;
  title: string;
  body: string;
}[] = [
  {
    key: "fetch_sharp",
    title: "Get bookmaker lines",
    body: "Downloads tonight's player lines from DraftKings, FanDuel and others. Costs a few API credits per game.",
  },
  {
    key: "parse_pp",
    title: "Read your PrizePicks board",
    body: "Reads the PrizePicks data you saved into data/raw/prizepicks_raw.json. Paste a fresh copy close to game time.",
  },
  {
    key: "run_matcher",
    title: "Find the picks",
    body: "Compares both sides, calculates win chances, and posts verdicts to Today's Picks. Free.",
  },
  {
    key: "settle_results",
    title: "Grade yesterday (next morning)",
    body: "Looks up final box scores and marks each pick Won or Lost, building your record. Free.",
  },
];

function feedSentence(status?: string, detail?: string): string {
  if (!detail) return "No data yet";
  if (status === "fresh") return `Fresh — ${detail.toLowerCase()}`;
  if (status === "aging") return `Getting old — ${detail.toLowerCase()}`;
  return detail;
}

export function ExecutionPage() {
  const [feeds, setFeeds] = useState<FeedsResponse | null>(null);
  const [log, setLog] = useState("Nothing has run yet this session.");
  const [running, setRunning] = useState<ActionKey | null>(null);
  const [lastDone, setLastDone] = useState<ActionKey | null>(null);

  const refreshFeeds = useCallback(async () => {
    try {
      setFeeds(await api.getFeeds());
    } catch {
      /* ignore polling errors */
    }
  }, []);

  useEffect(() => {
    refreshFeeds();
    const interval = setInterval(refreshFeeds, 30_000);
    return () => clearInterval(interval);
  }, [refreshFeeds]);

  const runAction = async (key: ActionKey) => {
    setRunning(key);
    setLog("Working...");

    let result: PipelineResult;
    try {
      switch (key) {
        case "fetch_sharp":
          result = await api.fetchSharp();
          break;
        case "parse_pp":
          result = await api.parsePp();
          break;
        case "run_matcher":
          result = await api.runMatcher();
          break;
        case "run_full":
          result = await api.runFull();
          break;
        case "settle_results":
          result = await api.settleResults();
          break;
      }
      setLog(result.output);
      setLastDone(key);
      await refreshFeeds();
    } catch (err) {
      setLog(err instanceof Error ? err.message : "Something failed — see details above.");
    } finally {
      setRunning(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Update Data"
        subtitle="Run these steps in order before games start. Or press the big button to do steps 1–3 at once."
        action={
          <button
            type="button"
            disabled={running !== null}
            onClick={() => runAction("run_full")}
            className="inline-flex items-center gap-2 rounded-md bg-ink px-5 py-2.5 text-sm font-semibold text-card transition-opacity hover:opacity-85 disabled:opacity-40"
          >
            {running === "run_full" ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Zap size={16} />
            )}
            Run everything
          </button>
        }
      />

      {/* data freshness, in words */}
      <div className="rise rise-1 mb-8 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg border border-line bg-card px-5 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
            Bookmaker lines
          </p>
          <p className="mt-1 text-sm font-medium text-ink">
            {feedSentence(feeds?.draftkings.status, feeds?.draftkings.detail)}
          </p>
        </div>
        <div className="rounded-lg border border-line bg-card px-5 py-4">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-faint">
            PrizePicks board
          </p>
          <p className="mt-1 text-sm font-medium text-ink">
            {feedSentence(feeds?.prizepicks.status, feeds?.prizepicks.detail)}
          </p>
        </div>
      </div>

      {/* numbered steps */}
      <div className="rise rise-2 overflow-hidden rounded-lg border border-line bg-card">
        {STEPS.map(({ key, title, body }, index) => (
          <div
            key={key}
            className="flex items-center gap-5 border-b border-line px-5 py-5 last:border-b-0"
          >
            <span
              className="tnum w-7 shrink-0 text-2xl font-bold text-ink-faint"
              style={{ fontFamily: "var(--font-display)" }}
            >
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-semibold text-ink">{title}</p>
              <p className="mt-0.5 text-sm leading-relaxed text-ink-soft">{body}</p>
            </div>
            <div className="flex shrink-0 items-center gap-3">
              {lastDone === key ? (
                <CheckCircle2 size={18} className="text-bet" />
              ) : (
                <Circle size={18} className="text-line-strong" />
              )}
              <button
                type="button"
                disabled={running !== null}
                onClick={() => runAction(key)}
                className="rounded-md border border-line-strong bg-card px-4 py-2 text-sm font-semibold text-ink transition-colors hover:border-ink disabled:opacity-40"
              >
                {running === key ? <Loader2 size={15} className="animate-spin" /> : "Run"}
              </button>
            </div>
          </div>
        ))}
      </div>

      <p className="rise rise-3 mt-4 text-xs leading-relaxed text-ink-faint">
        Step 2 needs a fresh PrizePicks capture saved to{" "}
        <code className="rounded bg-line/60 px-1.5 py-0.5 font-mono">
          data/raw/prizepicks_raw.json
        </code>
        {" "}— see the Help tab for exactly how.
      </p>

      {/* output log, tucked away */}
      <details className="rise rise-4 mt-6 overflow-hidden rounded-lg border border-line bg-card">
        <summary className="flex cursor-pointer items-center gap-2 px-5 py-3.5 text-sm font-semibold text-ink-soft hover:text-ink">
          <ChevronDown size={15} />
          What happened last run (details)
        </summary>
        <pre className="max-h-72 overflow-auto border-t border-line bg-paper px-5 py-4 font-mono text-xs leading-relaxed text-ink-soft whitespace-pre-wrap">
          {log}
        </pre>
      </details>
    </div>
  );
}
