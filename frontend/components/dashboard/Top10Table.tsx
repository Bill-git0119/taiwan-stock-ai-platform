"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Lock, ArrowUpRight } from "lucide-react";
import { api, type Top10Response } from "@/lib/api";
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
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.top10().then(setData).catch((e) => setError(e.message ?? "fetch failed"));
  }, []);

  const rows = data?.items ?? [];
  const tier = data?.tier;

  return (
    <Card className="overflow-hidden">
      <CardHeader
        title="每日 TOP 10 強勢股"
        subtitle="Score = Chip 40% + Fundamental 35% + Technical 25%"
        right={
          tier ? (
            <span className="mono text-[11px] text-text-muted">
              {PLAN_LABEL[tier.plan]} · {tier.showing} / {tier.total_available}
            </span>
          ) : null
        }
      />

      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[760px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-text-muted">
              <th className="text-left  font-medium px-5 py-2">#</th>
              <th className="text-left  font-medium py-2">代號</th>
              <th className="text-left  font-medium py-2">名稱</th>
              <th className="text-left  font-medium py-2">AI 理由</th>
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
            {rows.map((s, i) => (
              <tr key={s.symbol} className="border-t border-line hover:bg-bg-elevated transition-colors group">
                <td className="mono text-text-muted px-5 py-2.5">{String(i + 1).padStart(2, "0")}</td>
                <td className="mono text-text-bright py-2.5">
                  <Link href={`/stock/${s.symbol}`} className="group-hover:text-accent">{s.symbol}</Link>
                </td>
                <td className="py-2.5">
                  <Link href={`/stock/${s.symbol}`} className="group-hover:text-accent">{s.name}</Link>
                </td>
                <td className="py-2.5 text-xs text-text-muted max-w-sm truncate">{s.reason ?? "—"}</td>
                <td className="mono text-right py-2.5">{fmtScore(s.chip_score)}</td>
                <td className="mono text-right py-2.5">{fmtScore(s.fundamental_score)}</td>
                <td className="mono text-right py-2.5">{fmtScore(s.technical_score)}</td>
                <td className={cn("mono text-right font-semibold px-5 py-2.5", scoreColor(s.total_score))}>
                  {fmtScore(s.total_score)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {tier && tier.upgrade_message && (
        <Link
          href="/pricing"
          className="flex items-center justify-between gap-4 px-5 py-4 border-t border-line bg-accent/5 hover:bg-accent/10 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Lock className="w-4 h-4 text-accent" />
            <div>
              <div className="text-sm text-text-bright">{tier.upgrade_message}</div>
              <div className="text-[11px] text-text-muted mt-0.5">
                目前方案: {PLAN_LABEL[tier.plan]} · 已隱藏 {tier.total_available - tier.showing} 檔
              </div>
            </div>
          </div>
          <span className="flex items-center gap-1 text-sm text-accent mono">
            升級方案 <ArrowUpRight className="w-4 h-4" />
          </span>
        </Link>
      )}
    </Card>
  );
}
