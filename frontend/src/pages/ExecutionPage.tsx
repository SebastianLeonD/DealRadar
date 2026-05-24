import {
  Activity,
  CircleHelp,
  Crosshair,
  Database,
  Info,
  Loader2,
  Terminal,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, type ActionInfo, type FeedsResponse, type PipelineResult } from "../lib/api";
import { Badge, PageHeader } from "../components/ui";

type ActionKey = "fetch_sharp" | "parse_pp" | "run_matcher" | "run_full";

const ACTIONS: { key: ActionKey; label: string; primary?: boolean }[] = [
  { key: "fetch_sharp", label: "Fetch Sharp Lines" },
  { key: "parse_pp", label: "Parse PrizePicks" },
  { key: "run_matcher", label: "Run Edge Detection" },
  { key: "run_full", label: "Run Full Pipeline", primary: true },
];

function HelpModal({
  action,
  onClose,
}: {
  action: ActionInfo;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-xl border border-border bg-surface-card p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-lg font-semibold text-text">{action.title}</h3>
        <pre className="mt-3 overflow-x-auto rounded-lg bg-black/50 p-3 font-mono text-xs text-accent">
          {action.command}
        </pre>
        <p className="mt-4 text-sm leading-relaxed text-text-muted">
          {action.description}
        </p>
        <div className="mt-4 space-y-1 text-sm">
          <p>
            <span className="text-text-dim">API cost:</span>{" "}
            <span className="text-text-muted">{action.api_calls}</span>
          </p>
          <p>
            <span className="text-text-dim">Writes to:</span>{" "}
            <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-xs text-orange-400">
              {action.writes_to}
            </code>
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="mt-6 w-full rounded-lg bg-surface-hover py-2 text-sm font-medium text-text hover:bg-white/10"
        >
          Close
        </button>
      </div>
    </div>
  );
}

function StatusCard({
  label,
  icon: Icon,
  badge,
  variant,
}: {
  label: string;
  icon: typeof Crosshair;
  badge: string;
  variant: "fresh" | "aging" | "stale" | "online";
}) {
  return (
    <div className="rounded-xl border border-border bg-surface-card px-5 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <Icon size={16} className="text-text-dim" />
          <span className="text-sm text-text-muted">{label}</span>
        </div>
        <Badge variant={variant}>{badge}</Badge>
      </div>
    </div>
  );
}

export function ExecutionPage() {
  const [feeds, setFeeds] = useState<FeedsResponse | null>(null);
  const [catalog, setCatalog] = useState<Record<string, ActionInfo>>({});
  const [log, setLog] = useState("Waiting for pipeline execution...");
  const [running, setRunning] = useState<ActionKey | null>(null);
  const [helpKey, setHelpKey] = useState<ActionKey | null>(null);

  const refreshFeeds = useCallback(async () => {
    try {
      setFeeds(await api.getFeeds());
    } catch {
      /* ignore polling errors */
    }
  }, []);

  useEffect(() => {
    refreshFeeds();
    api.getActions().then(setCatalog).catch(() => {});
    const interval = setInterval(refreshFeeds, 30_000);
    return () => clearInterval(interval);
  }, [refreshFeeds]);

  const runAction = async (key: ActionKey) => {
    setRunning(key);
    setLog(`Running ${catalog[key]?.title ?? key}...`);

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
      }
      setLog(result.output);
      await refreshFeeds();
    } catch (err) {
      setLog(err instanceof Error ? err.message : "Pipeline failed.");
    } finally {
      setRunning(null);
    }
  };

  return (
    <div>
      <PageHeader
        title="Execution Pipeline"
        subtitle="Run Arbitrage Engine tasks and monitor data feeds."
      />

      <div className="mb-4 grid grid-cols-3 gap-3">
        <StatusCard
          label="DraftKings Feed"
          icon={Crosshair}
          badge={feeds?.draftkings.label ?? "—"}
          variant={feeds?.draftkings.status ?? "stale"}
        />
        <StatusCard
          label="PrizePicks Feed"
          icon={Activity}
          badge={feeds?.prizepicks.label ?? "—"}
          variant={feeds?.prizepicks.status ?? "stale"}
        />
        <StatusCard
          label="Database"
          icon={Database}
          badge={feeds?.database.label ?? "—"}
          variant={feeds?.database.online ? "online" : "stale"}
        />
      </div>

      {feeds && (
        <p className="mb-4 text-xs text-text-dim">
          {feeds.draftkings.detail} · {feeds.prizepicks.detail}
        </p>
      )}

      <div className="mb-6 flex items-start gap-3 rounded-xl border border-yellow-500/20 bg-yellow-500/5 px-4 py-3">
        <Info size={16} className="mt-0.5 shrink-0 text-yellow-400" />
        <p className="text-sm text-text-muted">
          Edit{" "}
          <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-xs text-orange-400">
            data/raw/prizepicks_raw.json
          </code>{" "}
          in your IDE, then parse from here. Do not paste data directly.
        </p>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-3">
        {ACTIONS.map(({ key, label, primary }) => (
          <div key={key} className="relative">
            <button
              type="button"
              disabled={running !== null}
              onClick={() => runAction(key)}
              className={`flex w-full items-center justify-center rounded-xl border px-4 py-5 text-sm font-semibold transition-all disabled:opacity-50 ${
                primary
                  ? "border-accent/40 bg-accent/10 text-accent hover:bg-accent/15"
                  : "border-border bg-surface-card text-text hover:bg-surface-hover"
              }`}
            >
              {running === key ? (
                <Loader2 size={18} className="animate-spin" />
              ) : (
                label
              )}
            </button>
            <button
              type="button"
              onClick={() => setHelpKey(key)}
              className="absolute right-2 top-2 rounded-md p-1 text-text-dim hover:bg-white/10 hover:text-text-muted"
              title="What does this button do?"
            >
              <CircleHelp size={14} />
            </button>
          </div>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-black">
        <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
          <Terminal size={14} className="text-text-dim" />
          <span className="font-mono text-xs text-text-muted">
            Subprocess Log Output
          </span>
        </div>
        <pre className="max-h-72 overflow-auto p-4 font-mono text-xs leading-relaxed text-text-dim whitespace-pre-wrap">
          {log}
        </pre>
      </div>

      {helpKey && catalog[helpKey] && (
        <HelpModal action={catalog[helpKey]} onClose={() => setHelpKey(null)} />
      )}
    </div>
  );
}
