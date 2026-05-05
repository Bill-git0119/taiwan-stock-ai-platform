"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowDownRight, ArrowUpRight, Flame, TrendingUp } from "lucide-react";

import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { api, type MoverRow, type MoversResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "gainers" | "losers" | "volume_spikes" | "breakouts" | "momentum_5d";

const TABS: Array<{ key: Tab; label: string; icon: any; tone: string }> = [
  { key: "gainers",       label: "今日強勢",   icon: ArrowUpRight,   tone: "text-up" },
  { key: "breakouts",     label: "突破 20 日", icon: TrendingUp,     tone: "text-accent" },
  { key: "volume_spikes", label: "爆量",       icon: Flame,          tone: "text-orange-400" },
  { key: "momentum_5d",   label: "5 日動能",   icon: TrendingUp,     tone: "text-up" },
  { key: "losers",        label: "今日弱勢",   icon: ArrowDownRight, tone: "text-down" },
];

export function MoversWidget() {
  const [data, setData] = useState<MoversResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("gainers");

  useEffect(() => {
    let alive = true;
    api.movers()
      .then((d) => { if (alive) setData(d); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : "fetch failed"); });
    return () => { alive = false; };
  }, []);

  const rows: MoverRow[] = (data?.[tab] ?? []).slice(0, 8);

  return (
    <Card>
      <CardHeader
        title="盤後即時動向"
        subtitle={data ? `掃描 ${data.scanned} 檔` : "讀取中…"}
        right={
          <Link href="/scanner" className="text-xs text-accent hover:underline">
            完整 Scanner →
          </Link>
        }
      />
      <div className="px-3 pt-3 flex items-center gap-1.5 overflow-x-auto">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-colors",
                tab === t.key
                  ? "bg-accent/15 text-accent border-accent/40"
                  : "bg-bg-elevated text-text-muted border-line hover:text-text-bright",
              )}
            >
              <Icon className={cn("w-3.5 h-3.5", tab === t.key ? "" : t.tone)} />
              {t.label}
            </button>
          );
        })}
      </div>

      <div className="p-3">
        {error && <div className="p-4 text-xs text-down">載入失敗：{error}</div>}
        {!data && !error && (
          <div className="space-y-1.5">
            {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-9" />)}
          </div>
        )}
        {data && rows.length === 0 && (
          <div className="p-6 text-center text-xs text-text-muted">
            目前沒有資料 — 等待每日 15:10 自動更新
          </div>
        )}
        {rows.map((r) => (
          <Link
            key={r.symbol}
            href={`/stock/${r.symbol}`}
            className="flex items-center justify-between px-2 py-2 rounded hover:bg-bg-elevated transition-colors text-sm"
          >
            <div className="flex items-center gap-2 min-w-0">
              <span className="mono text-text-bright shrink-0 w-12">{r.symbol}</span>
              <span className="truncate text-text">{r.name}</span>
            </div>
            <div className="flex items-center gap-3 shrink-0 text-xs">
              <span className="mono text-text-muted">{r.last.toFixed(2)}</span>
              {tab === "volume_spikes" ? (
                <span className="mono text-orange-400 font-semibold w-14 text-right">
                  {r.volume_ratio.toFixed(1)}×
                </span>
              ) : tab === "momentum_5d" ? (
                <span className={cn("mono font-semibold w-14 text-right",
                  r.d5_pct >= 0 ? "text-up" : "text-down")}>
                  {r.d5_pct >= 0 ? "+" : ""}{r.d5_pct.toFixed(2)}%
                </span>
              ) : tab === "breakouts" ? (
                <span className="mono text-accent text-[10px] uppercase">突破</span>
              ) : (
                <span className={cn("mono font-semibold w-14 text-right",
                  r.d1_pct >= 0 ? "text-up" : "text-down")}>
                  {r.d1_pct >= 0 ? "+" : ""}{r.d1_pct.toFixed(2)}%
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </Card>
  );
}
