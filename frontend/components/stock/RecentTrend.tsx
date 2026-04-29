import type { PricePoint } from "@/lib/api";
import { Card, CardHeader } from "@/components/ui/Card";
import { cn } from "@/lib/utils";

function change(from: number, to: number): number {
  if (!from) return 0;
  return ((to - from) / from) * 100;
}

export function RecentTrend({ prices }: { prices: PricePoint[] }) {
  const recent = prices.slice(-10);
  return (
    <Card hover>
      <CardHeader
        title="近 10 日走勢"
        subtitle={
          recent.length ? `自 ${recent[0].date} 起` : "尚未收集歷史資料"
        }
      />
      <div className="overflow-x-auto">
        <table className="w-full text-sm min-w-[560px]">
          <thead>
            <tr className="text-[11px] uppercase tracking-wider text-text-muted">
              <th className="text-left  font-medium px-5 py-2">日期</th>
              <th className="text-right font-medium py-2">開</th>
              <th className="text-right font-medium py-2">高</th>
              <th className="text-right font-medium py-2">低</th>
              <th className="text-right font-medium py-2">收</th>
              <th className="text-right font-medium py-2">量</th>
              <th className="text-right font-medium px-5 py-2">漲跌</th>
            </tr>
          </thead>
          <tbody>
            {recent.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="text-center text-text-muted py-8 text-xs"
                >
                  無資料，請先執行 `python scripts/data_collector.py`
                </td>
              </tr>
            )}
            {recent.map((p, i) => {
              const prev = i > 0 ? recent[i - 1].close : p.open;
              const ch = change(prev, p.close);
              const tone = ch >= 0 ? "text-up" : "text-down";
              return (
                <tr key={p.date} className="border-t border-line">
                  <td className="mono text-text-muted px-5 py-2">{p.date}</td>
                  <td className="mono text-right py-2">{p.open.toFixed(2)}</td>
                  <td className="mono text-right py-2">{p.high.toFixed(2)}</td>
                  <td className="mono text-right py-2">{p.low.toFixed(2)}</td>
                  <td className="mono text-right text-text-bright py-2">
                    {p.close.toFixed(2)}
                  </td>
                  <td className="mono text-right text-text-muted py-2">
                    {(p.volume / 1000).toFixed(0)}K
                  </td>
                  <td className={cn("mono text-right px-5 py-2", tone)}>
                    {ch >= 0 ? "+" : ""}
                    {ch.toFixed(2)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
