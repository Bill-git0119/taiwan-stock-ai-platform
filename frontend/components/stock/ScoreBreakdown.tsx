import type { StockScore } from "@/lib/api";
import { Card, CardHeader } from "@/components/ui/Card";
import { cn, fmtScore } from "@/lib/utils";

function Bar({ value, label }: { value: number; label: string }) {
  const tone =
    value >= 80 ? "bg-up" : value >= 60 ? "bg-accent" : "bg-down/80";
  return (
    <div>
      <div className="flex items-center justify-between text-xs mb-1.5">
        <span className="text-text-muted">{label}</span>
        <span className="mono text-text-bright">{fmtScore(value)}</span>
      </div>
      <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", tone)}
          style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
        />
      </div>
    </div>
  );
}

export function ScoreBreakdown({ score }: { score: StockScore }) {
  const total = score.total_score;
  const tone =
    total >= 85 ? "text-up" : total >= 70 ? "text-text-bright" : "text-text";

  return (
    <Card hover>
      <CardHeader title="AI 綜合評分" subtitle={score.reason || "尚未產生理由"} />
      <div className="p-5 space-y-5">
        <div className="flex items-end gap-3">
          <div className={cn("mono font-semibold text-5xl tracking-tight", tone)}>
            {fmtScore(total)}
          </div>
          <div className="text-xs text-text-muted pb-2">/ 100</div>
        </div>
        <div className="space-y-3">
          <Bar label="籌碼面 (40%)" value={score.chip_score} />
          <Bar label="基本面 (35%)" value={score.fundamental_score} />
          <Bar label="技術面 (25%)" value={score.technical_score} />
        </div>
      </div>
    </Card>
  );
}
