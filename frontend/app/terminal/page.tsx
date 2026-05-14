"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  AlertTriangle, Newspaper, Flame, ShieldCheck, TrendingUp, TrendingDown,
  Layers, Hash, Cpu, Activity, FileText,
} from "lucide-react";

import { Topbar } from "@/components/layout/Topbar";
import { api, type DailyBriefResponse, type ScanItem, type IntelSectorRow } from "@/lib/api";
import { cn } from "@/lib/utils";

// ─────────────────────────── helpers ────────────────────────────

function num(n: number | null | undefined, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}
function pct(n: number | null | undefined, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const v = Number(n);
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}
function ts(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleString("zh-TW", { hour12: false });
  } catch { return iso; }
}

const REGIME_TONE: Record<string, string> = {
  trending_up: "text-up border-up/40 bg-up/10",
  trending_up_weak: "text-up/80 border-up/30 bg-up/5",
  trending_down: "text-down border-down/40 bg-down/10",
  trending_down_weak: "text-down/80 border-down/30 bg-down/5",
  sideways: "text-text-muted border-line bg-bg-elevated/40",
  bearish: "text-down border-down/40 bg-down/10",
  unknown: "text-text-muted border-line bg-bg-elevated/40",
};

// ─────────────────────────── page ───────────────────────────────

export default function TerminalPage() {
  const [brief, setBrief] = useState<DailyBriefResponse | null>(null);
  const [narrative, setNarrative] = useState<any>(null);
  const [strategyRank, setStrategyRank] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.brief()
      .then((b) => { if (alive) setBrief(b); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : "load failed"); });
    api.narrative().then((n) => alive && setNarrative(n)).catch(() => { });
    api.strategyRank().then((r) => alive && setStrategyRank(r)).catch(() => { });
    return () => { alive = false; };
  }, []);

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-[1600px] mx-auto px-5 py-5 space-y-5">
        <header className="flex items-baseline justify-between border-b border-line pb-3">
          <div>
            <h1 className="text-xl font-semibold text-text-bright tracking-tight">
              AI Trading Research Terminal
            </h1>
            <p className="text-[11px] text-text-muted mt-1">
              每日自動研究 · Edge-validated 訊號 · 不展示無驗證機會
            </p>
          </div>
          <div className="flex items-center gap-4">
            <nav className="flex gap-3 text-[11px] font-mono uppercase tracking-widest">
              <span className="text-accent border-b border-accent pb-0.5">Brief</span>
              <Link href="/terminal/performance" className="text-text-muted hover:text-text">Performance</Link>
              <Link href="/terminal/robustness" className="text-text-muted hover:text-text">Robustness</Link>
            </nav>
            {brief && (
              <span className="font-mono text-[10px] text-text-muted">
                GENERATED {ts(brief.generated_at)}
              </span>
            )}
          </div>
        </header>

        {error && (
          <div className="rounded-md border border-down/30 bg-down/10 p-3 text-sm text-down">
            載入失敗：{error}
          </div>
        )}

        {!brief && !error && (
          <div className="font-mono text-xs text-text-muted">Loading brief…</div>
        )}

        {brief && <BriefBody brief={brief} narrative={narrative} strategyRank={strategyRank} />}
      </main>
    </div>
  );
}

// ─────────────────────────── body ───────────────────────────────

function BriefBody({ brief, narrative, strategyRank }: {
  brief: DailyBriefResponse;
  narrative: any;
  strategyRank: any;
}) {
  return (
    <div className="grid grid-cols-12 gap-4">
      {/* Narrative panel — what the market is trading */}
      {narrative && (
        <Card className="col-span-12" icon={<Newspaper className="w-3.5 h-3.5 text-accent" />}
              title="MARKET NARRATIVE"
              subtitle={`style: ${narrative.market_style}`}>
          <div className="text-sm text-text leading-relaxed">{narrative.market_summary}</div>
          {narrative.risk_factors?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-line">
              <div className="text-[10px] uppercase text-text-muted mb-1.5">Risk factors</div>
              <ul className="text-xs space-y-1">
                {narrative.risk_factors.map((r: string, i: number) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-down mt-0.5">⚠</span>
                    <span className="text-text">{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {narrative.dominant_themes?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-line">
              <div className="text-[10px] uppercase text-text-muted mb-1.5">Dominant themes</div>
              <div className="flex flex-wrap gap-1.5">
                {narrative.dominant_themes.slice(0, 6).map((t: any) => (
                  <Tag key={t.theme}>{t.theme} ×{t.hits}</Tag>
                ))}
              </div>
            </div>
          )}
          {narrative.institutional_focus?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-line">
              <div className="text-[10px] uppercase text-text-muted mb-1.5">
                法人聚焦 (連續買超 + 爆量)
              </div>
              <div className="text-xs font-mono space-y-1">
                {narrative.institutional_focus.slice(0, 6).map((f: any) => (
                  <div key={f.symbol} className="flex justify-between">
                    <Link href={`/stock/${f.symbol}`} className="text-text-bright hover:text-accent">
                      {f.symbol} {f.name}
                    </Link>
                    <span className="text-text-muted">
                      外資 {f.foreign_streak}d · 投信 {f.investment_streak}d
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Strategy Rank panel */}
      {strategyRank?.items?.length > 0 && (
        <Card className="col-span-12" icon={<ShieldCheck className="w-3.5 h-3.5" />}
              title="STRATEGY HEALTH"
              subtitle={`${strategyRank.items.length} setups tracked`}>
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-text-muted">
                <th className="text-left py-1">SETUP</th>
                <th className="text-right">RANK</th>
                <th className="text-right">EXP_R</th>
                <th className="text-right">CONSEC L</th>
                <th className="text-right">N</th>
                <th className="text-center">STATUS</th>
              </tr>
            </thead>
            <tbody>
              {strategyRank.items.map((r: any) => (
                <tr key={r.strategy} className="border-t border-line/60">
                  <td className="py-1 text-text-bright">{r.strategy}</td>
                  <td className="text-right text-accent">{Number(r.rank_score).toFixed(3)}</td>
                  <td className={cn("text-right",
                    (r.components?.live_expectancy_R ?? 0) >= 0 ? "text-up" : "text-down")}>
                    {num(r.components?.live_expectancy_R)}
                  </td>
                  <td className="text-right">{r.components?.max_consec_loss ?? 0}</td>
                  <td className="text-right text-text-muted">{r.components?.sample_size ?? 0}</td>
                  <td className="text-center">
                    <span className={cn(
                      "inline-block px-1.5 py-0.5 rounded text-[10px] border",
                      r.production_status === "ACTIVE" ? "text-up border-up/40 bg-up/10"
                      : r.production_status === "WATCH" ? "text-amber-400 border-amber-400/40 bg-amber-400/10"
                      : r.production_status === "DISABLED" ? "text-down border-down/40 bg-down/10"
                      : "text-text-muted border-line bg-bg-elevated/40",
                    )}>{r.production_status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* row 1 — market regime */}
      <Card className="col-span-12 lg:col-span-4" icon={<Activity className="w-3.5 h-3.5" />}
            title="MARKET REGIME" subtitle={`proxy ${brief.market_regime.proxy ?? "—"}`}>
        <RegimeBadge label={brief.market_regime.label} />
        <Kv label="ADX(14)" value={num(brief.market_regime.adx)} />
        <Kv label="EMA200 slope" value={pct(brief.market_regime.ema200_slope_pct, 3)} />
        <Kv label="Reason" value={brief.market_regime.reason} mono={false} />
        <div className="mt-2">
          <div className="text-[10px] uppercase text-text-muted mb-1">Allowed setups</div>
          <div className="flex flex-wrap gap-1">
            {brief.market_regime.allowed_setups.length === 0
              ? <Tag tone="muted">— no LONG setups allowed —</Tag>
              : brief.market_regime.allowed_setups.map((s) => <Tag key={s}>{s}</Tag>)}
          </div>
        </div>
      </Card>

      {/* row 1 — validated signals */}
      <Card className="col-span-12 lg:col-span-8" icon={<ShieldCheck className="w-3.5 h-3.5 text-up" />}
            title="EDGE-VALIDATED SIGNALS" subtitle="actionable · iron-rule passed">
        {brief.top_signals.validated.length === 0 ? (
          <Empty msg="No validated signals today. Use the unvalidated list for research only." />
        ) : (
          <SignalTable rows={brief.top_signals.validated} validated />
        )}
        <div className="mt-2 text-[10px] text-text-muted leading-snug border-t border-line pt-2">
          {brief.top_signals.rule}
        </div>
      </Card>

      {/* row 2 — sector rotation */}
      <Card className="col-span-12 lg:col-span-6" icon={<Layers className="w-3.5 h-3.5" />}
            title="SECTOR ROTATION" subtitle="20d relative strength">
        <table className="w-full text-xs font-mono">
          <thead>
            <tr className="text-text-muted">
              <th className="text-left py-1">#</th>
              <th className="text-left">SECTOR</th>
              <th className="text-right">N</th>
              <th className="text-right">5D</th>
              <th className="text-right">20D</th>
              <th className="text-left pl-3">LEADERS</th>
            </tr>
          </thead>
          <tbody>
            {brief.strongest_sectors.map((s) => (
              <tr key={s.sector} className="border-t border-line/60">
                <td className="py-1 text-text-muted">{s.rs_rank}</td>
                <td className="text-text-bright">{s.sector}</td>
                <td className="text-right text-text-muted">{s.count}</td>
                <td className={cn("text-right", (s.return_5d ?? 0) >= 0 ? "text-up" : "text-down")}>
                  {pct(s.return_5d)}
                </td>
                <td className={cn("text-right", s.return_20d >= 0 ? "text-up" : "text-down")}>
                  {pct(s.return_20d)}
                </td>
                <td className="pl-3 text-text">
                  {s.leaders.slice(0, 3).map((l) => l.symbol).join(" ")}
                </td>
              </tr>
            ))}
            {brief.weakest_sectors.length > 0 && (
              <tr><td colSpan={6} className="pt-2 text-[10px] text-text-muted">弱勢族群</td></tr>
            )}
            {brief.weakest_sectors.map((s) => (
              <tr key={`w-${s.sector}`} className="border-t border-line/30 opacity-70">
                <td className="py-1 text-text-muted">{s.rs_rank}</td>
                <td className="text-text">{s.sector}</td>
                <td className="text-right text-text-muted">{s.count}</td>
                <td className={cn("text-right", (s.return_5d ?? 0) >= 0 ? "text-up" : "text-down")}>{pct(s.return_5d)}</td>
                <td className={cn("text-right", s.return_20d >= 0 ? "text-up" : "text-down")}>{pct(s.return_20d)}</td>
                <td className="pl-3 text-text-muted">{s.leaders.slice(0, 3).map((l) => l.symbol).join(" ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      {/* row 2 — volume anomalies */}
      <Card className="col-span-12 lg:col-span-6" icon={<Flame className="w-3.5 h-3.5 text-up" />}
            title="VOLUME ANOMALIES" subtitle=">= 2× 20d average">
        {brief.volume_anomalies.length === 0 ? (
          <Empty msg="No anomalies today" />
        ) : (
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="text-text-muted">
                <th className="text-left py-1">SYM</th>
                <th className="text-left">NAME</th>
                <th className="text-right">CLOSE</th>
                <th className="text-right">CHG</th>
                <th className="text-right">VOL</th>
                <th className="text-right">× AVG</th>
              </tr>
            </thead>
            <tbody>
              {brief.volume_anomalies.map((v) => (
                <tr key={v.symbol} className="border-t border-line/60">
                  <td className="py-1">
                    <Link href={`/stock/${v.symbol}`} className="text-text-bright hover:text-accent">
                      {v.symbol}
                    </Link>
                  </td>
                  <td className="text-text">{v.name}</td>
                  <td className="text-right">{num(v.close)}</td>
                  <td className={cn("text-right", v.change_pct >= 0 ? "text-up" : "text-down")}>
                    {pct(v.change_pct)}
                  </td>
                  <td className="text-right text-text-muted">
                    {(v.volume / 1000).toFixed(0)}K
                  </td>
                  <td className="text-right text-accent">{num(v.ratio, 1)}x</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {/* row 3 — top leaders + cross-source buzz */}
      <Card className="col-span-12 lg:col-span-6" icon={<TrendingUp className="w-3.5 h-3.5 text-up" />}
            title="CROSS-SECTOR LEADERS" subtitle="top 20d returners">
        <ul className="text-xs font-mono space-y-1">
          {brief.top_leaders.slice(0, 10).map((l) => (
            <li key={l.symbol} className="flex justify-between border-t border-line/40 py-1">
              <span>
                <Link href={`/stock/${l.symbol}`} className="text-text-bright hover:text-accent">
                  {l.symbol}
                </Link>
                <span className="text-text-muted ml-2">{l.sector}</span>
              </span>
              <span className={cn(l.return_20d >= 0 ? "text-up" : "text-down")}>
                {pct(l.return_20d)}
              </span>
            </li>
          ))}
        </ul>
      </Card>

      <Card className="col-span-12 lg:col-span-6" icon={<Hash className="w-3.5 h-3.5" />}
            title="CROSS-SOURCE BUZZ" subtitle="news + PTT + scanner overlap">
        {brief.cross_source_buzz_with_signal.length === 0 ? (
          <Empty msg="No symbol has news + chatter + signal alignment right now" />
        ) : (
          <ul className="text-xs font-mono space-y-1">
            {brief.cross_source_buzz_with_signal.map((b) => (
              <li key={b.symbol} className="flex justify-between border-t border-line/40 py-1">
                <Link href={`/stock/${b.symbol}`} className="text-text-bright hover:text-accent">
                  {b.symbol}
                </Link>
                <span className="text-accent">{b.mentions} mentions</span>
              </li>
            ))}
          </ul>
        )}
        {brief.ptt_hot.hot_keywords.length > 0 && (
          <div className="mt-3 pt-3 border-t border-line">
            <div className="text-[10px] uppercase text-text-muted mb-1">PTT keywords</div>
            <div className="flex flex-wrap gap-1">
              {brief.ptt_hot.hot_keywords.map((k) => (
                <Tag key={k.keyword}>{k.keyword} ×{k.count}</Tag>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* row 4 — news */}
      <Card className="col-span-12" icon={<Newspaper className="w-3.5 h-3.5" />}
            title="MARKET NEWS" subtitle={`${brief.news_headlines.length} headlines (cnyes)`}>
        {brief.news_headlines.length === 0 ? (
          <Empty msg="News feed temporarily unavailable" />
        ) : (
          <ul className="divide-y divide-line">
            {brief.news_headlines.map((n) => (
              <li key={n.id} className="py-2 flex items-start gap-3">
                <span className="font-mono text-[10px] text-text-muted whitespace-nowrap pt-0.5">
                  {new Date(n.published_at).toLocaleTimeString("zh-TW", { hour12: false })}
                </span>
                <div className="flex-1 min-w-0">
                  <a href={n.url} target="_blank" rel="noreferrer"
                     className="text-sm text-text-bright hover:text-accent line-clamp-1">
                    {n.title}
                  </a>
                  {n.mentioned_symbols.length > 0 && (
                    <div className="mt-1 flex gap-1.5 flex-wrap">
                      {n.mentioned_symbols.slice(0, 5).map((s) => (
                        <Link key={s} href={`/stock/${s}`}
                              className="text-[10px] font-mono px-1 rounded bg-bg-elevated/60 text-accent hover:text-text-bright">
                          {s}
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* row 5 — research-only signals */}
      {brief.top_signals.unvalidated.length > 0 && (
        <Card className="col-span-12" icon={<AlertTriangle className="w-3.5 h-3.5 text-text-muted" />}
              title="RESEARCH CANDIDATES" subtitle="unvalidated · sample size below threshold">
          <SignalTable rows={brief.top_signals.unvalidated} validated={false} />
        </Card>
      )}

      {/* row 6 — disabled + disclosure */}
      <Card className="col-span-12" icon={<Cpu className="w-3.5 h-3.5" />}
            title="SYSTEM STATUS"
            subtitle={`disabled setups: ${brief.disabled_setups.length}`}>
        {brief.disabled_setups.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {brief.disabled_setups.map((s) => <Tag key={s} tone="muted">{s}</Tag>)}
          </div>
        ) : (
          <div className="text-xs text-text-muted">All registered setups currently healthy.</div>
        )}
        <p className="mt-3 text-[10px] text-text-muted leading-relaxed">{brief.disclosure}</p>
      </Card>
    </div>
  );
}

// ─────────────────────────── pieces ─────────────────────────────

function Card({ icon, title, subtitle, className, children }: {
  icon: React.ReactNode; title: string; subtitle?: string;
  className?: string; children: React.ReactNode;
}) {
  return (
    <section className={cn("rounded-md border border-line bg-bg-elevated/40", className)}>
      <header className="flex items-center justify-between px-3.5 py-2 border-b border-line">
        <div className="flex items-center gap-2">
          {icon}
          <span className="text-[11px] uppercase tracking-widest font-semibold text-text-bright">{title}</span>
        </div>
        {subtitle && <span className="text-[10px] text-text-muted">{subtitle}</span>}
      </header>
      <div className="p-3.5">{children}</div>
    </section>
  );
}

function Empty({ msg }: { msg: string }) {
  return <div className="text-xs text-text-muted py-2">{msg}</div>;
}

function RegimeBadge({ label }: { label: string }) {
  return (
    <div className={cn(
      "inline-block px-2 py-1 rounded text-[11px] font-mono uppercase tracking-widest border",
      REGIME_TONE[label] ?? REGIME_TONE.unknown,
    )}>
      {label.replace(/_/g, " ")}
    </div>
  );
}

function Kv({ label, value, mono = true }: { label: string; value: string | number | null | undefined; mono?: boolean }) {
  return (
    <div className="flex justify-between text-xs mt-1.5">
      <span className="text-text-muted">{label}</span>
      <span className={cn("text-text-bright", mono && "font-mono")}>{value ?? "—"}</span>
    </div>
  );
}

function Tag({ children, tone = "default" }: { children: React.ReactNode; tone?: "default" | "muted" }) {
  return (
    <span className={cn(
      "inline-block px-1.5 py-0.5 rounded text-[10px] font-mono border",
      tone === "muted"
        ? "border-line bg-bg-elevated/60 text-text-muted"
        : "border-accent/30 bg-accent/10 text-accent",
    )}>
      {children}
    </span>
  );
}

function SignalTable({ rows, validated }: { rows: ScanItem[]; validated: boolean }) {
  if (rows.length === 0) return <Empty msg="—" />;
  return (
    <table className="w-full text-xs font-mono">
      <thead>
        <tr className="text-text-muted">
          <th className="text-left py-1">SYM</th>
          <th className="text-left">SETUP</th>
          <th className="text-right">ENTRY</th>
          <th className="text-right">SL</th>
          <th className="text-right">TP1</th>
          <th className="text-right">RR</th>
          <th className="text-right">CONF</th>
          <th className="text-right">WIN%</th>
          <th className="text-right">EXP_R</th>
          <th className="text-right">N</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.symbol} className="border-t border-line/60">
            <td className="py-1">
              <Link href={`/stock/${r.symbol}`} className="text-text-bright hover:text-accent">
                {r.symbol}
              </Link>
            </td>
            <td className="text-text">{r.setup ?? "—"}</td>
            <td className="text-right">{num(r.entry_zone?.[0])}</td>
            <td className="text-right text-down">{num(r.stop_loss)}</td>
            <td className="text-right text-up">{num(r.take_profit?.[0])}</td>
            <td className="text-right">{num(r.risk_reward)}</td>
            <td className="text-right text-accent">{((r.confidence ?? 0) * 100).toFixed(0)}%</td>
            <td className="text-right">
              {(r as any).validation?.win_rate !== undefined
                ? `${((r as any).validation.win_rate * 100).toFixed(0)}%`
                : "—"}
            </td>
            <td className="text-right">
              {(r as any).validation?.expectancy_r !== undefined
                ? num((r as any).validation.expectancy_r, 2)
                : "—"}
            </td>
            <td className="text-right text-text-muted">
              {(r as any).validation?.sample_size ?? 0}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
