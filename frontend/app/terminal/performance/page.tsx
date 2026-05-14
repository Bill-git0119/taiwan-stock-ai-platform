"use client";

import { useEffect, useState } from "react";
import { Activity, BarChart3, ShieldCheck, TrendingDown, Cpu } from "lucide-react";

import { Topbar } from "@/components/layout/Topbar";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const WINDOWS = [7, 30, 90] as const;
type Window = (typeof WINDOWS)[number];

function num(v: any, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(digits);
}
function pct(v: any, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return `${(Number(v) * 100).toFixed(digits)}%`;
}

const STATUS_TONE: Record<string, string> = {
  ACTIVE: "text-up border-up/40 bg-up/10",
  WATCH: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  DISABLED: "text-down border-down/40 bg-down/10",
  UNKNOWN: "text-text-muted border-line bg-bg-elevated/40",
};

export default function PerformancePage() {
  const [window, setWindow] = useState<Window>(30);
  const [snap, setSnap] = useState<any>(null);
  const [rank, setRank] = useState<any>(null);
  const [matrix, setMatrix] = useState<any>(null);
  const [decay, setDecay] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.performanceSnapshot(window),
      api.strategyRank(),
      api.performanceSetupXRegime(),
      api.performanceDecay(),
    ]).then(([s, r, m, d]) => {
      if (!alive) return;
      setSnap(s); setRank(r); setMatrix(m); setDecay(d);
    }).catch((e) => alive && setErr(e instanceof Error ? e.message : "load failed"));
    return () => { alive = false; };
  }, [window]);

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-[1600px] mx-auto px-5 py-5 space-y-5">
        <header className="flex items-baseline justify-between border-b border-line pb-3">
          <div>
            <h1 className="text-xl font-semibold text-text-bright tracking-tight">
              Live Edge Performance
            </h1>
            <p className="text-[11px] text-text-muted mt-1">
              真實 signal 績效 · 來源僅限 edge_signals.evaluated=true · 無回測數據混入
            </p>
          </div>
          <div className="flex gap-1.5">
            {WINDOWS.map((w) => (
              <button key={w} onClick={() => setWindow(w)}
                className={cn(
                  "px-2.5 py-1 rounded font-mono text-[11px] border transition",
                  w === window
                    ? "border-accent text-accent bg-accent/10"
                    : "border-line text-text-muted hover:text-text",
                )}>
                {w}D
              </button>
            ))}
          </div>
        </header>

        {err && <div className="text-down text-sm">{err}</div>}

        {/* row 1 — overall + ranker status */}
        <div className="grid grid-cols-12 gap-4">
          <Panel className="col-span-12 lg:col-span-4"
                 icon={<Activity className="w-3.5 h-3.5" />}
                 title="OVERALL" subtitle={`window ${window}D`}>
            {snap?.overall ? <OverallStats stats={snap.overall} /> : <Empty />}
          </Panel>

          <Panel className="col-span-12 lg:col-span-8"
                 icon={<ShieldCheck className="w-3.5 h-3.5" />}
                 title="STRATEGY RANK" subtitle="composite · production gate">
            {rank?.items?.length ? (
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-text-muted">
                    <th className="text-left py-1">SETUP</th>
                    <th className="text-right">RANK</th>
                    <th className="text-right">SHARPE</th>
                    <th className="text-right">PF</th>
                    <th className="text-right">EXP_R</th>
                    <th className="text-right">CONSEC L</th>
                    <th className="text-right">N</th>
                    <th className="text-center">STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {rank.items.map((r: any) => (
                    <tr key={r.strategy} className="border-t border-line/60">
                      <td className="py-1 text-text-bright">{r.strategy}</td>
                      <td className="text-right text-accent">{num(r.rank_score, 3)}</td>
                      <td className="text-right">{num(r.components?.oos_sharpe)}</td>
                      <td className="text-right">{num(r.components?.live_pf || r.components?.oos_pf)}</td>
                      <td className={cn("text-right",
                        (r.components?.live_expectancy_R ?? 0) >= 0 ? "text-up" : "text-down")}>
                        {num(r.components?.live_expectancy_R)}
                      </td>
                      <td className="text-right">{r.components?.max_consec_loss ?? 0}</td>
                      <td className="text-right text-text-muted">{r.components?.sample_size ?? 0}</td>
                      <td className="text-center">
                        <span className={cn(
                          "inline-block px-1.5 py-0.5 rounded text-[10px] border",
                          STATUS_TONE[r.production_status] ?? STATUS_TONE.UNKNOWN,
                        )}>{r.production_status}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty />}
          </Panel>
        </div>

        {/* row 2 — breakdowns */}
        <div className="grid grid-cols-12 gap-4">
          <Panel className="col-span-12 lg:col-span-6"
                 icon={<BarChart3 className="w-3.5 h-3.5" />}
                 title="BY SETUP" subtitle="real signal performance">
            <BreakdownTable rows={snap?.by_setup} keyName="setup" />
          </Panel>
          <Panel className="col-span-12 lg:col-span-6"
                 icon={<BarChart3 className="w-3.5 h-3.5" />}
                 title="BY REGIME" subtitle="performance per market state">
            <BreakdownTable rows={snap?.by_regime} keyName="regime" />
          </Panel>
        </div>

        <Panel icon={<BarChart3 className="w-3.5 h-3.5" />}
               title="BY SECTOR" subtitle="performance per sector">
          <BreakdownTable rows={snap?.by_sector} keyName="sector" />
        </Panel>

        {/* row 3 — setup × regime matrix */}
        <Panel icon={<BarChart3 className="w-3.5 h-3.5" />}
               title="SETUP × REGIME MATRIX"
               subtitle="expectancy_R per (setup, regime) · 90D window">
          {matrix?.matrix ? <SetupRegimeMatrix matrix={matrix.matrix} /> : <Empty />}
        </Panel>

        {/* row 4 — decay */}
        <Panel icon={<TrendingDown className="w-3.5 h-3.5" />}
               title="EDGE DECAY" subtitle="recent vs older expectancy">
          {decay && Object.keys(decay).length > 0 ? (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-text-muted">
                  <th className="text-left py-1">SETUP</th>
                  <th className="text-right">RECENT_R</th>
                  <th className="text-right">OLDER_R</th>
                  <th className="text-right">DECAY</th>
                  <th className="text-right">N_RECENT</th>
                  <th className="text-center">LABEL</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(decay).map(([setup, d]: [string, any]) => (
                  <tr key={setup} className="border-t border-line/60">
                    <td className="py-1 text-text-bright">{setup}</td>
                    <td className={cn("text-right",
                      d.recent_expectancy_R >= 0 ? "text-up" : "text-down")}>
                      {num(d.recent_expectancy_R)}
                    </td>
                    <td className="text-right text-text-muted">{num(d.older_expectancy_R)}</td>
                    <td className={cn("text-right",
                      d.decay >= 0 ? "text-up" : "text-down")}>
                      {d.decay > 0 ? "+" : ""}{num(d.decay)}
                    </td>
                    <td className="text-right">{d.recent_n}</td>
                    <td className="text-center">
                      <DecayBadge label={d.label} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty msg="尚無足夠 edge_signals 計算 decay" />}
        </Panel>

        <p className="text-[11px] text-text-muted leading-relaxed border-t border-line pt-3">
          資料來源：edge_signals 表（已 walk-forward 評估的真實訊號）。
          回測數據（lab metrics）僅用於 strategy rank 加權，從不作為績效呈現。
        </p>
      </main>
    </div>
  );
}

function Panel({ icon, title, subtitle, className, children }: {
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

function Empty({ msg = "尚無資料" }: { msg?: string }) {
  return <div className="text-xs text-text-muted py-2">{msg}</div>;
}

function OverallStats({ stats }: { stats: any }) {
  return (
    <div className="grid grid-cols-2 gap-y-2 text-xs">
      {[
        ["Sample size", stats.sample_size],
        ["Win rate", pct(stats.win_rate)],
        ["Profit factor", num(stats.profit_factor)],
        ["Expectancy R", num(stats.expectancy_R)],
        ["Avg R", num(stats.avg_R)],
        ["Max consec loss", stats.max_consec_loss],
        ["Avg MFE R", num(stats.avg_mfe_R)],
        ["Avg MAE R", num(stats.avg_mae_R)],
        ["Avg bars held", num(stats.avg_bars_held)],
      ].map(([k, v]) => (
        <div key={k as string} className="flex justify-between border-b border-line/40 pb-1">
          <span className="text-text-muted">{k}</span>
          <span className="text-text-bright font-mono">{v}</span>
        </div>
      ))}
    </div>
  );
}

function BreakdownTable({ rows, keyName }: { rows: Record<string, any> | undefined; keyName: string }) {
  if (!rows || Object.keys(rows).length === 0) return <Empty />;
  const entries = Object.entries(rows).sort(
    (a, b) => (b[1].expectancy_R ?? 0) - (a[1].expectancy_R ?? 0),
  );
  return (
    <table className="w-full text-xs font-mono">
      <thead>
        <tr className="text-text-muted">
          <th className="text-left py-1">{keyName.toUpperCase()}</th>
          <th className="text-right">N</th>
          <th className="text-right">WIN%</th>
          <th className="text-right">PF</th>
          <th className="text-right">EXP_R</th>
          <th className="text-right">MFE_R</th>
          <th className="text-right">MAE_R</th>
        </tr>
      </thead>
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="border-t border-line/60">
            <td className="py-1 text-text-bright">{k}</td>
            <td className="text-right">{v.sample_size}</td>
            <td className="text-right">{pct(v.win_rate)}</td>
            <td className="text-right">{num(v.profit_factor)}</td>
            <td className={cn("text-right",
              (v.expectancy_R ?? 0) >= 0 ? "text-up" : "text-down")}>
              {num(v.expectancy_R)}
            </td>
            <td className="text-right text-up">{num(v.avg_mfe_R)}</td>
            <td className="text-right text-down">{num(v.avg_mae_R)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SetupRegimeMatrix({ matrix }: { matrix: Record<string, Record<string, any>> }) {
  const setups = Object.keys(matrix);
  if (setups.length === 0) return <Empty />;
  const regimes = Array.from(
    new Set(setups.flatMap((s) => Object.keys(matrix[s])))
  ).sort();
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="text-text-muted">
            <th className="text-left py-1">SETUP \ REGIME</th>
            {regimes.map((r) => <th key={r} className="text-right px-2">{r}</th>)}
          </tr>
        </thead>
        <tbody>
          {setups.map((s) => (
            <tr key={s} className="border-t border-line/60">
              <td className="py-1 text-text-bright">{s}</td>
              {regimes.map((r) => {
                const cell = matrix[s][r];
                if (!cell) return <td key={r} className="text-right text-text-muted px-2">—</td>;
                const exp = cell.expectancy_R ?? 0;
                return (
                  <td key={r} className={cn(
                    "text-right px-2",
                    exp > 0 ? "text-up" : exp < 0 ? "text-down" : "text-text-muted",
                  )}>
                    {num(exp)} <span className="text-[10px] text-text-muted">({cell.sample_size})</span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DecayBadge({ label }: { label: string }) {
  const tone: Record<string, string> = {
    improving: "text-up border-up/40 bg-up/10",
    stable: "text-text-muted border-line bg-bg-elevated/40",
    decaying: "text-amber-400 border-amber-400/40 bg-amber-400/10",
    broken: "text-down border-down/40 bg-down/10",
  };
  return (
    <span className={cn(
      "inline-block px-1.5 py-0.5 rounded text-[10px] uppercase border",
      tone[label] ?? tone.stable,
    )}>
      {label}
    </span>
  );
}
