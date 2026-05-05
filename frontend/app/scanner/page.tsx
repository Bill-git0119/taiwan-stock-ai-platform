"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Filter, Flame, RefreshCw, Sparkles, TrendingUp, Zap } from "lucide-react";

import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { api, type ScanItem, type ScanResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const SETUP_LABEL: Record<string, string> = {
  trend_breakout_retest: "突破回踩",
  ma20_support_bounce: "MA20 支撐反彈",
  chip_follow_long: "籌碼跟單",
};

type FilterMode = "actionable" | "long" | "all";

const FILTER_PRESETS: Record<FilterMode, { label: string; bias?: "LONG"; min_rr?: number; min_confidence?: number }> = {
  actionable: { label: "可進場 (LONG · RR≥1.5)", bias: "LONG", min_rr: 1.5 },
  long: { label: "全部 LONG 訊號", bias: "LONG" },
  all: { label: "全市場 (含 NO_TRADE)" },
};

export default function ScannerPage() {
  const [mode, setMode] = useState<FilterMode>("actionable");
  const [setup, setSetup] = useState<string>("");
  const [data, setData] = useState<ScanResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    const preset = FILTER_PRESETS[mode];
    api.scan({
      bias: preset.bias,
      min_rr: preset.min_rr,
      min_confidence: preset.min_confidence,
      setup: setup || undefined,
      limit: 100,
    })
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : "fetch failed"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [mode, setup, refreshTick]);

  const items = data?.items ?? [];
  const longCount = useMemo(() => items.filter((i) => i.bias === "LONG").length, [items]);

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <section className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-text-bright tracking-tight inline-flex items-center gap-2">
              <Zap className="w-6 h-6 text-accent" />
              強勢股 Scanner
            </h1>
            <p className="text-xs text-text-muted mt-1">
              整個 universe 跑一次 trade-plan 引擎 · 鐵律過濾 · 依 edge score 排序
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => setRefreshTick((n) => n + 1)} className="gap-1.5">
            <RefreshCw className={cn("w-3.5 h-3.5", loading && "animate-spin")} />
            重新掃描
          </Button>
        </section>

        {/* Filter bar */}
        <Card className="p-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex items-center gap-1.5 text-[11px] uppercase tracking-widest text-text-muted">
              <Filter className="w-3.5 h-3.5" /> 篩選
            </div>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(FILTER_PRESETS) as FilterMode[]).map((k) => (
                <button
                  key={k}
                  onClick={() => setMode(k)}
                  className={cn(
                    "px-3 py-1.5 rounded-md text-xs font-medium transition-colors border",
                    mode === k
                      ? "bg-accent/15 text-accent border-accent/40"
                      : "bg-bg-elevated text-text-muted border-line hover:text-text-bright",
                  )}
                >
                  {FILTER_PRESETS[k].label}
                </button>
              ))}
            </div>
            <div className="ml-auto flex items-center gap-2">
              <select
                value={setup}
                onChange={(e) => setSetup(e.target.value)}
                className="bg-bg-elevated border border-line rounded-md px-3 py-1.5 text-xs text-text-bright focus:border-accent outline-none"
              >
                <option value="">全部 Setup</option>
                <option value="trend_breakout_retest">突破回踩</option>
                <option value="ma20_support_bounce">MA20 支撐反彈</option>
                <option value="chip_follow_long">籌碼跟單</option>
              </select>
            </div>
          </div>

          {data && (
            <div className="mt-3 pt-3 border-t border-line flex flex-wrap items-center gap-4 text-xs text-text-muted">
              <span>掃描 <span className="text-text-bright font-mono">{data.scanned}</span> 檔</span>
              <span>·</span>
              <span>命中 <span className="text-up font-mono font-semibold">{data.matched}</span> 檔</span>
              <span>·</span>
              <span>LONG: <span className="text-up font-mono">{longCount}</span></span>
            </div>
          )}
        </Card>

        {/* Results */}
        <Card>
          <CardHeader
            title="掃描結果"
            subtitle="Edge = confidence×60 + min(RR,4)×5 + 突破×8 + 量倍率 + 籌碼連續度"
            right={
              <span className="text-[10px] uppercase tracking-widest text-text-muted">
                Sorted by Edge Score
              </span>
            }
          />

          {error && (
            <div className="p-8 text-center text-down text-sm">
              掃描失敗: {error}
            </div>
          )}
          {loading && !data && (
            <div className="p-5 space-y-2">
              {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12" />)}
            </div>
          )}
          {!loading && items.length === 0 && !error && (
            <div className="p-10 text-center text-sm text-text-muted">
              <Sparkles className="w-6 h-6 mx-auto mb-2 opacity-40" />
              此篩選條件下沒有符合的標的<br />
              <span className="text-[11px]">— 鐵律生效中：RR&lt;1.5 或無結構訊號的標的會被自動過濾 —</span>
            </div>
          )}
          {items.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm min-w-[1100px]">
                <thead className="text-[11px] uppercase tracking-wider text-text-muted bg-bg-elevated/40">
                  <tr>
                    <th className="text-left  font-medium px-4 py-2.5">#</th>
                    <th className="text-left  font-medium py-2.5">代號 / 名稱</th>
                    <th className="text-left  font-medium py-2.5">Bias</th>
                    <th className="text-left  font-medium py-2.5">Setup</th>
                    <th className="text-right font-medium py-2.5">收盤</th>
                    <th className="text-right font-medium py-2.5">進場</th>
                    <th className="text-right font-medium py-2.5">停損</th>
                    <th className="text-right font-medium py-2.5">TP1 / TP2</th>
                    <th className="text-right font-medium py-2.5">RR</th>
                    <th className="text-right font-medium py-2.5">RSI</th>
                    <th className="text-right font-medium py-2.5">Vol×</th>
                    <th className="text-right font-medium py-2.5">信心</th>
                    <th className="text-right font-medium px-4 py-2.5">Edge</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((it, i) => (
                    <ScanRow key={it.symbol} item={it} rank={i + 1} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <p className="text-[11px] text-text-muted text-center">
          ⚠️ 掃描結果僅供參考，請以你的資金管理紀律執行。
          交易鐵律：每筆風險 ≤ 1% 帳戶資金 · RR ≥ 1.5 才進場 · 停損為硬規則。
        </p>
      </main>
    </div>
  );
}

function ScanRow({ item, rank }: { item: ScanItem; rank: number }) {
  const isLong = item.bias === "LONG";
  const ind = item.indicators ?? {};
  const rsi = ind.rsi14 as number | undefined;
  const vol = ind.volume_spike as number | undefined;

  return (
    <tr className="border-t border-line hover:bg-bg-elevated/60 transition-colors group">
      <td className="px-4 py-3 mono text-text-muted">{String(rank).padStart(2, "0")}</td>
      <td className="py-3">
        <Link href={`/stock/${item.symbol}`} className="block group-hover:text-accent">
          <div className="flex items-baseline gap-2">
            <span className="mono text-text-bright font-semibold">{item.symbol}</span>
            <span className="text-xs">{item.name}</span>
          </div>
        </Link>
      </td>
      <td className="py-3">
        <BiasBadge bias={item.bias} reason={item.no_trade_reason ?? undefined} />
      </td>
      <td className="py-3 text-xs">
        {item.setup ? (
          <span className="px-2 py-0.5 rounded bg-accent/10 text-accent border border-accent/30 text-[10px] uppercase tracking-wider">
            {SETUP_LABEL[item.setup] ?? item.setup}
          </span>
        ) : <span className="text-text-muted">—</span>}
      </td>
      <td className="py-3 text-right mono text-text-bright">
        {item.last_close?.toFixed(2) ?? "—"}
      </td>
      <td className="py-3 text-right mono text-xs">
        {isLong && item.entry_zone
          ? `${item.entry_zone[0].toFixed(2)}–${item.entry_zone[1].toFixed(2)}`
          : "—"}
      </td>
      <td className="py-3 text-right mono text-down">
        {isLong && item.stop_loss != null ? item.stop_loss.toFixed(2) : "—"}
      </td>
      <td className="py-3 text-right mono text-up text-xs">
        {isLong && item.take_profit
          ? `${item.take_profit[0].toFixed(2)} / ${item.take_profit[1].toFixed(2)}`
          : "—"}
      </td>
      <td className={cn(
        "py-3 text-right mono font-semibold",
        (item.risk_reward ?? 0) >= 2 ? "text-up" : "text-text-bright",
      )}>
        {item.risk_reward ? `${item.risk_reward.toFixed(2)}` : "—"}
      </td>
      <td className="py-3 text-right mono text-xs text-text-muted">
        {rsi != null ? rsi.toFixed(0) : "—"}
      </td>
      <td className={cn(
        "py-3 text-right mono text-xs",
        vol && vol >= 1.5 ? "text-up font-semibold" : "text-text-muted",
      )}>
        {vol != null ? `${vol.toFixed(1)}×` : "—"}
      </td>
      <td className="py-3 text-right">
        <ConfidenceBar value={item.confidence} />
      </td>
      <td className="px-4 py-3 text-right">
        <span className={cn(
          "inline-flex items-center gap-1 px-2 py-0.5 rounded mono text-xs font-bold",
          item.edge >= 60 ? "bg-up/20 text-up border border-up/40" :
          item.edge >= 40 ? "bg-accent/15 text-accent border border-accent/30" :
          "bg-bg-elevated text-text-muted border border-line",
        )}>
          {item.edge >= 60 && <Flame className="w-3 h-3" />}
          {item.edge.toFixed(0)}
        </span>
      </td>
    </tr>
  );
}

function BiasBadge({ bias, reason }: { bias: string; reason?: string }) {
  if (bias === "LONG") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-mono bg-up/15 text-up border border-up/40">
        <TrendingUp className="w-3 h-3" />LONG
      </span>
    );
  }
  if (bias === "SHORT") {
    return (
      <span className="px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-mono bg-down/15 text-down border border-down/40">
        SHORT
      </span>
    );
  }
  return (
    <span title={reason} className="px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-mono bg-bg-elevated text-text-muted border border-line">
      NO TRADE
    </span>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(100, Math.round(value * 100)));
  return (
    <div className="inline-flex flex-col items-end gap-1 w-[72px]">
      <span className="mono text-[11px] text-text-muted">{pct}%</span>
      <div className="h-1 w-full rounded-full bg-bg-elevated overflow-hidden">
        <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
