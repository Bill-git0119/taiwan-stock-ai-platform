import type { StockScore } from "@/lib/api";
import { Card, CardHeader } from "@/components/ui/Card";
import { Activity, LineChart, TrendingUp } from "lucide-react";
import { fmtScore } from "@/lib/utils";

export function AnalysisCards({ score }: { score: StockScore }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card hover>
        <CardHeader
          title="籌碼分析"
          subtitle="外資 / 投信 / 主力分點"
          right={<TrendingUp className="w-4 h-4 text-up" />}
        />
        <div className="p-5">
          <div className="mono text-4xl text-text-bright">
            {fmtScore(score.chip_score)}
          </div>
          <p className="text-xs text-text-muted mt-3 leading-relaxed">
            籌碼結構評估含三大法人買賣超、量能倍數、券商集中度變化。
          </p>
        </div>
      </Card>
      <Card hover>
        <CardHeader
          title="基本面分析"
          subtitle="EPS / ROE / 營收 / PE"
          right={<Activity className="w-4 h-4 text-accent" />}
        />
        <div className="p-5">
          <div className="mono text-4xl text-text-bright">
            {fmtScore(score.fundamental_score)}
          </div>
          <p className="text-xs text-text-muted mt-3 leading-relaxed">
            看 EPS 年增、ROE、營收月增、本益比合理度。PE 甜蜜點 8–20。
          </p>
        </div>
      </Card>
      <Card hover>
        <CardHeader
          title="技術面分析"
          subtitle="MA / MACD / RSI / 突破"
          right={<LineChart className="w-4 h-4 text-down" />}
        />
        <div className="p-5">
          <div className="mono text-4xl text-text-bright">
            {fmtScore(score.technical_score)}
          </div>
          <p className="text-xs text-text-muted mt-3 leading-relaxed">
            均線多頭排列、MACD 金叉、RSI 健康區間、突破 20 日高點。
          </p>
        </div>
      </Card>
    </div>
  );
}
