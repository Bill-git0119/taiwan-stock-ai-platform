"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Copy, Check, Share2 } from "lucide-react";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface Stats {
  code: string;
  invited: number;
  converted: number;
  granted: number;
  rewards_unlocked: string[];
  next_target: number | null;
  progress: number;
  share_url: string;
}

export default function ReferralPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [siteUrl, setSiteUrl] = useState("");

  useEffect(() => {
    if (loading) return;
    if (!user) { router.push("/login"); return; }
    api.referralMe()
      .then(setStats)
      .catch((e) => setError(e instanceof Error ? e.message : "fetch failed"));
  }, [loading, user, router]);

  useEffect(() => {
    if (typeof window !== "undefined") setSiteUrl(window.location.origin);
  }, []);

  const fullShare = stats ? `${siteUrl}${stats.share_url}` : "";

  async function copy() {
    if (!fullShare) return;
    try {
      await navigator.clipboard.writeText(fullShare);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {}
  }

  async function share() {
    if (!fullShare) return;
    if (typeof navigator !== "undefined" && "share" in navigator) {
      try {
        await (navigator as Navigator & { share: (data: ShareData) => Promise<void> }).share({
          title: "Taiwan Stock AI",
          text: "用我的推薦碼註冊，雙方都有 7 天 Pro 體驗。",
          url: fullShare,
        });
      } catch {}
    } else {
      copy();
    }
  }

  if (loading || !user) {
    return (
      <div className="min-h-screen">
        <Topbar />
        <main className="max-w-3xl mx-auto px-6 py-16 text-text-muted text-sm">驗證權限中…</main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <header>
          <h1 className="text-2xl font-semibold text-text-bright tracking-tight">推薦獎勵</h1>
          <p className="text-xs text-text-muted mt-1">
            邀請朋友升級付費，雙方都有獎勵 · 1 人 +7 天 Pro · 3 人 +30 天 Elite
          </p>
        </header>

        {error && <div className="text-down text-sm">{error}</div>}

        <Card>
          <CardHeader title="你的推薦碼" subtitle="複製連結後分享給朋友" />
          <div className="p-6 space-y-4">
            {!stats ? (
              <Skeleton className="h-20" />
            ) : (
              <>
                <div className="flex items-center gap-3">
                  <code className="flex-1 px-4 py-3 rounded-md bg-bg-elevated border border-line text-text-bright font-mono text-lg tracking-widest">
                    {stats.code}
                  </code>
                  <Button onClick={copy} variant="secondary" size="lg" className="gap-2">
                    {copied ? <Check className="w-4 h-4 text-up" /> : <Copy className="w-4 h-4" />}
                    {copied ? "已複製" : "複製碼"}
                  </Button>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    readOnly
                    value={fullShare}
                    className="flex-1 px-3 py-2 rounded-md bg-bg-elevated border border-line text-text-muted text-xs font-mono"
                  />
                  <Button onClick={share} size="md" className="gap-2">
                    <Share2 className="w-4 h-4" />
                    分享
                  </Button>
                </div>
              </>
            )}
          </div>
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[
            { label: "已邀請", value: stats?.invited ?? "—" },
            { label: "已升級", value: stats?.converted ?? "—" },
            { label: "解鎖獎勵", value: stats?.granted ?? "—" },
          ].map((s) => (
            <Card key={s.label} className="p-5">
              <div className="text-[11px] uppercase tracking-wider text-text-muted">{s.label}</div>
              <div className="mt-2 text-3xl font-semibold text-text-bright font-mono">{s.value}</div>
            </Card>
          ))}
        </div>

        <Card>
          <CardHeader title="獎勵進度" />
          <div className="p-6 space-y-4">
            {!stats ? (
              <Skeleton className="h-12" />
            ) : (
              <>
                <div className="flex items-center justify-between text-xs text-text-muted">
                  <span>下一個目標</span>
                  <span className="text-text-bright font-mono">
                    {stats.next_target ? `${stats.converted} / ${stats.next_target} 人付費升級` : "已達最高獎勵"}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-bg-elevated overflow-hidden">
                  <div
                    className="h-full bg-accent transition-all duration-500"
                    style={{ width: `${Math.round(stats.progress * 100)}%` }}
                  />
                </div>
                <ul className="text-xs text-text-muted space-y-1.5 pt-2">
                  <li className={stats.converted >= 1 ? "text-up" : ""}>
                    ✓ 1 人付費升級 → +7 天 Pro
                  </li>
                  <li className={stats.converted >= 3 ? "text-up" : ""}>
                    ✓ 3 人付費升級 → +30 天 Elite
                  </li>
                </ul>
                {stats.rewards_unlocked.length > 0 && (
                  <div className="pt-2 text-xs text-up">
                    已解鎖：{stats.rewards_unlocked.join(" · ")}
                  </div>
                )}
              </>
            )}
          </div>
        </Card>
      </main>
    </div>
  );
}
