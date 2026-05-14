"use client";

import { useEffect, useState } from "react";
import {
  Target, Shield, TrendingUp, AlertTriangle, Database, AlertCircle,
  Activity, ShieldCheck,
} from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { api, type TradePlanResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const SETUP_LABEL: Record<string, string> = {
  trend_breakout_retest: "突破回踩",
  ma20_support_bounce: "MA20 支撐反彈",
  chip_follow_long: "籌碼跟單",
};

const REGIME_TONE: Record<string, string> = {
  trending_up: "text-up border-up/40 bg-up/10",
  trending_up_weak: "text-up/80 border-up/30 bg-up/5",
  trending_down: "text-down border-down/40 bg-down/10",
  bearish: "text-down border-down/40 bg-down/10",
  sideways: "text-text-muted border-line bg-bg-elevated/40",
  unknown: "text-text-muted border-line bg-bg-elevated/40",
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
    const noData = plan.no_trade_reason === "NO_REAL_DATA";
    return (
      <Card>
        <CardHeader
          title="交易計畫"
          subtitle={`${plan.symbol} · ${noData ? "資料尚未灌入" : "不建議進場"}`}
          right={<DataSourceBadge source={plan.data_source} />}
        />
        <div className="p-6 flex items-start gap-3">
          {noData ? (
            <AlertCircle className="w-5 h-5 text-accent mt-0.5" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-text-muted mt-0.5" />
          )}
          <div className="text-sm">
            <div className="text-text-bright font-medium">
              {noData ? "等待資料更新" : "NO TRADE"}
            </div>
            <div className="text-text-muted mt-1">
              {noData
                ? "此標的尚未在資料庫中（每日 15:10 自動灌入）。當日盤後會自動產生交易計畫。"
                : `理由：${plan.no_trade_reason ?? "未滿足進場條件"}`}
            </div>
            {!noData && (
              <div className="text-xs text-text-muted mt-3">
                信心 {(plan.confidence * 100).toFixed(0)}% · 籌碼 {plan.chip_score} · 技術 {plan.technical_score}
              </div>
            )}
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
          <div className="flex items-center gap-2">
            <DataSourceBadge source={plan.data_source} />
            <span className={cn(
              "px-2 py-1 rounded text-[10px] uppercase tracking-widest font-mono",
              plan.bias === "LONG"
                ? "bg-up/15 text-up border border-up/30"
                : "bg-down/15 text-down border border-down/30",
            )}>
              {plan.bias}
            </span>
          </div>
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

        {/* Market regime block — informs trader whether this setup is allowed today */}
        {plan.regime && (
          <div className="grid grid-cols-3 gap-3 pt-2 border-t border-line text-xs">
            <div>
              <div className="text-[10px] uppercase text-text-muted mb-1">市場狀態</div>
              <div className={cn(
                "inline-block px-1.5 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider border",
                REGIME_TONE[plan.regime.label] ?? REGIME_TONE.unknown,
              )}>
                {plan.regime.label.replace(/_/g, " ")}
              </div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-text-muted mb-1">ADX(14)</div>
              <div className="font-mono text-text-bright">{plan.regime.adx?.toFixed(1) ?? "—"}</div>
            </div>
            <div>
              <div className="text-[10px] uppercase text-text-muted mb-1">EMA200 斜率</div>
              <div className="font-mono text-text-bright">
                {plan.regime.ema200_slope_pct != null
                  ? `${plan.regime.ema200_slope_pct >= 0 ? "+" : ""}${plan.regime.ema200_slope_pct.toFixed(3)}%`
                  : "—"}
              </div>
            </div>
          </div>
        )}

        {/* Validation history — only when we have evaluated edge_signals */}
        {(plan as any).validation && (plan as any).validation.status !== "n/a" && (
          <div className="rounded-md border border-line bg-bg-elevated/40 p-3">
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck className={cn(
                "w-3.5 h-3.5",
                (plan as any).validation.status === "validated" ? "text-up" : "text-text-muted",
              )} />
              <span className="text-[10px] uppercase tracking-widest text-text-bright">
                Setup 歷史表現
              </span>
              <span className={cn(
                "ml-auto px-1.5 py-0.5 rounded text-[10px] uppercase font-mono border",
                (plan as any).validation.status === "validated"
                  ? "text-up border-up/40 bg-up/10"
                  : "text-amber-400 border-amber-400/40 bg-amber-400/10",
              )}>
                {(plan as any).validation.status === "validated" ? "已驗證" : "樣本不足"}
              </span>
            </div>
            <div className="grid grid-cols-4 gap-2 text-xs font-mono">
              <div>
                <div className="text-[10px] text-text-muted">勝率</div>
                <div className="text-text-bright">
                  {(plan as any).validation.win_rate != null
                    ? `${((plan as any).validation.win_rate * 100).toFixed(0)}%`
                    : "—"}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-text-muted">期望值</div>
                <div className={cn(
                  ((plan as any).validation.expectancy_r ?? 0) >= 0 ? "text-up" : "text-down"
                )}>
                  {(plan as any).validation.expectancy_r != null
                    ? `${(plan as any).validation.expectancy_r >= 0 ? "+" : ""}${(plan as any).validation.expectancy_r.toFixed(2)}R`
                    : "—"}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-text-muted">PF</div>
                <div className="text-text-bright">
                  {(plan as any).validation.profit_factor != null
                    ? (plan as any).validation.profit_factor.toFixed(2)
                    : "—"}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-text-muted">樣本數</div>
                <div className="text-text-muted">
                  {(plan as any).validation.sample_size ?? 0}
                </div>
              </div>
            </div>
            {(plan as any).validation.status !== "validated" && (
              <p className="mt-2 text-[10px] text-text-muted">
                此 setup 累積樣本不足，系統將其視為「研究候選」而非實單機會。
              </p>
            )}
          </div>
        )}

        {/* Management rules */}
        {plan.management && (
          <div className="rounded-md border border-line bg-bg-elevated/40 p-3">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-3.5 h-3.5 text-accent" />
              <span className="text-[10px] uppercase tracking-widest text-text-bright">
                動態出場規則
              </span>
            </div>
            <ul className="text-[11px] text-text-muted space-y-1 leading-relaxed">
              <li>• 達 +{plan.management.move_to_breakeven_at_r}R 時將停損移到成本價（break-even）</li>
              <li>• 之後採 {plan.management.trailing_stop_atr_mult}× ATR 移動停損
                {plan.management.trailing_stop_value != null && (
                  <span className="text-text"> · 目前位置 ≈ {plan.management.trailing_stop_value}</span>
                )}
              </li>
              <li>• TP1 出 {plan.management.scale_out_tp1_pct}%、TP2 出 {plan.management.scale_out_tp2_pct}%</li>
              <li>• 最長持有 {plan.management.max_hold_bars} 根日 K，未達 TP/SL 則出場</li>
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

function DataSourceBadge({ source }: { source?: string }) {
  if (source === "real") {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider font-mono bg-up/10 text-up border border-up/30">
        <Database className="w-3 h-3" />real
      </span>
    );
  }
  if (source === "none") {
    return (
      <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider font-mono bg-bg-elevated text-text-muted border border-line">
        <Database className="w-3 h-3" />no data
      </span>
    );
  }
  return null;
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
