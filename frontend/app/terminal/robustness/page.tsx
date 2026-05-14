"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, Layers, GitBranch, Zap, ShieldCheck } from "lucide-react";

import { Topbar } from "@/components/layout/Topbar";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

function num(v: any, d = 2) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return Number(v).toFixed(d);
}
function pct(v: any, d = 0) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return `${(Number(v) * 100).toFixed(d)}%`;
}

const STATUS_TONE: Record<string, string> = {
  ACTIVE: "text-up border-up/40 bg-up/10",
  RESEARCH_ONLY: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  WATCH: "text-amber-400 border-amber-400/40 bg-amber-400/10",
  DISABLED: "text-down border-down/40 bg-down/10",
  UNKNOWN: "text-text-muted border-line bg-bg-elevated/40",
};

export default function RobustnessPage() {
  const [quality, setQuality] = useState<any>(null);
  const [corr, setCorr] = useState<any>(null);
  const [pers, setPers] = useState<any>(null);
  const [risk, setRisk] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([
      api.qualityReport(),
      api.correlationMatrix(90),
      api.edgePersistence(90),
      api.riskAllocation("trending_up"),
    ]).then(([q, c, p, r]) => {
      if (!alive) return;
      setQuality(q); setCorr(c); setPers(p); setRisk(r);
    }).catch((e) => alive && setErr(e instanceof Error ? e.message : "load failed"));
    return () => { alive = false; };
  }, []);

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-[1600px] mx-auto px-5 py-5 space-y-5">
        <header className="flex items-baseline justify-between border-b border-line pb-3">
          <div>
            <h1 className="text-xl font-semibold text-text-bright tracking-tight">
              Strategy Robustness
            </h1>
            <p className="text-[11px] text-text-muted mt-1">
              抗過擬合驗證 · cross-regime + correlation + persistence + quality gates
            </p>
          </div>
          <nav className="flex gap-3 text-[11px] font-mono uppercase tracking-widest">
            <Link href="/terminal" className="text-text-muted hover:text-text">Brief</Link>
            <Link href="/terminal/performance" className="text-text-muted hover:text-text">Performance</Link>
            <span className="text-accent border-b border-accent pb-0.5">Robustness</span>
          </nav>
        </header>

        {err && <div className="text-down text-sm">{err}</div>}

        <Panel icon={<ShieldCheck className="w-3.5 h-3.5" />}
               title="RESEARCH QUALITY VERDICT"
               subtitle="composite gate · ACTIVE / RESEARCH_ONLY / DISABLED">
          {quality?.items?.length ? (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-text-muted">
                  <th className="text-left py-1">STRATEGY</th>
                  <th className="text-right">SCORE</th>
                  <th className="text-right">SAMPLE</th>
                  <th className="text-right">OVERFIT_R</th>
                  <th className="text-right">REGIME_S</th>
                  <th className="text-right">CORR</th>
                  <th className="text-right">DECAY</th>
                  <th className="text-right">ROBUST</th>
                  <th className="text-center">STATUS</th>
                </tr>
              </thead>
              <tbody>
                {quality.items.map((q: any) => (
                  <tr key={q.strategy} className="border-t border-line/60">
                    <td className="py-1 text-text-bright">{q.strategy}</td>
                    <td className="text-right text-accent">{num(q.production_research_score, 3)}</td>
                    <td className="text-right">{num(q.components.sample_quality)}</td>
                    <td className="text-right">{num(q.components.overfit_resistance)}</td>
                    <td className="text-right">{num(q.components.regime_stability)}</td>
                    <td className="text-right">{num(q.components.correlation_health)}</td>
                    <td className="text-right">{num(q.components.decay_score)}</td>
                    <td className="text-right">{num(q.components.robustness_score)}</td>
                    <td className="text-center">
                      <span className={cn(
                        "inline-block px-1.5 py-0.5 rounded text-[10px] border",
                        STATUS_TONE[q.research_status] ?? STATUS_TONE.UNKNOWN,
                      )}>{q.research_status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty msg="尚無 quality 資料" />}
        </Panel>

        <div className="grid grid-cols-12 gap-4">
          <Panel className="col-span-12 lg:col-span-6"
                 icon={<GitBranch className="w-3.5 h-3.5" />}
                 title="STRATEGY CORRELATION"
                 subtitle={`window ${corr?.window_days ?? 90}D`}>
            {corr?.pairs?.length ? (
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-text-muted">
                    <th className="text-left py-1">PAIR</th>
                    <th className="text-right">RET_R</th>
                    <th className="text-right">DD_OL</th>
                    <th className="text-right">SIG_OL</th>
                    <th className="text-center">FLAG</th>
                  </tr>
                </thead>
                <tbody>
                  {corr.pairs.map((p: any, i: number) => (
                    <tr key={i} className="border-t border-line/60">
                      <td className="py-1 text-text">{p.a} × {p.b}</td>
                      <td className={cn("text-right",
                        Math.abs(p.return_corr) > 0.5 ? "text-amber-400" : "")}>
                        {num(p.return_corr)}
                      </td>
                      <td className="text-right">{num(p.drawdown_overlap)}</td>
                      <td className="text-right">{num(p.signal_overlap)}</td>
                      <td className="text-center">
                        {p.flagged ? (
                          <span className="inline-block px-1.5 py-0.5 rounded text-[10px] border text-down border-down/40 bg-down/10">
                            FLAGGED
                          </span>
                        ) : (
                          <span className="text-text-muted">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty msg="尚無足夠資料計算相關性" />}
            {corr?.flagged_pairs?.length > 0 && (
              <p className="mt-2 text-[10px] text-amber-400">
                ⚠ {corr.flagged_pairs.length} 組策略可能本質相同，建議只保留 rank 較高者
              </p>
            )}
          </Panel>

          <Panel className="col-span-12 lg:col-span-6"
                 icon={<Zap className="w-3.5 h-3.5" />}
                 title="EDGE PERSISTENCE"
                 subtitle="half-life + decay velocity">
            {pers && Object.keys(pers).length > 0 ? (
              <table className="w-full text-xs font-mono">
                <thead>
                  <tr className="text-text-muted">
                    <th className="text-left py-1">SETUP</th>
                    <th className="text-right">N</th>
                    <th className="text-right">HALF-LIFE (D)</th>
                    <th className="text-right">VELOCITY</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(pers).map(([setup, d]: [string, any]) => (
                    <tr key={setup} className="border-t border-line/60">
                      <td className="py-1 text-text-bright">{setup}</td>
                      <td className="text-right text-text-muted">{d.sample_size}</td>
                      <td className="text-right">
                        {d.half_life_days != null ? num(d.half_life_days) : "∞"}
                      </td>
                      <td className={cn("text-right",
                        d.decay_velocity >= 0 ? "text-up" : "text-down")}>
                        {(d.decay_velocity >= 0 ? "+" : "") + num(d.decay_velocity, 3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <Empty msg="尚無足夠樣本估算 half-life" />}
            <p className="mt-2 text-[10px] text-text-muted">
              half-life: edge 預期維持多久 (天)。velocity 為負 = 衰退中。
            </p>
          </Panel>
        </div>

        <Panel icon={<Layers className="w-3.5 h-3.5" />}
               title="RISK ALLOCATION (trending_up)"
               subtitle={`regime modifier ${risk?.regime_modifier ?? '—'} · base risk ${pct(risk?.base_risk_pct, 1)} · max concurrent ${risk?.max_concurrent ?? '—'}`}>
          {risk?.allocations?.length ? (
            <table className="w-full text-xs font-mono">
              <thead>
                <tr className="text-text-muted">
                  <th className="text-left py-1">STRATEGY</th>
                  <th className="text-right">WEIGHT</th>
                  <th className="text-right">MAX EXPOSURE</th>
                  <th className="text-right">SIGNAL RISK</th>
                  <th className="text-center">STATUS</th>
                </tr>
              </thead>
              <tbody>
                {risk.allocations.map((a: any) => (
                  <tr key={a.strategy} className="border-t border-line/60">
                    <td className="py-1 text-text-bright">{a.strategy}</td>
                    <td className="text-right text-accent">{pct(a.weight, 1)}</td>
                    <td className="text-right">{pct(a.max_exposure_pct, 1)}</td>
                    <td className="text-right">{pct(a.per_signal_risk_pct, 2)}</td>
                    <td className="text-center">
                      <span className={cn(
                        "inline-block px-1.5 py-0.5 rounded text-[10px] border",
                        STATUS_TONE[a.production_status] ?? STATUS_TONE.UNKNOWN,
                      )}>{a.production_status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty />}
          {risk?.notes?.length > 0 && (
            <div className="mt-3 pt-3 border-t border-line space-y-1 text-[10px] text-text-muted">
              {risk.notes.map((n: string, i: number) => <div key={i}>· {n}</div>)}
            </div>
          )}
        </Panel>

        <p className="text-[11px] text-text-muted leading-relaxed border-t border-line pt-3">
          所有指標均從 edge_signals 真實表現匯出。Quality gate 阻擋 score &lt; 0.65
          的策略進入 production；correlation 高度重疊的策略系統會自動降權；
          edge persistence 衰退過快的策略將被標記為 broken。
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

function Empty({ msg = "—" }: { msg?: string }) {
  return <div className="text-xs text-text-muted py-2">{msg}</div>;
}
