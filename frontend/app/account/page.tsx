"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { api, type SubscriptionInfo } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AccountPage() {
  const { user, loading, refresh, logout } = useAuth();
  const router = useRouter();
  const [name, setName] = useState("");
  const [lineId, setLineId] = useState("");
  const [no, setNo] = useState(true);
  const [ni, setNi] = useState(true);
  const [nc, setNc] = useState(true);
  const [sub, setSub] = useState<SubscriptionInfo | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (user) {
      setName(user.name ?? "");
      setLineId(user.line_user_id ?? "");
      setNo(user.notify_open);
      setNi(user.notify_intraday);
      setNc(user.notify_close);
      api.subscription().then(setSub).catch(() => {});
    }
  }, [user]);

  if (loading || !user) {
    return (
      <div className="min-h-screen">
        <Topbar />
        <main className="max-w-3xl mx-auto px-6 py-16 text-text-muted text-sm">載入中…</main>
      </div>
    );
  }

  async function save() {
    setMsg(null);
    try {
      await api.updateMe({
        name, line_user_id: lineId || null,
        notify_open: no, notify_intraday: ni, notify_close: nc,
      } as any);
      await refresh();
      setMsg("已儲存 ✓");
    } catch (e: any) {
      setMsg(e?.message ?? "儲存失敗");
    }
  }

  async function testNotify() {
    setMsg(null);
    setTesting(true);
    try {
      await api.notifyTest();
      setMsg("測試推播已送出 (請查看 LINE)");
    } catch (e: any) {
      if (e?.status === 402) setMsg("LINE 推播需 Elite 方案，請先升級");
      else setMsg(e?.message ?? "測試失敗");
    } finally {
      setTesting(false);
    }
  }

  async function manageBilling() {
    try {
      const r = await api.portal();
      window.location.href = r.url;
    } catch (e: any) {
      setMsg(e?.message ?? "billing portal 無法開啟");
    }
  }

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-3xl mx-auto px-6 py-10 space-y-6">
        <h1 className="text-2xl font-semibold text-text-bright tracking-tight">會員中心</h1>

        <Card>
          <CardHeader title="訂閱狀態" subtitle={`方案：${user.plan.toUpperCase()}`}
            right={<Link href="/pricing" className="text-xs text-accent hover:underline">升級 / 變更</Link>} />
          <div className="p-5 grid sm:grid-cols-3 gap-4 text-sm">
            <div>
              <div className="text-[11px] text-text-muted uppercase tracking-wider">月費</div>
              <div className="mono text-text-bright text-xl mt-1">NT$ {sub?.price_twd ?? 0}</div>
            </div>
            <div>
              <div className="text-[11px] text-text-muted uppercase tracking-wider">狀態</div>
              <div className="mono text-text-bright mt-1">{sub?.status ?? "—"}</div>
            </div>
            <div>
              <div className="text-[11px] text-text-muted uppercase tracking-wider">下次續費</div>
              <div className="mono text-text-bright mt-1">{sub?.current_period_end ?? "—"}</div>
            </div>
          </div>
          {user.plan !== "free" && (
            <div className="px-5 pb-5">
              <Button variant="secondary" size="sm" onClick={manageBilling}>
                管理付款方式 / 取消訂閱
              </Button>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader title="個人資料" />
          <div className="p-5 space-y-4">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" value={user.email} disabled />
            </div>
            <div>
              <Label htmlFor="name">姓名</Label>
              <Input id="name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="line">LINE User ID</Label>
              <Input id="line" value={lineId} onChange={(e) => setLineId(e.target.value)} placeholder="U..." />
              <p className="text-[11px] text-text-muted mt-1">
                綁定後可接收每日 TOP 強勢股推播 (Elite 方案)
              </p>
            </div>
            <div className="grid grid-cols-3 gap-3 pt-2">
              {[
                ["開盤觀察 09:00", no, setNo],
                ["盤中提醒 13:25", ni, setNi],
                ["收盤總結 15:30", nc, setNc],
              ].map(([label, val, setter]: any) => (
                <label key={label} className="flex items-center gap-2 text-sm">
                  <input type="checkbox" checked={val} onChange={(e) => setter(e.target.checked)} />
                  <span>{label}</span>
                </label>
              ))}
            </div>
            <div className="flex items-center gap-3 pt-2">
              <Button onClick={save}>儲存</Button>
              <Button variant="secondary" onClick={testNotify} disabled={testing}>
                {testing ? "送出中…" : "發送測試推播"}
              </Button>
              <Button variant="ghost" onClick={() => { logout(); router.push("/"); }}>
                登出
              </Button>
              {msg && <span className="text-xs text-text-muted">{msg}</span>}
            </div>
          </div>
        </Card>
      </main>
    </div>
  );
}
