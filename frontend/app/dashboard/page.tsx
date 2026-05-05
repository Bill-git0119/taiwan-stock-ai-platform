import { Suspense } from "react";
import Link from "next/link";
import { Zap } from "lucide-react";
import { Topbar } from "@/components/layout/Topbar";
import { MarketOverview } from "@/components/dashboard/MarketOverview";
import { Top10Table } from "@/components/dashboard/Top10Table";
import { StockSearch } from "@/components/dashboard/StockSearch";
import { MoversWidget } from "@/components/dashboard/MoversWidget";
import { Skeleton } from "@/components/ui/Skeleton";

export const metadata = { title: "Dashboard" };

export default function DashboardPage() {
  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        <section className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-2xl font-semibold text-text-bright tracking-tight">
              Dashboard
            </h1>
            <p className="text-xs text-text-muted mt-1">
              AI 驅動的台股每日強勢股排行 · 籌碼 × 基本面 × 技術面
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/scanner"
              className="inline-flex items-center gap-1.5 px-4 h-9 rounded-md bg-accent/15 text-accent border border-accent/40 hover:bg-accent/25 text-sm font-medium transition-colors"
            >
              <Zap className="w-4 h-4" />
              開啟 Scanner
            </Link>
            <StockSearch />
          </div>
        </section>

        <section>
          <Suspense
            fallback={
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-[104px]" />
                ))}
              </div>
            }
          >
            <MarketOverview />
          </Suspense>
        </section>

        <section className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <Top10Table />
          </div>
          <div>
            <MoversWidget />
          </div>
        </section>

        <footer className="text-[11px] text-text-muted text-center py-8">
          Taiwan Stock AI Platform · v0.6.0 · data source: TWSE / TPEX / MOPS
        </footer>
      </main>
    </div>
  );
}
