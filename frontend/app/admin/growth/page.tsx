"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Growth {
  mrr_twd: number;
  arpu_twd: number;
  paid_users_now: number;
  paid_users_ever: number;
  churn_rate: number;
  cac_twd: number;
  ltv_twd: number;
  ltv_cac_ratio: number;
  trial_to_paid_rate: number;
  referrals_total: number;
  referrals_converted: number;
  referral_lift_pct: number;
  revenue_trend?: Array<{ month: string; revenue: number }>;
}

const FALLBACK: Growth = {
  mrr_twd: 0,
  arpu_twd: 0,
  paid_users_now: 0,
  paid_users_ever: 0,
  churn_rate: 0,
  cac_twd: 200,
  ltv_twd: 0,
  ltv_cac_ratio: 0,
  trial_to_paid_rate: 0,
  referrals_total: 0,
  referrals_converted: 0,
  referral_lift_pct: 0,
};

function fmtTWD(n: number) {
  return new Intl.NumberFormat("zh-TW", { style: "currency", currency: "TWD", maximumFractionDigits: 0 }).format(n);
}
function pct(n: number) { return `${(n * 100).toFixed(1)}%`; }

function RevenueTrend({ data }: { data: Array<{ month: string; revenue: number }> }) {
  if (!data || data.length < 2) {
    return <div className="h-40 flex items-center justify-center text-text-muted text-xs">營收趨勢資料累積中</div>;
  }
  const w = 720, h = 180, pad = 28;
  const ys = data.map((d) => d.revenue);
  const maxY = Math.max(...ys, 1);
  const X = (i: number) => pad + (i / (data.length - 1)) * (w - 2 * pad);
  const Y = (v: number) => h - pad - (v / maxY) * (h - 2 * pad);
  const path = data.map((d, i) => `${i === 0 ? "M" : "L"} ${X(i).toFixed(2)} ${Y(d.revenue).toFixed(2)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-44">
      <defs>
        <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2962FF" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#2962FF" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path} L ${X(data.length - 1)} ${h - pad} L ${X(0)} ${h - pad} Z`} fill="url(#rev)" />
      <path d={path} fill="none" stroke="#2962FF" strokeWidth="2" />
      {data.map((d, i) => (
        <text key={d.month} x={X(i)} y={h - 6} textAnchor="middle" className="fill-text-muted" fontSize="10">{d.month}</text>
      ))}
    </svg>
  );
}

export default function AdminGrowthPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<Growth | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user) { router.push("/login"); return; }
    if (!user.is_admin) { router.push("/"); return; }
    api.adminGrowth()
      .then((r: Partial<Growth>) => setData({ ...FALLBACK, ...r }))
      .catch((e: Error) => {
        setError(e?.message ?? "load failed");
        setData(FALLBACK);
      });
  }, [loading, user, router]);

  if (loading || !user || !user.is_admin) {
    return (
      <div className="min-h-screen">
        <Topbar />
        <main className="max-w-7xl mx-auto px-6 py-16 text-text-muted text-sm">驗證權限中…</main>
      </div>
    );
  }

  const stats = data ?? null;

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        <header className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-text-bright tracking-tight">Growth Dashboard</h1>
            <p className="text-xs text-text-muted mt-1">MRR · 留存 · 轉換 · 推薦 · LTV/CAC</p>
          </div>
        </header>

        {error && <div className="text-down text-sm">{error}（使用 fallback）</div>}

        {!stats ? (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-24" />)}
          </div>
        ) : (
          <>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <KPI label="MRR" value={fmtTWD(stats.mrr_twd)} hint="月度經常性收入" tone="up" />
              <KPI label="付費用戶" value={String(stats.paid_users_now)} hint={`累計 ${stats.paid_users_ever}`} />
              <KPI label="ARPU" value={fmtTWD(stats.arpu_twd)} hint="每位付費用戶平均收入" />
              <KPI label="Churn" value={pct(stats.churn_rate)} tone={stats.churn_rate <= 0.05 ? "up" : "down"} />
              <KPI label="LTV" value={fmtTWD(stats.ltv_twd)} />
              <KPI label="CAC" value={fmtTWD(stats.cac_twd)} hint="估算" />
              <KPI label="LTV / CAC" value={stats.ltv_cac_ratio.toFixed(2)} tone={stats.ltv_cac_ratio >= 3 ? "up" : "down"} />
              <KPI label="Trial → Paid" value={pct(stats.trial_to_paid_rate)} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <Card>
                <CardHeader title="推薦病毒成長" />
                <div className="p-5 space-y-3">
                  <div className="flex justify-between text-sm">
                    <span className="text-text-muted">總邀請</span>
                    <span className="font-mono text-text-bright">{stats.referrals_total}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-text-muted">已轉換付費</span>
                    <span className="font-mono text-up">{stats.referrals_converted}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-text-muted">推薦增量</span>
                    <span className={cn("font-mono", stats.referral_lift_pct >= 0 ? "text-up" : "text-down")}>
                      +{stats.referral_lift_pct.toFixed(1)}%
                    </span>
                  </div>
                </div>
              </Card>
              <Card className="lg:col-span-2">
                <CardHeader title="營收趨勢" subtitle="MRR by month" />
                <div className="p-3">
                  <RevenueTrend data={stats.revenue_trend ?? []} />
                </div>
              </Card>
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function KPI({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: "up" | "down" }) {
  return (
    <Card className="p-5">
      <div className="text-[11px] uppercase tracking-wider text-text-muted">{label}</div>
      <div className={cn("mt-2 text-2xl font-semibold font-mono",
        tone === "up" ? "text-up" : tone === "down" ? "text-down" : "text-text-bright")}>
        {value}
      </div>
      {hint && <div className="text-[11px] text-text-muted mt-1">{hint}</div>}
    </Card>
  );
}
