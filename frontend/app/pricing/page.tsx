"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Check, Crown, Zap, Sparkles } from "lucide-react";
import { Topbar } from "@/components/layout/Topbar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { api, type PlansResponse } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ICONS = { free: Sparkles, pro: Zap, elite: Crown };

export default function PricingPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [plans, setPlans] = useState<PlansResponse | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { api.plans().then(setPlans).catch(() => {}); }, []);

  async function buy(plan: "pro" | "elite") {
    setError(null);
    if (!user) { router.push("/login"); return; }
    setBusy(plan);
    try {
      const r = await api.checkout(plan);
      window.location.href = r.url;
    } catch (e: any) {
      setError(e?.message ?? "checkout 失敗");
    } finally {
      setBusy(null);
    }
  }

  const tiers = plans
    ? [
        { key: "free", ...plans.free, cta: "目前方案", highlight: false },
        { key: "pro", ...plans.pro, cta: "升級 Pro", highlight: true },
        { key: "elite", ...plans.elite, cta: "升級 Elite", highlight: false },
      ]
    : [];

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-6xl mx-auto px-6 py-12">
        <header className="text-center mb-10">
          <h1 className="text-3xl font-semibold text-text-bright tracking-tight">選擇你的方案</h1>
          <p className="text-sm text-text-muted mt-2">
            隨時可升級 / 降級 · 取消無罰款 · 安全的 Stripe 金流
          </p>
        </header>

        {error && <div className="text-center text-down text-sm mb-4">{error}</div>}

        <div className="grid md:grid-cols-3 gap-5">
          {tiers.map((t) => {
            const Icon = ICONS[t.key as keyof typeof ICONS];
            const isCurrent = user?.plan === t.key;
            return (
              <Card
                key={t.key}
                className={`p-7 flex flex-col ${t.highlight ? "border-accent/60 shadow-[0_0_0_1px_rgba(41,98,255,0.4)]" : ""}`}
              >
                {t.highlight && (
                  <div className="text-[10px] uppercase tracking-widest text-accent mono mb-2">
                    Most Popular
                  </div>
                )}
                <div className="flex items-center gap-2.5 mb-3">
                  <Icon className="w-5 h-5 text-accent" />
                  <h3 className="text-lg font-semibold text-text-bright">{t.name}</h3>
                </div>
                <div className="mb-1">
                  <span className="mono text-3xl font-bold text-text-bright">
                    NT$ {t.price_twd}
                  </span>
                  <span className="text-text-muted text-sm"> / 月</span>
                </div>
                <p className="text-xs text-text-muted mb-5">每日 TOP {t.top_n} 強勢股</p>
                <ul className="space-y-2 text-sm flex-1 mb-6">
                  {t.features.map((f: string) => (
                    <li key={f} className="flex items-start gap-2">
                      <Check className="w-4 h-4 text-up mt-0.5 shrink-0" />
                      <span className="text-text">{f}</span>
                    </li>
                  ))}
                </ul>
                {t.key === "free" ? (
                  <Button variant="secondary" size="lg" disabled>
                    {isCurrent ? "目前方案" : "免費註冊即享"}
                  </Button>
                ) : (
                  <Button
                    size="lg"
                    variant={t.highlight ? "primary" : "secondary"}
                    disabled={busy === t.key || isCurrent}
                    onClick={() => buy(t.key as "pro" | "elite")}
                  >
                    {isCurrent ? "目前方案" : busy === t.key ? "前往金流…" : t.cta}
                  </Button>
                )}
              </Card>
            );
          })}
        </div>

        <p className="text-center text-[11px] text-text-muted mt-10">
          所有方案皆可隨時取消 · 由 Stripe 加密付款 · 發票自動寄送
        </p>
      </main>
    </div>
  );
}
