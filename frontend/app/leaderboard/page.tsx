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

interface LbStatus {
  total_picks_tracked: number;
  tracking_started_at: string | null;
  latest_pick_at: string | null;
  has_data: boolean;
}

export default function LeaderboardPage() {
  const [items, setItems] = useState<Item[] | null>(null);
  const [status, setStatus] = useState<LbStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.leaderboardWeekly()
      .then((r) => {
        setItems(r.items);
        if ("status" in r) setStatus((r as { status: LbStatus }).status);
      })
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
                    <tr>
                      <td colSpan={6} className="px-3 py-8 text-center text-text-muted">
                        <div className="text-sm text-text-bright mb-1">尚無已 evaluate 的 picks</div>
                        <div className="text-[11px]">
                          {status?.tracking_started_at
                            ? <>追蹤中：{status.total_picks_tracked} 筆 picks · 自 {status.tracking_started_at} 起記錄，需要 7 個交易日才能算出報酬。</>
                            : <>尚未開始 pick 追蹤。每日盤後排程啟動後會自動寫入。</>}
                          <br />
                          <span className="text-[10px] italic">本榜不會偽造績效。空欄 = 沒資料。</span>
                        </div>
                      </td>
                    </tr>
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
