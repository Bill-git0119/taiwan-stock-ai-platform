import { api } from "@/lib/api";
import { StatCard } from "@/components/dashboard/StatCard";

function fmtVolume(v: number): string {
  if (v >= 1e11) return `${(v / 1e8).toFixed(0)} 億`;
  if (v >= 1e8) return `${(v / 1e8).toFixed(2)} 億`;
  if (v >= 1e4) return `${(v / 1e4).toFixed(1)} 萬`;
  return v.toLocaleString();
}

function fmtNet(v: number): string {
  const sign = v >= 0 ? "+" : "";
  if (Math.abs(v) >= 1000) return `${sign}${(v / 1000).toFixed(1)}K 張`;
  return `${sign}${v.toFixed(0)} 張`;
}

export async function MarketOverview() {
  let m = null as Awaited<ReturnType<typeof api.marketSummary>> | null;
  try {
    m = await api.marketSummary();
  } catch {
    m = null;
  }

  const hasData = m && m.as_of;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <StatCard
        label="收錄股票"
        value={hasData ? String(m!.stock_count) : "—"}
        delta={hasData ? `as of ${m!.as_of}` : "等待 data collector"}
        tone="neutral"
      />
      <StatCard
        label="成交總量"
        value={hasData ? fmtVolume(m!.total_volume) : "—"}
        delta={hasData ? `漲 ${m!.gainers} / 跌 ${m!.losers}` : undefined}
        tone={hasData && m!.gainers > m!.losers ? "up" : "down"}
      />
      <StatCard
        label="外資買賣超"
        value={hasData ? fmtNet(m!.foreign_net) : "—"}
        delta="資料來源：TWSE"
        tone={hasData && m!.foreign_net >= 0 ? "up" : "down"}
      />
      <StatCard
        label="投信買賣超"
        value={hasData ? fmtNet(m!.investment_net) : "—"}
        delta="資料來源：TWSE"
        tone={hasData && m!.investment_net >= 0 ? "up" : "down"}
      />
    </div>
  );
}
