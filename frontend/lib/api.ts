export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface StockScore {
  symbol: string;
  name: string;
  chip_score: number;
  fundamental_score: number;
  technical_score: number;
  total_score: number;
  reason?: string;
}

export interface PricePoint {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface StockDetail {
  symbol: string;
  name: string;
  market: string;
  sector?: string | null;
  latest_score?: StockScore | null;
  prices: PricePoint[];
}

export interface MarketSummary {
  as_of: string | null;
  stock_count: number;
  total_volume: number;
  foreign_net: number;
  investment_net: number;
  dealer_net: number;
  gainers: number;
  losers: number;
}

export interface MarketBreadth {
  as_of: string | null;
  universe_size: number;
  advance_decline: { advancing: number; declining: number; ratio: number };
  above_ma20_pct: number;
  above_ma50_pct: number;
  new_highs_20: number;
  new_lows_20: number;
  new_highs_60: number;
  new_lows_60: number;
  regime_hint: "broad_strength" | "broad_weakness" | "consolidation" | "mixed" | "no_data";
  sectors: Array<{ sector: string; ret_5d: number; members: number; rank: number }>;
  leaders: Array<{ symbol: string; name?: string; sector?: string; ret_5d: number; ret_1d: number; last: number }>;
  laggards: Array<{ symbol: string; name?: string; sector?: string; ret_5d: number; ret_1d: number; last: number }>;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  env: string;
  timestamp: string;
}

export interface TierInfo {
  plan: "free" | "pro" | "elite";
  limit: number;
  showing: number;
  total_available: number;
  upgrade_message?: string | null;
}

export interface Top10Response {
  items: StockScore[];
  tier: TierInfo;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> ?? {}),
  };
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    next: { revalidate: 0 },
  });
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err: any = new Error(body?.detail?.error || body?.detail || `API ${path} ${res.status}`);
    err.status = res.status;
    err.payload = body?.detail ?? body;
    throw err;
  }
  return body as T;
}

export const api = {
  health: () => request<HealthResponse>("/api/v1/health"),
  top10: () => request<Top10Response>("/api/v1/top10"),
  stock: (symbol: string) => request<StockDetail>(`/api/v1/stocks/${encodeURIComponent(symbol)}`),
  marketSummary: () => request<MarketSummary>("/api/v1/market/summary"),
  marketBreadth: () => request<MarketBreadth>("/api/v1/market/breadth"),

  // backtest
  strategies: () =>
    request<Array<{ key: string; name: string; description: string; min_plan: string }>>(
      "/api/v1/backtest/strategies",
    ),
  runBacktest: (data: { symbol: string; start: string; end: string; strategy: string }) =>
    request<any>("/api/v1/backtest/run", { method: "POST", body: JSON.stringify(data) }),
  predict: (symbol: string) => request<any>(`/api/v1/backtest/predict/${encodeURIComponent(symbol)}`),

  // leaderboard
  leaderboardWeekly: () => request<{
    period: string;
    items: Array<{ symbol: string; name: string; rank: number; entry_price: number; return_pct: number; date: string }>;
    status?: { total_picks_tracked: number; tracking_started_at: string | null; latest_pick_at: string | null; has_data: boolean };
  }>("/api/v1/leaderboard/weekly"),

  // trade plan
  tradePlan: (symbol: string, accountSize?: number) => {
    const qs = accountSize ? `?account_size=${accountSize}` : "";
    return request<TradePlanResponse>(`/api/v1/trade-plan/${encodeURIComponent(symbol)}${qs}`);
  },

  // scanner — strong-stock workflow for short-term traders
  scan: (params?: {
    bias?: "LONG" | "SHORT" | "NO_TRADE";
    setup?: string;
    min_rr?: number;
    min_confidence?: number;
    limit?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.bias) q.set("bias", params.bias);
    if (params?.setup) q.set("setup", params.setup);
    if (params?.min_rr !== undefined) q.set("min_rr", String(params.min_rr));
    if (params?.min_confidence !== undefined) q.set("min_confidence", String(params.min_confidence));
    if (params?.limit !== undefined) q.set("limit", String(params.limit));
    const s = q.toString();
    return request<ScanResponse>(`/api/v1/scanner/scan${s ? `?${s}` : ""}`);
  },
  movers: () => request<MoversResponse>("/api/v1/scanner/movers"),
  sectors: () => request<SectorsResponse>("/api/v1/scanner/sectors"),

  // AI Trading Research Terminal
  brief: () => request<DailyBriefResponse>("/api/v1/brief/today"),
  narrative: () => request<any>("/api/v1/narrative/today"),
  performanceSnapshot: (window = 30) => request<any>(`/api/v1/performance/snapshot?window=${window}`),
  performanceBySetup: (window = 30) => request<any>(`/api/v1/performance/by-setup?window=${window}`),
  performanceByRegime: (window = 30) => request<any>(`/api/v1/performance/by-regime?window=${window}`),
  performanceBySector: (window = 30) => request<any>(`/api/v1/performance/by-sector?window=${window}`),
  performanceSetupXRegime: () => request<any>("/api/v1/performance/setup-x-regime"),
  performanceDecay: () => request<any>("/api/v1/performance/decay"),
  strategyRank: () => request<any>("/api/v1/strategy-rank/"),
  universeActive: () => request<any>("/api/v1/universe/active"),
  universeSectors: () => request<any>("/api/v1/universe/sectors"),
  researchReport: () => request<{ markdown: string }>("/api/v1/research/today"),
  intelNews: (limit = 30) => request<{ count: number; items: NewsItem[] }>(`/api/v1/intelligence/news?limit=${limit}`),
  intelSectors: () => request<{ sectors: IntelSectorRow[]; top_leaders: any[]; bottom_laggards: any[] }>(`/api/v1/intelligence/sectors`),
  intelVolumes: (minRatio = 2.0) => request<{ items: VolumeAnomaly[] }>(`/api/v1/intelligence/volume-anomalies?min_ratio=${minRatio}`),
  intelPtt: () => request<PttHot>(`/api/v1/intelligence/ptt`),
  labRun: (symbol: string, strategy?: string) => {
    const qs = strategy ? `?strategy=${encodeURIComponent(strategy)}` : "";
    return request<any>(`/api/v1/lab/run/${encodeURIComponent(symbol)}${qs}`);
  },
  labPromoted: () => request<{ promoted: Record<string, any>; thresholds: Record<string, number> }>(`/api/v1/lab/promoted`),

  // Robust Quant Phase
  stressRun: (strategy: string, symbol = "0050") =>
    request<any>(`/api/v1/stress/run/${encodeURIComponent(strategy)}?symbol=${encodeURIComponent(symbol)}`),
  stressSegments: () => request<{ known_segments: any[] }>(`/api/v1/stress/segments`),
  correlationMatrix: (window = 90) => request<any>(`/api/v1/correlation/matrix?window=${window}`),
  riskAllocation: (regime: string, baseRiskPct = 0.01, maxConcurrent = 3) =>
    request<any>(`/api/v1/risk/allocation?regime=${encodeURIComponent(regime)}&base_risk_pct=${baseRiskPct}&max_concurrent=${maxConcurrent}`),
  portfolioSimulate: (symbol = "0050", strategies = "trend_breakout,chip_follow", maxConcurrent = 3) =>
    request<any>(`/api/v1/portfolio/simulate?symbol=${encodeURIComponent(symbol)}&strategies=${encodeURIComponent(strategies)}&max_concurrent=${maxConcurrent}`),
  edgePersistence: (window = 90) => request<any>(`/api/v1/persistence/?window=${window}`),
  qualityReport: () => request<{ items: any[] }>(`/api/v1/quality/`),
};

export interface SetupStats {
  setup: string;
  sample_size: number;
  win_rate: number;
  avg_rr: number;
  expectancy: number;
  max_consecutive_loss: number;
  avg_bars_held: number;
  last_30d_count: number;
  is_healthy: boolean;
}

export interface RankBreakdown {
  mode: "validated" | "prior";
  expectancy: number | null;
  frequency: number | null;
  confidence: number;
  sample_size: number;
}

export interface RegimeInfo {
  label: string;
  adx?: number | null;
  ema200_slope_pct?: number | null;
  ema50_slope_pct?: number | null;
  atr_contraction?: number | null;
  allowed_setups: string[];
  reason: string;
}

export interface ScanItem extends TradePlanResponse {
  name: string;
  market: string;
  edge: number;
  data_source?: string;
  rank: number;
  rank_breakdown?: RankBreakdown;
  stats?: SetupStats | null;
  regime?: RegimeInfo;
  management?: {
    move_to_breakeven_at_r: number;
    trailing_stop_atr_mult: number;
    trailing_stop_value: number | null;
    scale_out_tp1_pct: number;
    scale_out_tp2_pct: number;
    max_hold_bars: number;
  };
  // Market-context fields attached by scanner_service
  as_of?: string | null;
  ret_1d?: number | null;
  ret_5d?: number | null;
  ret_20d?: number | null;
  gap_pct?: number | null;
  rel_volume?: number | null;
  rs_5d?: number | null;
  rs_20d?: number | null;
  sector?: string;
  sector_rank?: number | null;
  sector_count?: number | null;
  sector_ret_5d?: number | null;
}

export interface MarketContext {
  as_of: string | null;
  market_5d: number;
  market_20d: number;
  universe_size: number;
  sectors: Record<string, { sector: string; ret_5d: number; count: number; rank: number; total: number }>;
}

export interface ScanResponse {
  scanned: number;
  matched: number;
  disabled_setups: string[];
  as_of?: string | null;
  market_context?: MarketContext;
  items: ScanItem[];
}

export interface StrategyHealthResponse {
  setups: Record<string, SetupStats & { is_healthy: boolean; reason: string }>;
}

export interface ValidationInfo {
  status: "validated" | "unvalidated" | "n/a";
  win_rate?: number;
  profit_factor?: number;
  max_drawdown_r?: number;
  expectancy_r?: number;
  sample_size?: number;
  reason?: string;
}

export interface NewsItem {
  id: number;
  title: string;
  summary: string;
  url: string;
  source: string;
  published_at: string;
  keywords: string[];
  mentioned_symbols: string[];
}

export interface IntelSectorRow {
  sector: string;
  count: number;
  return_5d: number | null;
  return_20d: number;
  rs_rank: number;
  momentum: number;
  leaders: Array<{ symbol: string; name: string; return_5d: number | null; return_20d: number; last_close: number | null }>;
}

export interface VolumeAnomaly {
  symbol: string;
  name: string;
  date: string;
  close: number;
  change_pct: number;
  volume: number;
  avg_volume_20d: number;
  ratio: number;
}

export interface PttHot {
  titles_seen: number;
  avg_push: number;
  hot_symbols: Array<{ symbol: string; mentions: number }>;
  hot_keywords: Array<{ keyword: string; count: number }>;
}

export interface DailyBriefResponse {
  generated_at: string;
  market_regime: {
    label: string;
    adx?: number | null;
    ema200_slope_pct?: number | null;
    allowed_setups: string[];
    reason: string;
    proxy?: string;
  };
  top_signals: {
    validated: ScanItem[];
    unvalidated: ScanItem[];
    rule: string;
  };
  strongest_sectors: IntelSectorRow[];
  weakest_sectors: IntelSectorRow[];
  top_leaders: Array<{ symbol: string; sector: string; return_20d: number; return_5d: number | null }>;
  volume_anomalies: VolumeAnomaly[];
  news_headlines: NewsItem[];
  ptt_hot: PttHot;
  cross_source_buzz_with_signal: Array<{ symbol: string; mentions: number }>;
  disabled_setups: string[];
  disclosure: string;
}

export interface PromotionDecision {
  promoted: boolean;
  failures: string[];
  metrics: Record<string, number>;
}

export interface IntradayResponse {
  symbol: string;
  ok: boolean;
  reason?: string | null;
  bars_count: number;
  opening_range_high?: number | null;
  opening_range_low?: number | null;
  vwap?: number | null;
  last_15m_close?: number | null;
  last_15m_volume?: number | null;
  cumulative_volume?: number | null;
  suggested_entry?: number | null;
  trigger?: string | null;
  confidence_boost: number;
}

export interface MoverRow {
  symbol: string;
  name: string;
  last: number;
  open: number;
  gap_pct: number;
  d1_pct: number;
  d5_pct: number;
  d20_pct: number;
  volume: number;
  volume_ratio: number;
  breakout_20: boolean;
  date: string;
}

export interface MoversResponse {
  scanned: number;
  gainers: MoverRow[];
  losers: MoverRow[];
  gap_ups: MoverRow[];
  volume_spikes: MoverRow[];
  breakouts: MoverRow[];
  momentum_5d: MoverRow[];
  momentum_20d: MoverRow[];
}

export interface SectorRow {
  sector: string;
  count: number;
  avg_d1_pct: number;
  avg_d5_pct: number;
  leaders: Array<{ symbol: string; name: string; last: number; d1_pct: number; d5_pct: number }>;
}

export interface SectorsResponse {
  sectors: SectorRow[];
}

export interface TradePlanResponse {
  symbol: string;
  bias: "LONG" | "SHORT" | "NO_TRADE";
  setup?: string | null;
  entry_zone?: [number, number] | null;
  stop_loss?: number | null;
  take_profit?: [number, number] | null;
  risk_reward?: number | null;
  confidence: number;
  chip_score: number;
  technical_score: number;
  fundamental_score: number;
  fundamental_available?: boolean;
  reasons: string[];
  indicators: Record<string, number | string | boolean | null>;
  chip: Record<string, number | string | boolean | null>;
  no_trade_reason?: string | null;
  last_close?: number | null;
  atr?: number | null;
  position_size_hint?: {
    account_size: number;
    risk_pct: number;
    max_risk_twd: number;
    suggested_shares: number;
    suggested_notional: number;
  } | null;
  data_source?: string;
  regime?: {
    label: string;
    adx?: number | null;
    ema200_slope_pct?: number | null;
    ema50_slope_pct?: number | null;
    atr_contraction?: number | null;
    allowed_setups: string[];
    reason: string;
  } | null;
  management?: {
    move_to_breakeven_at_r: number;
    trailing_stop_atr_mult: number;
    trailing_stop_value: number | null;
    scale_out_tp1_pct: number;
    scale_out_tp2_pct: number;
    max_hold_bars: number;
  } | null;
  validation?: ValidationInfo | null;
  production_status?: string;
  as_of?: string | null;
}
