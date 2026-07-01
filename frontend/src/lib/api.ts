export type Page = "execution" | "prizepicks" | "slip" | "bets" | "clv" | "help";

/** "full" weighs the sharp books; "stats_only" is a PrizePicks-only, form-based read. */
export type AnalysisMode = "full" | "stats_only";

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

export interface EdgeUnderdog {
  ud_line: number;
  ud_delta: number;
  best_app: "UD" | "PP" | "EVEN";
  bet_on_underdog: boolean;
  play_price: string | null;
  play_multiplier: number | null;
  ud_matched_name: string;
}

export interface Edge {
  id: number;
  flagged_at: string;
  player: string;
  dk_player_name: string;
  team: string;
  opponent?: string | null;
  game?: string | null;
  commence_time?: string | null;
  stat_type: string;
  play: "OVER" | "UNDER";
  pp_line: number;
  dk_line: number;
  ud_line?: number | null;
  edge_type: "Line Discrepancy" | "+EV Odds Juice" | "Duration Model" | string;
  probability_text: string;
  dk_over_prob: number;
  dk_under_prob: number;
  win_prob: number | null;
  ev_percent: number | null;
  verdict: "YES" | "LEAN" | "NO" | null;
  flags: string | null;
  book_count: number | null;
  result: "WIN" | "LOSS" | "PUSH" | "VOID" | null;
  actual_value: number | null;
  underdog?: EdgeUnderdog | null;
  model_p?: number | null;
  model_p_side?: number | null;
  model_credibility?: number | null;
  consensus_n?: number | null;
  consensus_tag?: "identified" | "single_book" | "degraded" | string | null;
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
  voids: number;
  hit_rate: number | null;
  avg_predicted_prob: number | null;
  by_verdict: Record<string, { wins: number; losses: number; pushes: number; voids: number }>;
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

export interface AiRecommendation {
  pick: "OVER" | "UNDER" | "PASS";
  underdog_pick?: "OVER" | "UNDER" | "PASS" | null;
  confidence: number;
  agrees_with_engine: boolean;
  reasoning: string;
  key_factors: string[];
}

export interface SentToAi {
  context: Record<string, unknown>;
  prompt: string;
  system: string;
  response_format: string;
}

export interface AnalyzeResponse {
  ok: boolean;
  recommendation?: AiRecommendation;
  opponent?: string | null;
  sent?: SentToAi;
  error?: string;
}

export interface PromptResponse {
  ok: boolean;
  opponent?: string | null;
  sent: SentToAi;
}

export interface PpUnderdog {
  ud_line: number;
  ud_delta: number;
  over_app: "UD" | "PP" | "EVEN";
  under_app: "UD" | "PP" | "EVEN";
  ud_higher_price: string | null;
  ud_lower_price: string | null;
  ud_higher_multiplier: number | null;
  ud_lower_multiplier: number | null;
  ud_matched_name: string;
}

export interface PpEngine {
  verdict: "YES" | "LEAN" | "NO" | null;
  play: "OVER" | "UNDER" | null;
  win_prob: number | null;
  ev_percent: number | null;
  edge_type: string | null;
  book_count: number | null;
  dk_line: number | null;
  flags: string | null;
  model_p?: number | null;
  model_p_side?: number | null;
  model_credibility?: number | null;
  consensus_n?: number | null;
  consensus_tag?: "identified" | "single_book" | "degraded" | string | null;
}

export interface PpBoardProp {
  player: string;
  team: string | null;
  line: number;
  position?: string | null;
  image_url?: string | null;
  opponent?: string | null;
  game_id?: string | null;
  start_time?: string | null;
  underdog?: PpUnderdog | null;
  engine?: PpEngine | null;
}

export interface PpBoardGroup {
  stat_type: string;
  mapped_stat: string | null;
  has_form_data: boolean;
  count: number;
  props: PpBoardProp[];
}

export interface PpBoardGame {
  game_id: string;
  home: string;
  away: string;
  start_time: string | null;
  status: string | null;
  count: number;
}

export interface PpBoardResponse {
  total: number;
  groups: PpBoardGroup[];
  games: PpBoardGame[];
}

export interface SlipLeg {
  player: string;
  team: string | null;
  opponent: string | null;
  game: string | null;
  commence_time: string | null;
  stat_type: string;
  side: "OVER" | "UNDER";
  provider: "PP" | "UD";
  line: number | null;
  pp_line: number | null;
  ud_line: number | null;
  win_prob: number | null;
  ev_percent: number | null;
  verdict: "YES" | "LEAN" | "NO" | null;
  edge_type: string | null;
  ai: {
    pick: "OVER" | "UNDER" | "PASS";
    confidence: number | null;
    reasoning: string | null;
    key_factors: string[];
  };
}

export interface Slip {
  provider: "PP" | "UD";
  metric: "ev" | "win";
  requested: number;
  eligible: number;
  considered: number;
  agreed: number;
  legs: SlipLeg[];
  short: boolean;
  team_count: number;
  valid: boolean;
  correlations: { game: string; players: string[] }[];
}

export interface SlipResponse {
  ok: boolean;
  error?: string;
  slip: Slip;
}

export interface Bet {
  id: number;
  created_at: string;
  pp_player_name: string;
  dk_player_name: string;
  team: string | null;
  opponent: string | null;
  stat_type: string;
  play: "OVER" | "UNDER";
  pp_line: number;
  dk_line: number | null;
  win_prob: number | null;
  ev_percent: number | null;
  verdict: "YES" | "LEAN" | "NO" | null;
  edge_type: string | null;
  book_count: number | null;
  commence_time: string | null;
  stake: number | null;
  result: "WIN" | "LOSS" | "PUSH" | "VOID" | null;
  actual_value: number | null;
}

export interface BetSummary {
  total: number;
  settled: number;
  wins: number;
  losses: number;
  pushes: number;
  voids: number;
  hit_rate: number | null;
  total_staked: number;
  by_verdict: Record<string, { wins: number; losses: number; pushes: number; voids: number }>;
}

export interface BetsResponse {
  bets: Bet[];
  summary: BetSummary;
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
  fetchForm: () =>
    request<PipelineResult>("/pipeline/fetch-form", { method: "POST" }),
  fetchUnderdog: () =>
    request<PipelineResult>("/pipeline/fetch-underdog", { method: "POST" }),
  runMatcher: () =>
    request<PipelineResult>("/pipeline/run-matcher", { method: "POST" }),
  runFull: () =>
    request<PipelineResult>("/pipeline/full", { method: "POST" }),
  settleResults: () =>
    request<PipelineResult>("/pipeline/settle", { method: "POST" }),
  getRecord: () => request<RecordSummary>("/record"),
  trackBet: (edge: Edge, stake?: number) =>
    request<{ ok: boolean; id?: number; duplicate?: boolean; error?: string }>("/bets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...edge, stake: stake ?? null }),
    }),
  getBets: () => request<BetsResponse>("/bets"),
  settleBets: () =>
    request<{ success: boolean; settled: number; output: string }>("/bets/settle", {
      method: "POST",
    }),
  removeBet: (id: number) =>
    request<{ ok: boolean }>(`/bets/${id}`, { method: "DELETE" }),
  getPrizePicksBoard: () => request<PpBoardResponse>("/prizepicks/board"),
  buildSlip: (n: number, provider: "PP" | "UD", metric: "ev" | "win") =>
    request<SlipResponse>("/slip/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n, provider, metric }),
    }),
  getEdges: (stat: string, edgeType: string) =>
    request<EdgesResponse>(
      `/edges?stat=${encodeURIComponent(stat)}&edge_type=${encodeURIComponent(edgeType)}`,
    ),
  previewPrompt: (edge: Edge, mode: AnalysisMode = "full") =>
    request<PromptResponse>("/edges/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...edge, mode }),
    }),
  analyzeEdge: (edge: Edge, mode: AnalysisMode = "full") =>
    request<AnalyzeResponse>("/edges/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...edge, mode }),
    }),
  getClv: (refresh = false) =>
    request<ClvResponse>(`/clv?refresh=${refresh}`),
  refreshClv: () =>
    request<ClvResponse>("/clv/refresh", { method: "POST" }),
  exportEdgesUrl: (stat: string, edgeType: string) =>
    `${BASE}/edges/export?stat=${encodeURIComponent(stat)}&edge_type=${encodeURIComponent(edgeType)}`,
};
