import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { api, type StockDetail } from "@/lib/api";
import { Topbar } from "@/components/layout/Topbar";
import { AnalysisCards } from "@/components/stock/AnalysisCards";
import { RecentTrend } from "@/components/stock/RecentTrend";
import { ScoreBreakdown } from "@/components/stock/ScoreBreakdown";
import { TradingViewChart } from "@/components/stock/TradingViewChart";

async function loadStock(symbol: string): Promise<StockDetail | null> {
  try {
    return await api.stock(symbol);
  } catch {
    return null;
  }
}

export default async function StockPage({
  params,
}: {
  params: Promise<{ symbol: string }>;
}) {
  const { symbol } = await params;
  const detail = await loadStock(symbol);
  if (!detail) notFound();

  const score = detail.latest_score;
  const market = detail.market === "TPEX" ? "TPEX" : "TWSE";

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <div>
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-xs text-text-muted hover:text-text transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            返回 Dashboard
          </Link>
          <div className="mt-2 flex items-baseline gap-3">
            <h1 className="text-2xl font-semibold text-text-bright tracking-tight mono">
              {detail.symbol}
            </h1>
            <span className="text-lg text-text">{detail.name}</span>
            <span className="text-[11px] text-text-muted uppercase tracking-widest border border-line rounded px-1.5 py-0.5">
              {detail.market}
            </span>
          </div>
        </div>

        <AnalysisCards
          score={
            score ?? {
              symbol: detail.symbol,
              name: detail.name,
              chip_score: 0,
              fundamental_score: 0,
              technical_score: 0,
              total_score: 0,
              reason: "尚無評分資料",
            }
          }
        />

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <TradingViewChart symbol={detail.symbol} market={market} />
          </div>
          <div>
            {score && <ScoreBreakdown score={score} />}
          </div>
        </div>

        <RecentTrend prices={detail.prices} />

        <footer className="text-[11px] text-text-muted text-center py-8">
          Taiwan Stock AI Platform · {detail.symbol}
        </footer>
      </main>
    </div>
  );
}
