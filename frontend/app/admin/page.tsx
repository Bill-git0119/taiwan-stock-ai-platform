"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { StatCard } from "@/components/dashboard/StatCard";
import { useAuth } from "@/lib/auth";
import { api } from "@/lib/api";

export default function AdminPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [subs, setSubs] = useState<any[]>([]);
  const [revenue, setRevenue] = useState<any>(null);
  const [notifs, setNotifs] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loading) return;
    if (!user) { router.push("/login"); return; }
    if (!user.is_admin) { router.push("/"); return; }
    Promise.all([
      api.adminStats(), api.adminUsers(), api.adminSubs(),
      api.adminRevenue(), api.adminNotifications(),
    ]).then(([s, u, sb, r, n]) => {
      setStats(s); setUsers(u); setSubs(sb); setRevenue(r); setNotifs(n);
    }).catch((e) => setError(e?.message ?? "load failed"));
  }, [loading, user, router]);

  if (loading || !user || !user.is_admin) {
    return (
      <div className="min-h-screen">
        <Topbar />
        <main className="max-w-7xl mx-auto px-6 py-16 text-text-muted text-sm">驗證權限中…</main>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
        <h1 className="text-2xl font-semibold text-text-bright tracking-tight">Admin Dashboard</h1>
        {error && <div className="text-down text-sm">{error}</div>}

        {stats && (
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            <StatCard label="總會員" value={String(stats.total_users)} tone="neutral" />
            <StatCard label="活躍會員" value={String(stats.active_users)} tone="up" />
            <StatCard label="付費會員" value={String(stats.paid_users)} tone="up" delta={`Pro ${stats.pro_users} / Elite ${stats.elite_users}`} />
            <StatCard label="MRR" value={`NT$ ${(stats.mrr_twd ?? 0).toLocaleString()}`} tone="up" />
            <StatCard label="24h 推播" value={String(stats.notifications_24h ?? 0)} delta={`成功 ${(stats.notify_success_rate ?? 0).toFixed?.(1) ?? "—"}%`} />
          </div>
        )}

        <Card>
          <CardHeader title="會員列表" right={<span className="text-[11px] text-text-muted mono">{users.length}</span>} />
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[700px]">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-text-muted">
                  <th className="text-left px-5 py-2">Email</th>
                  <th className="text-left py-2">姓名</th>
                  <th className="text-left py-2">方案</th>
                  <th className="text-left py-2">建立時間</th>
                  <th className="text-left py-2 px-5">LINE</th>
                </tr>
              </thead>
              <tbody>
                {users.slice(0, 50).map((u) => (
                  <tr key={u.id} className="border-t border-line">
                    <td className="px-5 py-2 mono">{u.email}</td>
                    <td className="py-2">{u.name ?? "—"}</td>
                    <td className="py-2 mono uppercase">{u.plan}</td>
                    <td className="py-2 mono text-text-muted text-xs">{u.created_at?.slice(0, 10)}</td>
                    <td className="py-2 px-5 mono text-xs">{u.line_user_id ? "✓" : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <div className="grid lg:grid-cols-2 gap-5">
          <Card>
            <CardHeader title="訂閱記錄" right={<span className="text-[11px] text-text-muted mono">{subs.length}</span>} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-text-muted">
                    <th className="text-left px-5 py-2">User</th>
                    <th className="text-left py-2">方案</th>
                    <th className="text-left py-2">狀態</th>
                    <th className="text-right px-5 py-2">月費</th>
                  </tr>
                </thead>
                <tbody>
                  {subs.slice(0, 20).map((s) => (
                    <tr key={s.id} className="border-t border-line">
                      <td className="px-5 py-2 mono text-xs">{s.user_email ?? s.user_id}</td>
                      <td className="py-2 mono uppercase">{s.plan}</td>
                      <td className="py-2 text-xs">{s.status}</td>
                      <td className="py-2 px-5 mono text-right">{s.price_twd}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <CardHeader title="近期推播" right={<span className="text-[11px] text-text-muted mono">{notifs.length}</span>} />
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[11px] uppercase tracking-wider text-text-muted">
                    <th className="text-left px-5 py-2">時間</th>
                    <th className="text-left py-2">類別</th>
                    <th className="text-left py-2">狀態</th>
                    <th className="text-left py-2 px-5">錯誤</th>
                  </tr>
                </thead>
                <tbody>
                  {notifs.slice(0, 20).map((n) => (
                    <tr key={n.id} className="border-t border-line">
                      <td className="px-5 py-2 mono text-xs">{n.created_at?.slice(0, 16)}</td>
                      <td className="py-2 text-xs">{n.kind}</td>
                      <td className={`py-2 text-xs ${n.success ? "text-up" : "text-down"}`}>
                        {n.success ? "成功" : "失敗"}
                      </td>
                      <td className="py-2 px-5 text-xs text-text-muted truncate max-w-[200px]">{n.error ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        {revenue && (
          <Card>
            <CardHeader title="收入概覽" subtitle={`MRR: NT$ ${(revenue.mrr_twd ?? 0).toLocaleString()}`} />
            <div className="p-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div>
                <div className="text-[11px] text-text-muted uppercase">Pro 訂閱數</div>
                <div className="mono text-xl text-text-bright">{revenue.pro_count ?? 0}</div>
              </div>
              <div>
                <div className="text-[11px] text-text-muted uppercase">Elite 訂閱數</div>
                <div className="mono text-xl text-text-bright">{revenue.elite_count ?? 0}</div>
              </div>
              <div>
                <div className="text-[11px] text-text-muted uppercase">本月收入</div>
                <div className="mono text-xl text-up">NT$ {(revenue.this_month_twd ?? 0).toLocaleString()}</div>
              </div>
              <div>
                <div className="text-[11px] text-text-muted uppercase">累積收入</div>
                <div className="mono text-xl text-up">NT$ {(revenue.lifetime_twd ?? 0).toLocaleString()}</div>
              </div>
            </div>
          </Card>
        )}
      </main>
    </div>
  );
}
