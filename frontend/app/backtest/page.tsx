"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input, Label } from "@/components/ui/Input";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface Strategy { key: string; name: string; description: string; min_plan: string }
interface EquityPoint { date: string; equity: number }
interface BacktestRes {
  symbol: string;
  strategy: string;
  start: string;
  end: string;
  trades: number;
  win_rate: number;
  cagr: number;
  sharpe: number;
  max_drawdown: number;
  total_return: number;
  equity_curve: EquityPoint[];
}

function EquityChart({ data }: { data: EquityPoint[] }) {
  if (!data || data.length < 2) return <div className="h-48 flex items-center justify-center text-text-muted text-xs">資料不足</div>;
  const w = 720, h = 220, pad = 24;
  const xs = data.map((_, i) => i);
  const ys = data.map((d) => d.equity);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const rng = maxY - minY || 1;
  const X = (i: number) => pad + (i / (xs.length - 1)) * (w - 2 * pad);
  const Y = (v: number) => h - pad - ((v - minY) / rng) * (h - 2 * pad);
  const path = data.map((d, i) => `${i === 0 ? "M" : "L"} ${X(i).toFixed(2)} ${Y(d.equity).toFixed(2)}`).join(" ");
  const last = data[data.length - 1].equity;
  const first = data[0].equity;
  const up = last >= first;
  const stroke = up ? "#26A69A" : "#EF5350";
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-56">
      <defs>
        <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path} L ${X(xs.length - 1)} ${h - pad} L ${X(0)} ${h - pad} Z`} fill="url(#eq)" />
      <path d={path} fill="none" stroke={stroke} strokeWidth="2" />
    </svg>
  );
}

function pct(n: number) {
  return `${(n * 100).toFixed(2)}%`;
}

export default function BacktestPage() {
  const { user, loading } = useAuth();
  const [strategies, setStrategies] = useState<Strategy[] | null>(null);
  const [symbol, setSymbol] = useState("2330");
  const [start, setStart] = useState("2025-01-01");
  const [end, setEnd] = useState("2025-12-31");
  const [strategy, setStrategy] = useState("ai_top_rank");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestRes | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [gated, setGated] = useState(false);

  useEffect(() => {
    api.strategies().then(setStrategies).catch(() => setStrategies([]));
  }, []);

  async function run() {
    setError(null); setGated(false); setResult(null); setRunning(true);
    try {
      const r = await api.runBacktest({ symbol, start, end, strategy });
      setResult(r as BacktestRes);
    } catch (e) {
      const err = e as { status?: number; message?: string };
      if (err.status === 402 || err.status === 403) setGated(true);
      else setError(err.message || "執行失敗");
    } finally {
      setRunning(false);
    }
  }

  const eliteOnly = !loading && user && user.plan !== "elite" && !user.is_admin;

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-6xl mx-auto px-6 py-8 space-y-6">
        <header>
          <h1 className="text-2xl font-semibold text-text-bright tracking-tight">回測中心</h1>
          <p className="text-xs text-text-muted mt-1">
            遵循鐵律：手續費 0.05% / 滑點 0.05% / 停損 5% / R:R 1.3 / 日熔斷 9%
          </p>
        </header>

        {(gated || (!loading && !user)) && (
          <Card className="border-accent/40 bg-accent/5 p-5 text-sm">
            <div className="font-semibold text-text-bright mb-1">需要 Elite 方案才能執行回測</div>
            <p className="text-text-muted">
              {user
                ? "升級到 Elite 方案以解鎖完整回測中心。"
                : "請先登入並升級到 Elite 方案。"}
            </p>
            <div className="mt-3 flex gap-2">
              <Link href="/pricing"><Button>查看方案</Button></Link>
              {!user && <Link href="/login"><Button variant="secondary">登入</Button></Link>}
            </div>
          </Card>
        )}

        <Card>
          <CardHeader title="設定" subtitle="選擇標的、區間與策略" />
          <div className="p-6 grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="md:col-span-1">
              <Label htmlFor="sym">代號</Label>
              <Input id="sym" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="2330" />
            </div>
            <div>
              <Label htmlFor="start">開始</Label>
              <Input id="start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="end">結束</Label>
              <Input id="end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
            </div>
            <div className="md:col-span-2">
              <Label htmlFor="strategy">策略</Label>
              <select
                id="strategy"
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="w-full h-9 rounded-md bg-bg-elevated border border-line px-3 text-sm text-text-bright"
              >
                {(strategies ?? []).map((s) => (
                  <option key={s.key} value={s.key}>{s.name}</option>
                ))}
                {!strategies && <option>載入中…</option>}
              </select>
            </div>
            <div className="md:col-span-5 flex items-center gap-3 pt-2">
              <Button onClick={run} disabled={running || !!eliteOnly} size="lg">
                {running ? "回測中…" : "執行回測"}
              </Button>
              {strategy && strategies && (
                <span className="text-xs text-text-muted">
                  {strategies.find((s) => s.key === strategy)?.description}
                </span>
              )}
            </div>
            {error && <div className="md:col-span-5 text-down text-sm">{error}</div>}
          </div>
        </Card>

        {running && <Skeleton className="h-72" />}

        {result && (
          <>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              {[
                { label: "總報酬", value: pct(result.total_return), color: result.total_return >= 0 ? "text-up" : "text-down" },
                { label: "年化 (CAGR)", value: pct(result.cagr), color: result.cagr >= 0 ? "text-up" : "text-down" },
                { label: "Sharpe", value: result.sharpe.toFixed(2), color: "text-text-bright" },
                { label: "最大回撤", value: pct(result.max_drawdown), color: "text-down" },
                { label: "勝率 / 交易", value: `${(result.win_rate * 100).toFixed(0)}% · ${result.trades}`, color: "text-text-bright" },
              ].map((s) => (
                <Card key={s.label} className="p-4">
                  <div className="text-[11px] uppercase tracking-wider text-text-muted">{s.label}</div>
                  <div className={cn("mt-1.5 text-2xl font-semibold font-mono", s.color)}>{s.value}</div>
                </Card>
              ))}
            </div>

            <Card>
              <CardHeader title="權益曲線" subtitle={`${result.symbol} · ${result.strategy} · ${result.start} → ${result.end}`} />
              <div className="p-4">
                <EquityChart data={result.equity_curve} />
              </div>
            </Card>
          </>
        )}
      </main>
    </div>
  );
}
