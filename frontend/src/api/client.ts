const API_BASE = 'http://localhost:8001/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'API 요청 실패');
  }
  return res.json();
}

// === Types ===

export type CycleState =
  | 'BOOTSTRAP' | 'READY' | 'BUY_PENDING' | 'HOLDING'
  | 'SELL_PENDING' | 'BUY_BLOCKED' | 'OBSERVE_ONLY'
  | 'COOLDOWN' | 'MANUAL_REVIEW' | 'HALTED';

export interface CycleSummary {
  id: number;
  ticker: string;
  name: string;
  state: CycleState;
  state_reason: string;
  buy_mode: string;
  cycle_budget: number;
  tranche_count: number;
  steps_used: number;
  total_invested: number;
  total_quantity: number;
  avg_cost: number;
  last_buy_fill_price: number;
  take_profit_pct: number;
  add_trigger_pct: number;
  soft_drawdown_pct: number;
  hard_drawdown_pct: number;
  daily_buy_count: number;
  realized_pnl: number;
  realized_pnl_pct: number;
  started_at: string;
  ended_at: string | null;
  position_version: number;
}

export interface DashboardData {
  active_count: number;
  completed_count: number;
  halted_count: number;
  total_invested: number;
  total_pnl: number;
  avg_pnl_pct: number;
  cycles: CycleSummary[];
}

export interface SymbolInfo {
  id: number;
  ticker: string;
  name: string;
  market: string;
  exchange: string;
  is_enabled: boolean;
}

export interface OrderRecord {
  id: number;
  cycle_id: number;
  ticker: string;
  client_order_id: string;
  side: 'BUY' | 'SELL';
  status: string;
  quantity: number;
  limit_price: number | null;
  filled_quantity: number;
  filled_avg_price: number;
  filled_amount: number;
  step_no: number | null;
  reason: string;
  replace_count: number;
  created_at: string;
  filled_at: string | null;
}

export interface EventLogEntry {
  id: number;
  cycle_id: number | null;
  event_type: string;
  level: string;
  message: string;
  data: Record<string, unknown> | null;
  created_at: string;
}

export interface CompletedCycle {
  id: number;
  ticker: string;
  cycle_budget: number;
  realized_pnl: number;
  realized_pnl_pct: number;
  steps_used: number;
  tranche_count: number;
  started_at: string;
  ended_at: string | null;
}

export interface CompletedSummary {
  total_cycles: number;
  total_pnl: number;
  avg_pnl_pct: number;
  cycles: CompletedCycle[];
}

export interface HealthStatus {
  status: string;
  paused: boolean;
}

export interface AppSettings {
  strategy: Record<string, unknown>;
  session: Record<string, unknown>;
  risk: Record<string, unknown>;
  execution: Record<string, unknown>;
  cascade: Record<string, unknown>;
  kill_switch: Record<string, unknown>;
  decision_interval_sec: number;
  regime_symbol: string;
}

// === API ===

export const fetchDashboard = () => request<DashboardData>('/dashboard');

export const fetchSymbolDetail = (ticker: string) =>
  request<{ symbol: SymbolInfo & { is_enabled: boolean }; cycles: CycleSummary[] }>(
    `/dashboard/${ticker}`
  );

export const fetchSymbols = () => request<SymbolInfo[]>('/symbols');

export const addSymbol = (data: { ticker: string; name: string; market?: string; exchange?: string }) =>
  request<{ id: number; message: string }>('/symbols', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const toggleSymbol = (id: number) =>
  request<{ is_enabled: boolean; message: string }>(`/symbols/${id}/toggle`, { method: 'PUT' });

export const startCycle = (data: {
  ticker: string;
  cycle_budget: number;
  buy_mode?: string;
  tranche_count?: number;
  take_profit_pct?: number;
  add_trigger_pct?: number;
}) =>
  request<{ id: number; message: string }>('/cycle/start', {
    method: 'POST',
    body: JSON.stringify(data),
  });

export const haltCycle = (id: number) =>
  request<{ message: string }>(`/cycle/${id}/halt`, { method: 'POST' });

export const resumeCycle = (id: number) =>
  request<{ message: string }>(`/cycle/${id}/resume`, { method: 'POST' });

export const resolveCycle = (id: number) =>
  request<{ message: string }>(`/cycle/${id}/resolve`, { method: 'POST' });

export const fetchOrders = (params?: {
  ticker?: string;
  side?: string;
  limit?: number;
  offset?: number;
}) => {
  const query = new URLSearchParams();
  if (params?.ticker) query.set('ticker', params.ticker);
  if (params?.side) query.set('side', params.side);
  if (params?.limit) query.set('limit', String(params.limit));
  if (params?.offset) query.set('offset', String(params.offset));
  const qs = query.toString();
  return request<OrderRecord[]>(`/orders${qs ? `?${qs}` : ''}`);
};

export const fetchCompletedSummary = () => request<CompletedSummary>('/orders/summary');

export const fetchEvents = (params?: {
  cycle_id?: number;
  event_type?: string;
  level?: string;
  limit?: number;
}) => {
  const query = new URLSearchParams();
  if (params?.cycle_id) query.set('cycle_id', String(params.cycle_id));
  if (params?.event_type) query.set('event_type', params.event_type);
  if (params?.level) query.set('level', params.level);
  if (params?.limit) query.set('limit', String(params.limit));
  const qs = query.toString();
  return request<EventLogEntry[]>(`/events${qs ? `?${qs}` : ''}`);
};

export const fetchSettings = () => request<AppSettings>('/settings');

export const fetchHealth = () => request<HealthStatus>('/health');

// === 실시간 시세 ===

export interface LiveQuote {
  symbol: string;
  bid: number;
  ask: number;
  mid: number;
  last: number;
  spread_bps: number;
  volume: number;
  prev_close: number;
  change_pct: number;
  is_live: boolean;
  timestamp: string;
  sma200?: number;
  sma20?: number;
}

export interface MarketOverview {
  is_live: boolean;
  quotes: {
    symbol: string;
    last: number;
    prev_close: number;
    change_pct: number;
    volume: number;
  }[];
}

export const fetchQuote = (ticker: string) =>
  request<LiveQuote>(`/dashboard/quote/${ticker}`);

export const fetchMarketOverview = () =>
  request<MarketOverview>('/dashboard/market-overview');

// === 시장 데이터 ===

export interface MarketQuote {
  symbol: string;
  name: string;
  price: number;
  prev_close: number;
  change_pct: number;
  volume: number;
  market_cap: number;
  day_high: number;
  day_low: number;
  '52w_high': number;
  '52w_low': number;
  avg_volume_3m: number;
  exchange: string;
}

export interface MarketTopResponse {
  market: string;
  quotes: MarketQuote[];
  error?: string;
}

export interface RecommendedStock {
  symbol: string;
  name: string;
  reason: string;
  risk: string;
  leverage: string;
  tracking: string;
  price?: number;
  prev_close?: number;
  change_pct?: number;
  volume?: number;
  is_live?: boolean;
  sma20?: number;
  sma200?: number;
  above_sma200?: boolean;
}

export interface StrategyPhase {
  id: number;
  name: string;
  icon: string;
  description: string;
  analogy?: string;
  example: string;
  key_param?: string;
}

export interface RiskControl {
  name: string;
  description: string;
  analogy?: string;
  param: string;
}

export interface SimStep {
  step: number;
  price: number;
  qty: number;
  invested: number;
  avg_cost: number;
  action?: string;
  sell_price?: number;
  pnl?: number;
  comment?: string;
}

export interface AnalogyScene {
  scene: string;
  analogy: string;
  actual: string;
}

export interface WhySection {
  title: string;
  analogy: string;
  detail: string;
}

export interface FAQ {
  q: string;
  a: string;
}

export interface StrategyGuide {
  title: string;
  subtitle: string;
  summary: string;
  analogy: {
    title: string;
    intro: string;
    story: AnalogyScene[];
    key_insight: string;
  };
  why_it_works: WhySection[];
  phases: StrategyPhase[];
  risk_controls: RiskControl[];
  simulation_example: {
    symbol: string;
    budget: number;
    tranches: number;
    per_tranche: number;
    steps: SimStep[];
  };
  faq: FAQ[];
}

export const fetchUSTop = (count = 10) =>
  request<MarketTopResponse>(`/market/us/top?count=${count}`);

export const fetchKRTop = (count = 10) =>
  request<MarketTopResponse>(`/market/kr/top?count=${count}`);

export const fetchRecommended = () =>
  request<{ recommendations: RecommendedStock[] }>('/market/recommended');

export const fetchStrategyGuide = () =>
  request<StrategyGuide>('/market/strategy-guide');

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const fetchManualGuide = () => request<any>('/market/manual-guide');

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const fetchTqqqStrategies = () => request<any>('/market/tqqq-strategies');
