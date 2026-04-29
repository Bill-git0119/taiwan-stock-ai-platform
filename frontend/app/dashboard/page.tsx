import { Suspense } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { MarketOverview } from "@/components/dashboard/MarketOverview";
import { Top10Table } from "@/components/dashboard/Top10Table";
import { StockSearch } from "@/components/dashboard/StockSearch";
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
          <StockSearch />
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

        <section>
          <Top10Table />
        </section>

        <footer className="text-[11px] text-text-muted text-center py-8">
          Taiwan Stock AI Platform · v0.5.0 · data source: TWSE / TPEX / MOPS
        </footer>
      </main>
    </div>
  );
}
