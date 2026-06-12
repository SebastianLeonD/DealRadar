export type Page = "execution" | "opportunities" | "clv" | "help";

export interface FeedStatus {
  status: "fresh" | "aging" | "stale";
  label: string;
  detail: string;
}

export interface FeedsResponse {
  draftkings: FeedStatus;
  prizepicks: FeedStatus;
  database: { online: boolean; label: string };
  pp_raw_exists: boolean;
}

export interface Edge {
  id: number;
  flagged_at: string;
  player: string;
  dk_player_name: string;
  team: string;
  stat_type: string;
  play: "OVER" | "UNDER";
  pp_line: number;
  dk_line: number;
  edge_type: "Line Discrepancy" | "+EV Odds Juice" | "Duration Model" | string;
  probability_text: string;
  dk_over_prob: number;
  dk_under_prob: number;
  win_prob: number | null;
  ev_percent: number | null;
  verdict: "YES" | "LEAN" | "NO" | null;
  flags: string | null;
  book_count: number | null;
  result: "WIN" | "LOSS" | "PUSH" | null;
  actual_value: number | null;
}

export interface EdgesResponse {
  edges: Edge[];
  summary: {
    unique: number;
    line_discrepancy: number;
    ev_juice: number;
    yes_count: number;
    stats: string[];
  };
}

export interface RecordSummary {
  settled: number;
  wins: number;
  losses: number;
  pushes: number;
  hit_rate: number | null;
  avg_predicted_prob: number | null;
  by_verdict: Record<string, { wins: number; losses: number; pushes: number }>;
}

export interface ClvRow {
  flagged_at: string;
  player: string;
  pp_player_name: string;
  play: "OVER" | "UNDER";
  original_line: number;
  dk_line_at_flag: number;
  dk_line_now: number;
  movement: number;
  clv: number;
  clv_status: "Positive" | "Neutral" | "Negative";
  edge_type: string;
  team: string;
}

export interface ClvResponse {
  rows: ClvRow[];
  summary: {
    unique: number;
    positive_rate: number;
    positive_count: number;
    avg_clv: number;
  };
  daily: { date: string; avg_clv: number; edge_count: number }[];
}

export interface PipelineResult {
  success: boolean;
  output: string;
  edges_found?: number;
}

export interface ActionInfo {
  title: string;
  command: string;
  description: string;
  api_calls: string;
  writes_to: string;
}

const BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8800/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, init);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export const api = {
  getFeeds: () => request<FeedsResponse>("/status/feeds"),
  getActions: () => request<Record<string, ActionInfo>>("/actions"),
  fetchSharp: () =>
    request<PipelineResult>("/pipeline/fetch-sharp", { method: "POST" }),
  parsePp: () =>
    request<PipelineResult>("/pipeline/parse-pp", { method: "POST" }),
  runMatcher: () =>
    request<PipelineResult>("/pipeline/run-matcher", { method: "POST" }),
  runFull: () =>
    request<PipelineResult>("/pipeline/full", { method: "POST" }),
  settleResults: () =>
    request<PipelineResult>("/pipeline/settle", { method: "POST" }),
  getRecord: () => request<RecordSummary>("/record"),
  getEdges: (stat: string, edgeType: string) =>
    request<EdgesResponse>(
      `/edges?stat=${encodeURIComponent(stat)}&edge_type=${encodeURIComponent(edgeType)}`,
    ),
  getClv: (refresh = false) =>
    request<ClvResponse>(`/clv?refresh=${refresh}`),
  refreshClv: () =>
    request<ClvResponse>("/clv/refresh", { method: "POST" }),
  exportEdgesUrl: (stat: string, edgeType: string) =>
    `${BASE}/edges/export?stat=${encodeURIComponent(stat)}&edge_type=${encodeURIComponent(edgeType)}`,
};
