"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState("");
  const [newPw, setNewPw] = useState("");
  const [step, setStep] = useState<"request" | "reset" | "done">("request");
  const [devToken, setDevToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onRequest(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api.forgotPassword(email);
      setDevToken(r.dev_reset_token ?? null);
      setStep("reset");
    } catch (e: any) {
      setError(e?.message ?? "請求失敗");
    }
  }

  async function onReset(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api.resetPassword(token, newPw);
      setStep("done");
    } catch (e: any) {
      setError(e?.message ?? "重設失敗");
    }
  }

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-md mx-auto px-6 py-16">
        <Card>
          <CardHeader title="忘記密碼" subtitle="輸入 Email 取得重設連結" />
          {step === "request" && (
            <form onSubmit={onRequest} className="p-6 space-y-4">
              <div>
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" required value={email}
                       onChange={(e) => setEmail(e.target.value)} />
              </div>
              {error && <div className="text-xs text-down">{error}</div>}
              <Button type="submit" size="lg" className="w-full">寄送重設連結</Button>
            </form>
          )}
          {step === "reset" && (
            <form onSubmit={onReset} className="p-6 space-y-4">
              <p className="text-xs text-text-muted">
                重設信件已寄出。請從信件中複製 token 並設定新密碼。
              </p>
              {devToken && (
                <div className="p-3 rounded bg-bg-elevated border border-line text-[11px] mono break-all">
                  <div className="text-text-muted mb-1">Dev token (開發環境):</div>
                  {devToken}
                </div>
              )}
              <div>
                <Label htmlFor="token">Reset token</Label>
                <Input id="token" required value={token}
                       onChange={(e) => setToken(e.target.value)} />
              </div>
              <div>
                <Label htmlFor="np">新密碼</Label>
                <Input id="np" type="password" required value={newPw}
                       onChange={(e) => setNewPw(e.target.value)} placeholder="至少 8 碼" />
              </div>
              {error && <div className="text-xs text-down">{error}</div>}
              <Button type="submit" size="lg" className="w-full">重設密碼</Button>
            </form>
          )}
          {step === "done" && (
            <div className="p-6 space-y-4 text-sm">
              <div className="text-up">密碼已重設成功 ✓</div>
              <Link href="/login" className="text-accent hover:underline text-xs">前往登入</Link>
            </div>
          )}
        </Card>
      </main>
    </div>
  );
}
