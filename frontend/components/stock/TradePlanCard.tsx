"use client";

import { useEffect, useState } from "react";
import { Target, Shield, TrendingUp, AlertTriangle } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { api, type TradePlanResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const SETUP_LABEL: Record<string, string> = {
  trend_breakout_retest: "突破回踩",
  ma20_support_bounce: "MA20 支撐反彈",
  chip_follow_long: "籌碼跟單",
};

export function TradePlanCard({ symbol }: { symbol: string }) {
  const [plan, setPlan] = useState<TradePlanResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.tradePlan(symbol)
      .then((p) => { if (alive) setPlan(p); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : "fetch failed"); });
    return () => { alive = false; };
  }, [symbol]);

  if (error) {
    return (
      <Card className="p-5 text-sm">
        <div className="text-down">交易計畫載入失敗：{error}</div>
      </Card>
    );
  }
  if (!plan) {
    return <Skeleton className="h-72" />;
  }

  if (plan.bias === "NO_TRADE") {
    return (
      <Card>
        <CardHeader title="交易計畫" subtitle={`${plan.symbol} · 不建議進場`} />
        <div className="p-6 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-text-muted mt-0.5" />
          <div className="text-sm">
            <div className="text-text-bright font-medium">NO TRADE</div>
            <div className="text-text-muted mt-1">理由：{plan.no_trade_reason ?? "未滿足進場條件"}</div>
            <div className="text-xs text-text-muted mt-3">
              信心 {(plan.confidence * 100).toFixed(0)}% · 籌碼 {plan.chip_score} · 技術 {plan.technical_score}
            </div>
          </div>
        </div>
      </Card>
    );
  }

  const [entryLo, entryHi] = plan.entry_zone ?? [0, 0];
  const [tp1, tp2] = plan.take_profit ?? [0, 0];
  const sl = plan.stop_loss ?? 0;
  const rr = plan.risk_reward ?? 0;

  return (
    <Card>
      <CardHeader
        title="交易計畫"
        subtitle={`${plan.symbol} · ${SETUP_LABEL[plan.setup ?? ""] ?? plan.setup}`}
        right={
          <span className={cn(
            "px-2 py-1 rounded text-[10px] uppercase tracking-widest font-mono",
            plan.bias === "LONG"
              ? "bg-up/15 text-up border border-up/30"
              : "bg-down/15 text-down border border-down/30",
          )}>
            {plan.bias}
          </span>
        }
      />
      <div className="p-5 space-y-5">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Tile icon={<TrendingUp className="w-4 h-4" />} label="進場區間"
                value={`${entryLo.toFixed(2)} - ${entryHi.toFixed(2)}`}
                tone="text-text-bright" />
          <Tile icon={<Shield className="w-4 h-4" />} label="停損"
                value={sl.toFixed(2)} tone="text-down" />
          <Tile icon={<Target className="w-4 h-4" />} label="目標 TP1"
                value={tp1.toFixed(2)} tone="text-up" />
          <Tile icon={<Target className="w-4 h-4" />} label="目標 TP2"
                value={tp2.toFixed(2)} tone="text-up" />
        </div>

        <div className="grid grid-cols-3 gap-4 pt-2 border-t border-line">
          <KPI label="風險:回報" value={`${rr.toFixed(2)} : 1`} tone={rr >= 1.5 ? "up" : "muted"} />
          <KPI label="信心分數"
               value={`${(plan.confidence * 100).toFixed(0)}%`}
               extra={
                 <div className="mt-2 h-1.5 rounded-full bg-bg-elevated overflow-hidden">
                   <div className="h-full bg-accent transition-all duration-500"
                        style={{ width: `${(plan.confidence * 100).toFixed(0)}%` }} />
                 </div>
               } />
          <KPI label="ATR (14)" value={plan.atr ? plan.atr.toFixed(2) : "—"} tone="muted" />
        </div>

        {plan.reasons.length > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-wider text-text-muted mb-2">進場理由</div>
            <ul className="space-y-1.5">
              {plan.reasons.map((r, i) => (
                <li key={i} className="text-sm text-text flex items-start gap-2">
                  <span className="text-up mt-0.5">✓</span><span>{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded-md bg-bg-elevated/60 border border-line p-3 text-[11px] text-text-muted leading-relaxed">
          <span className="text-text-bright font-semibold">交易鐵律：</span>
          每筆風險 ≤ 1% 帳戶資金 · RR ≥ 1.5 才進場 · 停損為硬規則 · 不使用未來資料 ·
          手續費 0.05% / 滑點 0.05% 已內含。
          <br />
          本平台僅提供分析，不構成投資建議；請自負交易風險。
        </div>
      </div>
    </Card>
  );
}

function Tile({ icon, label, value, tone }: { icon: React.ReactNode; label: string; value: string; tone: string }) {
  return (
    <div className="rounded-md border border-line bg-bg-elevated/40 p-3">
      <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
        {icon}{label}
      </div>
      <div className={cn("mt-1 font-mono text-lg font-semibold", tone)}>{value}</div>
    </div>
  );
}

function KPI({ label, value, tone = "muted", extra }: {
  label: string; value: string;
  tone?: "up" | "down" | "muted"; extra?: React.ReactNode;
}) {
  const cls = tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-text-bright";
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className={cn("mt-1 text-xl font-semibold font-mono", cls)}>{value}</div>
      {extra}
    </div>
  );
}
