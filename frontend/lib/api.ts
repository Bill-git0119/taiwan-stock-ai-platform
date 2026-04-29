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

export interface UserOut {
  id: number;
  email: string;
  name?: string | null;
  plan: "free" | "pro" | "elite";
  is_admin: boolean;
  line_user_id?: string | null;
  notify_open: boolean;
  notify_intraday: boolean;
  notify_close: boolean;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: UserOut;
}

export interface PlansResponse {
  free: { name: string; price_twd: number; top_n: number; features: string[] };
  pro: { name: string; price_twd: number; top_n: number; features: string[] };
  elite: { name: string; price_twd: number; top_n: number; features: string[] };
}

export interface SubscriptionInfo {
  plan: string;
  status: string;
  price_twd: number;
  current_period_end?: string | null;
}

const TOKEN_KEY = "tsa_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit & { auth?: boolean }): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> ?? {}),
  };
  if (init?.auth !== false) {
    const t = getToken();
    if (t) headers["Authorization"] = `Bearer ${t}`;
  }
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

  // auth
  register: (data: { email: string; password: string; name?: string; ref?: string }) =>
    request<AuthResponse>("/api/v1/auth/register", { method: "POST", body: JSON.stringify(data) }),
  login: (data: { email: string; password: string }) =>
    request<AuthResponse>("/api/v1/auth/login", { method: "POST", body: JSON.stringify(data) }),
  me: () => request<UserOut>("/api/v1/auth/me"),
  updateMe: (data: Partial<Pick<UserOut, "name" | "line_user_id" | "notify_open" | "notify_intraday" | "notify_close">>) =>
    request<UserOut>("/api/v1/auth/me", { method: "PATCH", body: JSON.stringify(data) }),
  forgotPassword: (email: string) =>
    request<{ ok: boolean; dev_reset_token?: string }>("/api/v1/auth/forgot-password", {
      method: "POST", body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, new_password: string) =>
    request<{ ok: boolean }>("/api/v1/auth/reset-password", {
      method: "POST", body: JSON.stringify({ token, new_password }),
    }),
  changePassword: (current_password: string, new_password: string) =>
    request<{ ok: boolean }>("/api/v1/auth/change-password", {
      method: "POST", body: JSON.stringify({ current_password, new_password }),
    }),

  // billing
  plans: () => request<PlansResponse>("/api/v1/billing/plans"),
  checkout: (plan: "pro" | "elite") =>
    request<{ url: string; plan: string }>("/api/v1/billing/checkout", {
      method: "POST", body: JSON.stringify({ plan }),
    }),
  subscription: () => request<SubscriptionInfo>("/api/v1/billing/subscription"),
  portal: () => request<{ url: string }>("/api/v1/billing/portal", { method: "POST" }),

  // notify
  notifyTest: () => request<{ ok: boolean }>("/api/v1/notify/test", { method: "POST" }),
  notifySettings: () => request<any>("/api/v1/notify/settings"),

  // admin
  adminStats: () => request<any>("/api/v1/admin/stats"),
  adminUsers: () => request<any[]>("/api/v1/admin/users"),
  adminSubs: () => request<any[]>("/api/v1/admin/subscriptions"),
  adminRevenue: () => request<any>("/api/v1/admin/revenue"),
  adminNotifications: () => request<any[]>("/api/v1/admin/notifications"),
  adminHealth: () => request<any>("/api/v1/admin/health"),
  adminGrowth: () => request<any>("/api/v1/admin/growth"),

  // backtest
  strategies: () =>
    request<Array<{ key: string; name: string; description: string; min_plan: string }>>(
      "/api/v1/backtest/strategies",
    ),
  runBacktest: (data: { symbol: string; start: string; end: string; strategy: string }) =>
    request<any>("/api/v1/backtest/run", { method: "POST", body: JSON.stringify(data) }),
  predict: (symbol: string) => request<any>(`/api/v1/backtest/predict/${encodeURIComponent(symbol)}`),

  // referral
  referralMe: () => request<{
    code: string;
    invited: number;
    converted: number;
    granted: number;
    rewards_unlocked: string[];
    next_target: number | null;
    progress: number;
    share_url: string;
  }>("/api/v1/referral/me"),
  referralInvite: (email: string) =>
    request<{ ok: boolean; code: string; invitee_email: string }>(
      "/api/v1/referral/invite", { method: "POST", body: JSON.stringify({ email }) },
    ),

  // leaderboard
  leaderboardWeekly: () => request<{
    period: string;
    items: Array<{ symbol: string; name: string; rank: number; entry_price: number; return_pct: number; date: string }>;
  }>("/api/v1/leaderboard/weekly"),

  // blog
  blogList: () => request<Array<{ slug: string; title: string; summary: string; tags: string[]; published_at: string }>>(
    "/api/v1/blog/",
  ),
  blogPost: (slug: string) => request<{
    slug: string; title: string; summary: string; body_md: string; tags: string[]; published_at: string;
  }>(`/api/v1/blog/${encodeURIComponent(slug)}`),
};
