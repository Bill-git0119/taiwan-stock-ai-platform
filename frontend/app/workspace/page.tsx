"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  Activity, AlertCircle, Brain, Database, Flame, RefreshCw, ShieldCheck,
  Target, TrendingUp,
} from "lucide-react";

import { Topbar } from "@/components/layout/Topbar";
import {
  api,
  type DatahubFreshness,
  type DecisionsResponse,
  type LongTermResponse,
  type MarketStateResponse,
  type NarrativeResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// ─────────────────────────── helpers ──────────────────────────────────

function pct(n: number | null | undefined, dp = 2): string {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(dp)}%`;
}
function num(n: number | null | undefined, dp = 2): string {
  if (n == null) return "—";
  return n.toFixed(dp);
}

const REGIME_TONE: Record<string, string> = {
  trending_up: "text-up border-up/40 bg-up/10",
  trending_up_weak: "text-up/80 border-up/30 bg-up/5",
  sideways: "text-text-muted border-line bg-bg-elevated/40",
  trending_down: "text-down border-down/40 bg-down/10",
  trending_down_weak: "text-down/80 border-down/30 bg-down/5",
  bearish: "text-down border-down/40 bg-down/10",
  unknown: "text-text-muted border-line bg-bg-elevated/40",
};
const RISK_TONE: Record<string, string> = {
  low: "text-up", normal: "text-text-bright",
  elevated: "text-amber-400", high: "text-down",
};
const STATUS_TONE: Record<string, string> = {
  ACTIVE: "text-up border-up/40 bg-up/10",
  WATCH: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  RESEARCH_ONLY: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  DISABLED: "text-down border-down/40 bg-down/10",
  UNKNOWN: "text-text-muted border-line bg-bg-elevated/40",
};
const SEVERITY_TONE: Record<string, string> = {
  ok: "text-up", warn: "text-amber-400", fail: "text-down",
};

// ─────────────────────────── page ────────────────────────────────────

export default function WorkspacePage() {
  const [state, setState] = useState<MarketStateResponse | null>(null);
  const [decisions, setDecisions] = useState<DecisionsResponse | null>(null);
  const [longTerm, setLongTerm] = useState<LongTermResponse | null>(null);
  const [narrative, setNarrative] = useState<NarrativeResponse | null>(null);
  const [freshness, setFreshness] = useState<DatahubFreshness | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const fail = (label: string, e: unknown) => {
      console.warn(label, e);
      if (alive && !error) setError(`${label} 載入失敗`);
    };
    api.marketState().then((s) => alive && setState(s)).catch((e) => fail("market_state", e));
    api.shortTermDecisions({ limit: 30, include_research: true })
      .then((d) => alive && setDecisions(d)).catch((e) => fail("decisions", e));
    api.longTermBuckets().then((l) => alive && setLongTerm(l)).catch((e) => fail("long_term", e));
    api.dailyBrief().then((n) => alive && setNarrative(n)).catch((e) => fail("narrative", e));
    api.datahubFreshness().then((f) => alive && setFreshness(f)).catch((e) => fail("freshness", e));
    return () => { alive = false; };
  }, [refresh]);

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-[1600px] mx-auto px-5 py-5 space-y-4">
        <header className="flex items-baseline justify-between border-b border-line pb-3">
          <div>
            <h1 className="text-xl font-semibold text-text-bright tracking-tight">
              Research Desk / Workspace
            </h1>
            <p className="text-[11px] text-text-muted mt-0.5">
              regime · breadth · macro · decisions · narrative — 一頁掌握
            </p>
          </div>
          <button onClick={() => setRefresh((n) => n + 1)}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded border border-line text-xs text-text-muted hover:text-text-bright hover:border-accent/40">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </header>

        {error && (
          <div className="rounded border border-down/30 bg-down/10 p-2 text-xs text-down">
            部分區塊載入失敗：{error}
          </div>
        )}

        {/* Top row: market state + freshness */}
        <section className="grid grid-cols-12 gap-3">
          <MarketStatePanel state={state} className="col-span-12 lg:col-span-8" />
          <FreshnessPanel data={freshness} className="col-span-12 lg:col-span-4" />
        </section>

        {/* Narrative */}
        <section>
          <NarrativePanel data={narrative} />
        </section>

        {/* Short-term decisions */}
        <section>
          <DecisionsPanel data={decisions} />
        </section>

        {/* Long-term buckets */}
        <section>
          <LongTermPanel data={longTerm} />
        </section>
      </main>
    </div>
  );
}

// ─────────────────────────── panels ──────────────────────────────────

function PanelHeader({ icon: Icon, title, subtitle, right }: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  subtitle?: React.ReactNode;
  right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between px-3 py-2 border-b border-line">
      <div className="flex items-center gap-2">
        <Icon className="w-3.5 h-3.5 text-accent" />
        <div>
          <h2 className="text-[11px] uppercase tracking-widest font-semibold text-text-bright">
            {title}
          </h2>
          {subtitle && <div className="text-[10px] text-text-muted mt-0.5">{subtitle}</div>}
        </div>
      </div>
      {right}
    </div>
  );
}

function MarketStatePanel({ state, className }: { state: MarketStateResponse | null; className?: string }) {
  return (
    <div className={cn("rounded-md border border-line bg-bg-panel/40", className)}>
      <PanelHeader icon={Brain} title="Market State"
                   subtitle={state ? `regime confidence ${(state.confidence * 100).toFixed(0)}%` : "loading…"} />
      <div className="p-3">
        {!state ? (
          <div className="text-xs text-text-muted">Loading…</div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
              <Tile label="Regime"
                    value={
                      <span className={cn(
                        "inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider border",
                        REGIME_TONE[state.regime] ?? REGIME_TONE.unknown,
                      )}>{state.regime.replace(/_/g, " ")}</span>
                    } />
              <Tile label="Risk Level"
                    value={<span className={cn("font-mono uppercase text-sm", RISK_TONE[state.risk_level])}>
                      {state.risk_level}
                    </span>} />
              <Tile label="Risk-On Score"
                    value={<span className={cn("font-mono text-sm",
                      state.risk_on_score >= 0 ? "text-up" : "text-down",
                    )}>
                      {state.risk_on_score >= 0 ? "+" : ""}{state.risk_on_score.toFixed(2)}
                    </span>} />
              <Tile label="Exposure ×"
                    value={<span className={cn("font-mono text-sm",
                      state.exposure_mult >= 0.75 ? "text-up"
                      : state.exposure_mult >= 0.5 ? "text-text-bright"
                      : "text-amber-400")}>
                      {state.exposure_mult.toFixed(2)}
                    </span>} />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <div className="text-[10px] uppercase text-text-muted mb-1">允許 setup</div>
                <div className="flex flex-wrap gap-1.5">
                  {state.allowed_setups.length === 0
                    ? <span className="text-xs text-down">無 — 全部封鎖</span>
                    : state.allowed_setups.map((s) => (
                      <span key={s} className="px-1.5 py-0.5 rounded bg-up/10 text-up border border-up/30 text-[10px] font-mono">{s}</span>
                    ))}
                </div>
                {state.forbidden_setups.length > 0 && (
                  <div className="mt-2 text-[10px] text-text-muted">
                    禁用：<span className="font-mono">{state.forbidden_setups.join(", ")}</span>
                  </div>
                )}
              </div>
              <div>
                <div className="text-[10px] uppercase text-text-muted mb-1">理由</div>
                <ul className="text-[11px] text-text-muted space-y-0.5 leading-relaxed">
                  {state.reasons.slice(0, 6).map((r, i) => (
                    <li key={i}>· {r}</li>
                  ))}
                </ul>
              </div>
            </div>
            {Object.keys(state.macro || {}).length > 0 && (
              <div className="mt-3 pt-3 border-t border-line">
                <div className="text-[10px] uppercase text-text-muted mb-1.5">Macro snapshot</div>
                <div className="grid grid-cols-3 md:grid-cols-7 gap-2 text-xs font-mono">
                  {Object.entries(state.macro).slice(0, 7).map(([k, v]) => (
                    <div key={k} className="rounded border border-line bg-bg-elevated/40 p-1.5">
                      <div className="text-[9px] uppercase text-text-muted">{k}</div>
                      <div className="text-text-bright">{num(v.last as number | undefined)}</div>
                      <div className={cn(
                        "text-[10px]",
                        (v.d1_pct ?? 0) >= 0 ? "text-up" : "text-down",
                      )}>{pct(v.d1_pct as number | undefined)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function FreshnessPanel({ data, className }: { data: DatahubFreshness | null; className?: string }) {
  return (
    <div className={cn("rounded-md border border-line bg-bg-panel/40", className)}>
      <PanelHeader icon={Database} title="Data Sources"
                   subtitle={data ? `${data.sources.length} 來源追蹤中` : "loading…"} />
      <div className="p-3 text-xs space-y-1.5">
        {!data?.sources.length && (
          <div className="text-text-muted">尚無來源 — 跑一次 collector：</div>
        )}
        {data?.sources.length === 0 && (
          <div className="flex gap-2 flex-wrap">
            {["yfinance.daily", "twse.chips"].map((s) => (
              <RunSourceButton key={s} source={s} />
            ))}
          </div>
        )}
        {data?.sources.map((s) => (
          <div key={s.source} className="flex items-baseline justify-between border-b border-line/40 py-1">
            <div>
              <div className="font-mono text-[11px] text-text-bright">{s.source}</div>
              <div className="text-[10px] text-text-muted">
                {s.latest_data_at ? `latest ${s.latest_data_at.slice(0, 10)}` : "—"}
                {s.age_hours != null && ` · ${s.age_hours}h ago`}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className={cn("font-mono text-[10px] uppercase", SEVERITY_TONE[s.severity])}>
                {s.severity}
              </span>
              <RunSourceButton source={s.source} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RunSourceButton({ source }: { source: string }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  async function run() {
    setRunning(true); setResult(null);
    try {
      const r = await api.runDatahub(source);
      setResult(`+${r.rows} rows`);
      setTimeout(() => setResult(null), 4000);
    } catch (e) {
      setResult(`✗ ${(e as Error).message?.slice(0, 30)}`);
    } finally {
      setRunning(false);
    }
  }
  return (
    <button onClick={run} disabled={running}
            className="text-[10px] px-1.5 py-0.5 rounded border border-line hover:border-accent/40 text-text-muted hover:text-text-bright disabled:opacity-50 font-mono">
      {running ? "running…" : result ?? "run"}
    </button>
  );
}

function NarrativePanel({ data }: { data: NarrativeResponse | null }) {
  return (
    <div className="rounded-md border border-line bg-bg-panel/40">
      <PanelHeader icon={AlertCircle} title="Daily Brief"
                   subtitle={data ? `provider=${data.provider} · ${new Date(data.generated_at).toLocaleString("zh-TW")}` : "loading…"} />
      <div className="p-4 prose prose-sm prose-invert max-w-none text-xs leading-relaxed text-text"
           dangerouslySetInnerHTML={{ __html: data ? renderMarkdown(data.markdown) : "loading…" }} />
    </div>
  );
}

function DecisionsPanel({ data }: { data: DecisionsResponse | null }) {
  if (!data) return <Skeleton label="decisions" />;
  const actionable = data.decisions.filter((d) => d.actionable);
  const research = data.decisions.filter((d) => !d.actionable);
  return (
    <div className="rounded-md border border-line bg-bg-panel/40">
      <PanelHeader icon={Target} title="Short-Term Decisions"
                   subtitle={`actionable=${data.actionable_count} · research=${data.research_count}`} />
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead className="text-[10px] uppercase tracking-wider text-text-muted bg-bg-elevated/40">
            <tr>
              <th className="text-left px-3 py-2">代號</th>
              <th className="text-left">Setup</th>
              <th className="text-right">信心</th>
              <th className="text-right">RR</th>
              <th className="text-right">進場</th>
              <th className="text-right">SL</th>
              <th className="text-right">TP1/TP2</th>
              <th className="text-right">RS 5D</th>
              <th className="text-left">族群</th>
              <th className="text-center">狀態</th>
              <th className="text-left">why_now / blocked</th>
            </tr>
          </thead>
          <tbody className="font-mono">
            {actionable.map((d) => <Row key={d.symbol + "-a"} d={d} />)}
            {actionable.length > 0 && research.length > 0 && (
              <tr><td colSpan={11} className="border-y border-line/40 bg-bg-elevated/40 px-3 py-1
                     text-[10px] uppercase tracking-wider text-text-muted">
                Research-only（被 gate 擋下）
              </td></tr>
            )}
            {research.slice(0, 8).map((d) => <Row key={d.symbol + "-r"} d={d} dim />)}
            {data.decisions.length === 0 && (
              <tr><td colSpan={11} className="text-center text-text-muted px-3 py-6">
                沒有候選 — 資料尚未灌入
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Row({ d, dim }: { d: ShortTermDecisionRow; dim?: boolean }) {
  return (
    <tr className={cn("border-t border-line", dim && "opacity-60")}>
      <td className="px-3 py-1.5">
        <Link href={`/stock/${d.symbol}`} className="text-text-bright hover:text-accent">
          {d.symbol}
        </Link>
        <span className="ml-1 font-sans text-[10px] text-text-muted">{d.name}</span>
      </td>
      <td className="py-1.5 text-[10px] uppercase font-mono text-text-muted">{d.setup ?? "—"}</td>
      <td className="text-right">{Math.round(d.confidence * 100)}%</td>
      <td className={cn("text-right", (d.risk_reward ?? 0) >= 1.5 ? "text-up" : "text-text-muted")}>
        {d.risk_reward ? d.risk_reward.toFixed(2) : "—"}
      </td>
      <td className="text-right">
        {d.entry_zone ? `${d.entry_zone[0].toFixed(2)}–${d.entry_zone[1].toFixed(2)}` : "—"}
      </td>
      <td className="text-right text-down">{d.stop_loss?.toFixed(2) ?? "—"}</td>
      <td className="text-right text-up">
        {d.take_profit ? `${d.take_profit[0].toFixed(2)}/${d.take_profit[1].toFixed(2)}` : "—"}
      </td>
      <td className={cn("text-right",
        (d.rs_5d ?? 0) >= 2 ? "text-up" : (d.rs_5d ?? 0) <= -2 ? "text-down" : "text-text-muted",
      )}>
        {d.rs_5d != null ? `${d.rs_5d >= 0 ? "+" : ""}${d.rs_5d.toFixed(1)}` : "—"}
      </td>
      <td className="text-[10px] text-text-muted">
        {d.sector ?? "—"}
        {d.sector_rank && <span className="ml-1 font-mono">#{d.sector_rank}/{d.sector_count ?? "?"}</span>}
      </td>
      <td className="text-center">
        <span className={cn(
          "inline-block px-1 py-0.5 rounded text-[9px] font-mono uppercase border",
          STATUS_TONE[d.production_status ?? "UNKNOWN"] ?? STATUS_TONE.UNKNOWN,
        )}>
          {d.production_status ?? "—"}
        </span>
      </td>
      <td className="px-3 py-1.5 text-[10px] text-text-muted max-w-[18em] truncate"
          title={d.invalidation_reason ?? (d.why_now ?? []).join(" · ")}>
        {d.actionable
          ? (d.why_now ?? []).slice(0, 2).join(" · ")
          : <span className="text-amber-400">⊘ {d.invalidation_reason}</span>}
      </td>
    </tr>
  );
}

// Local type to avoid duplicating ShortTermDecision shape here
type ShortTermDecisionRow = DecisionsResponse["decisions"][number] & { sector_count?: number };

function LongTermPanel({ data }: { data: LongTermResponse | null }) {
  if (!data) return <Skeleton label="long-term" />;
  const ORDER: Array<keyof typeof data.buckets> = [
    "COMPOUNDER", "TURNAROUND", "CYCLICAL", "AVOID", "NEUTRAL",
  ] as any;
  return (
    <div className="rounded-md border border-line bg-bg-panel/40">
      <PanelHeader icon={TrendingUp} title="Long-Term Buckets"
                   subtitle={data.fundamentals_wired
                     ? "fundamentals OK"
                     : "⚠ fundamentals not wired — COMPOUNDER 暫不可信"} />
      <div className="p-3 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
        {ORDER.map((k) => (
          <div key={String(k)} className="rounded border border-line/60 bg-bg-elevated/30 p-2">
            <div className="flex items-baseline justify-between mb-1.5">
              <div className="text-[10px] uppercase tracking-widest font-semibold text-text-bright">{String(k)}</div>
              <div className="text-[10px] font-mono text-text-muted">{data.counts[String(k)] ?? 0}</div>
            </div>
            <ul className="space-y-1 text-xs font-mono">
              {(data.buckets[String(k)] || []).slice(0, 5).map((c) => (
                <li key={c.symbol} className="flex items-baseline justify-between">
                  <Link href={`/stock/${c.symbol}`} className="text-text-bright hover:text-accent">
                    {c.symbol}
                  </Link>
                  <span className="text-[10px] text-text-muted">{c.score.toFixed(0)}</span>
                </li>
              ))}
              {(!data.buckets[String(k)] || data.buckets[String(k)].length === 0) && (
                <li className="text-[10px] text-text-muted">—</li>
              )}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function Skeleton({ label }: { label: string }) {
  return (
    <div className="rounded-md border border-line bg-bg-panel/40 p-4 text-xs text-text-muted">
      {label} loading…
    </div>
  );
}

function Tile({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded border border-line bg-bg-elevated/30 p-2">
      <div className="text-[10px] uppercase text-text-muted mb-1">{label}</div>
      <div>{value}</div>
    </div>
  );
}

// Tiny markdown → HTML — no library, supports headers + bullets + bold.
function renderMarkdown(md: string): string {
  return md
    .split("\n")
    .map((line) => {
      if (/^##\s+/.test(line)) {
        return `<h3 class="text-sm font-semibold text-text-bright mt-3 mb-1">${line.replace(/^##\s+/, "")}</h3>`;
      }
      if (/^- /.test(line)) {
        return `<li class="ml-4">${escapeHtml(line.slice(2))}</li>`;
      }
      if (/^_/.test(line) && /_$/.test(line)) {
        return `<div class="text-[10px] text-text-muted mt-2 italic">${escapeHtml(line.replace(/^_|_$/g, ""))}</div>`;
      }
      return line ? `<p class="text-xs text-text">${escapeHtml(line)}</p>` : "";
    })
    .join("");
}
function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}
