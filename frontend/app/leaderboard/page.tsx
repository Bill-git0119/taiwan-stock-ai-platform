"use client";

import { useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Item {
  symbol: string;
  name: string;
  rank: number;
  entry_price: number;
  return_pct: number;
  date: string;
}

export default function LeaderboardPage() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.leaderboardWeekly()
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof Error ? e.message : "fetch failed"));
  }, []);

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        <header>
          <h1 className="text-2xl font-semibold text-text-bright tracking-tight">每週績效榜</h1>
          <p className="text-xs text-text-muted mt-1">
            過去 7 日 AI 推薦個股的真實表現 · 透明可驗證
          </p>
        </header>

        <Card>
          <CardHeader title="Top 10 · 過去 7 日" subtitle="依累積報酬排序" />
          <div className="p-2">
            {error && <div className="p-4 text-down text-sm">載入失敗：{error}</div>}
            {!error && !items && (
              <div className="p-4 space-y-2">
                {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-10" />)}
              </div>
            )}
            {items && (
              <table className="w-full text-sm">
                <thead className="text-[11px] uppercase tracking-wider text-text-muted">
                  <tr>
                    <th className="text-left px-3 py-2">#</th>
                    <th className="text-left px-3 py-2">代號</th>
                    <th className="text-left px-3 py-2">名稱</th>
                    <th className="text-right px-3 py-2">進場</th>
                    <th className="text-right px-3 py-2">7 日報酬</th>
                    <th className="text-left px-3 py-2 hidden sm:table-cell">日期</th>
                  </tr>
                </thead>
                <tbody className="font-mono">
                  {items.map((it) => (
                    <tr key={`${it.date}-${it.symbol}`} className="border-t border-line">
                      <td className="px-3 py-2 text-text-muted">{it.rank}</td>
                      <td className="px-3 py-2 text-text-bright">{it.symbol}</td>
                      <td className="px-3 py-2 font-sans">{it.name}</td>
                      <td className="px-3 py-2 text-right">{it.entry_price.toFixed(2)}</td>
                      <td className={cn("px-3 py-2 text-right font-semibold",
                        it.return_pct >= 0 ? "text-up" : "text-down")}>
                        {it.return_pct >= 0 ? "+" : ""}{it.return_pct.toFixed(2)}%
                      </td>
                      <td className="px-3 py-2 hidden sm:table-cell text-text-muted">{it.date}</td>
                    </tr>
                  ))}
                  {items.length === 0 && (
                    <tr><td colSpan={6} className="px-3 py-6 text-center text-text-muted">暫無資料</td></tr>
                  )}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      </main>
    </div>
  );
}
