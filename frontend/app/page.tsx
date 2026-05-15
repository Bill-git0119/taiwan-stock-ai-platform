import Link from "next/link";
import { Activity, Brain, LineChart, Search, TrendingUp, Zap } from "lucide-react";
import { Topbar } from "@/components/layout/Topbar";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "Taiwan Stock AI · Local Research Desk",
  description: "Local quant research workstation for Taiwan equities.",
};

const ENTRY_POINTS = [
  {
    href: "/terminal",
    icon: Brain,
    title: "AI Trading Terminal",
    desc: "盤後 brief · regime · breadth · validated signals · 法人聚焦",
  },
  {
    href: "/scanner",
    icon: Zap,
    title: "強勢股 Scanner",
    desc: "全宇宙跑 trade-plan 引擎 · 鐵律過濾 · RS / 族群排名",
  },
  {
    href: "/dashboard",
    icon: Activity,
    title: "Dashboard",
    desc: "TOP-10 · 市場概況 · 漲跌幅 / 量能 / 突破 movers",
  },
  {
    href: "/backtest",
    icon: LineChart,
    title: "Backtest",
    desc: "Walk-forward · friction · 鐵律下的真實績效",
  },
  {
    href: "/terminal/performance",
    icon: TrendingUp,
    title: "Performance",
    desc: "edge_signals 真實統計 · setup × regime × sector 切片",
  },
  {
    href: "/terminal/robustness",
    icon: Search,
    title: "Robustness",
    desc: "Quality gate · correlation · 半衰期 · production status",
  },
];

export default function HomePage() {
  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-6xl mx-auto px-6 py-10">
        <header className="mb-10">
          <div className="inline-flex items-center gap-2 px-2 py-0.5 rounded border border-line bg-bg-panel text-[10px] uppercase tracking-widest text-text-muted mb-3">
            <span className="w-1.5 h-1.5 rounded-full bg-up animate-pulse" />
            Local single-user research desk
          </div>
          <h1 className="text-3xl md:text-4xl font-semibold text-text-bright tracking-tight">
            Taiwan Stock AI <span className="text-accent">Research Desk</span>
          </h1>
          <p className="mt-2 text-sm text-text-muted leading-relaxed max-w-2xl">
            盤後資料 → regime → 強勢股 setup → 風險管控的整套工作流。
            純本機運作；不展示無 edge 的訊號；不偽造績效。
          </p>
        </header>

        <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {ENTRY_POINTS.map((p) => (
            <Link key={p.href} href={p.href}
                  className="block rounded-md border border-line bg-bg-panel/40 p-4 hover:border-accent/40 hover:bg-bg-panel transition-colors">
              <div className="flex items-center gap-2 mb-1.5">
                <p.icon className="w-4 h-4 text-accent" />
                <h2 className="text-sm font-semibold text-text-bright">{p.title}</h2>
              </div>
              <p className="text-xs text-text-muted leading-relaxed">{p.desc}</p>
            </Link>
          ))}
        </section>

        <footer className="mt-12 pt-6 border-t border-line text-[11px] text-text-muted leading-relaxed">
          <div className="font-mono">
            iron rules · RR ≥ 1.5 · risk ≤ 1% · friction 0.10% round-trip ·
            stop is hard · no lookahead · real data only
          </div>
          <div className="mt-1">
            data: TWSE / TPEX / MOPS / yfinance · 此工作站僅供研究，不構成投資建議
          </div>
        </footer>
      </main>
    </div>
  );
}
