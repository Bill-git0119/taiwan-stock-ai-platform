"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { TrendingUp, Target } from "lucide-react";
import { api, type ScanItem, type ScanResponse, type Top10Response } from "@/lib/api";
import { cn, fmtScore } from "@/lib/utils";
import { Card, CardHeader } from "@/components/ui/Card";

function scoreColor(n: number) {
  if (n >= 85) return "text-up";
  if (n >= 70) return "text-text-bright";
  if (n >= 55) return "text-text";
  return "text-down";
}

const PLAN_LABEL: Record<string, string> = { free: "Free", pro: "Pro", elite: "Elite" };

export function Top10Table() {
  const [data, setData] = useState<Top10Response | null>(null);
  const [scan, setScan] = useState<ScanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.top10().then(setData).catch((e) => setError(e.message ?? "fetch failed"));
    // Pull scanner once for bias badges — non-fatal if unavailable
    api.scan({ limit: 200 }).then(setScan).catch(() => {});
  }, []);

  const rows = data?.items ?? [];
  const tier = data?.tier;
  // bias lookup by symbol from the scanner result
  const bias = new Map<string, ScanItem>(
    scan?.items.map((i) => [i.symbol, i]) ?? [],
  );

  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="每日 TOP 10 強勢股"
        subtitle="Score = Chip 40% + Fundamental 35% + Technical 25%"
        right={
          <div className="flex items-center gap-3">
            {scan?.as_of && (
              <span className="mono text-[10px] text-text-muted">
                資料日 <span className="text-text-bright">{scan.as_of}</span>
              </span>
            )}
            {tier && (
              <span className="mono text-[11px] text-text-muted">
                {PLAN_LABEL[tier.plan]} · {tier.showing} / {tier.total_available}
              </span>
            )}
          </div>
        }
      />

      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[820px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-text-muted">
              <th className="text-left  font-medium px-5 py-2">#</th>
              <th className="text-left  font-medium py-2">代號</th>
              <th className="text-left  font-medium py-2">名稱</th>
              <th className="text-left  font-medium py-2">交易訊號</th>
              <th className="text-right font-medium py-2">籌碼</th>
              <th className="text-right font-medium py-2">基本面</th>
              <th className="text-right font-medium py-2">技術面</th>
              <th className="text-right font-medium px-5 py-2">總分</th>
            </tr>
          </thead>
          <tbody>
            {error && (
              <tr><td colSpan={8} className="text-center text-down py-10 text-xs">
                {error} · 請確認 backend 執行中
              </td></tr>
            )}
            {!error && rows.length === 0 && (
              <tr><td colSpan={8} className="text-center text-text-muted py-10 text-xs">
                載入中…
              </td></tr>
            )}
            {rows.map((s, i) => {
              const b = bias.get(s.symbol);
              return (
                <tr key={s.symbol} className="border-t border-line hover:bg-bg-elevated transition-colors group">
                  <td className="mono text-text-muted px-5 py-2.5">{String(i + 1).padStart(2, "0")}</td>
                  <td className="mono text-text-bright py-2.5">
                    <Link href={`/stock/${s.symbol}`} className="group-hover:text-accent">{s.symbol}</Link>
                  </td>
                  <td className="py-2.5">
                    <Link href={`/stock/${s.symbol}`} className="group-hover:text-accent">{s.name}</Link>
                  </td>
                  <td className="py-2.5">
                    <SignalBadge item={b} reason={s.reason} />
                  </td>
                  <td className="mono text-right py-2.5">{fmtScore(s.chip_score)}</td>
                  <td className="mono text-right py-2.5">{fmtScore(s.fundamental_score)}</td>
                  <td className="mono text-right py-2.5">{fmtScore(s.technical_score)}</td>
                  <td className={cn("mono text-right font-semibold px-5 py-2.5", scoreColor(s.total_score))}>
                    {fmtScore(s.total_score)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Local mode: no upgrade prompts. Tier is always Elite. */}
    </Card>
  );
}

function SignalBadge({ item, reason }: { item?: ScanItem; reason?: string }) {
  // No scan data yet — fall back to AI reason text
  if (!item) {
    return <span className="text-xs text-text-muted truncate max-w-sm inline-block">{reason ?? "—"}</span>;
  }
  if (item.bias === "LONG" && item.risk_reward) {
    return (
      <div className="inline-flex items-center gap-2">
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-up/15 text-up border border-up/40">
          <TrendingUp className="w-3 h-3" />LONG
        </span>
        <span className="inline-flex items-center gap-1 text-[11px] text-text-muted">
          <Target className="w-3 h-3" />RR {item.risk_reward.toFixed(1)}
        </span>
      </div>
    );
  }
  return (
    <span
      title={item.no_trade_reason ?? undefined}
      className="px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider bg-bg-elevated text-text-muted border border-line"
    >
      NO TRADE
    </span>
  );
}
