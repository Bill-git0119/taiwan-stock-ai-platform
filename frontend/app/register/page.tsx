"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth";
import { captureRef, readRef, clearRef } from "@/lib/referral";

function RegisterInner() {
  const { register } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [ref, setRef] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fromUrl = search.get("ref");
    if (fromUrl) captureRef(fromUrl);
    setRef(readRef());
  }, [search]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("密碼至少 8 碼");
      return;
    }
    setLoading(true);
    try {
      await register(email, password, name || undefined, ref || undefined);
      clearRef();
      router.push("/dashboard");
    } catch (e) {
      const msg = e instanceof Error ? e.message : "註冊失敗";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader title="免費註冊" subtitle="3 秒開通 Free 方案，每日 TOP 3 強勢股" />
      <form onSubmit={onSubmit} className="p-6 space-y-4">
        <div>
          <Label htmlFor="name">姓名</Label>
          <Input id="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="可選" />
        </div>
        <div>
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" required value={email}
                 onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
        </div>
        <div>
          <Label htmlFor="password">密碼</Label>
          <Input id="password" type="password" required value={password}
                 onChange={(e) => setPassword(e.target.value)} placeholder="至少 8 碼" />
        </div>
        {ref && (
          <div className="rounded-md border border-accent/40 bg-accent/10 px-3 py-2 text-xs text-text-bright">
            已套用推薦碼 <span className="font-mono font-semibold">{ref}</span> · 雙方都有獎勵
          </div>
        )}
        {error && <div className="text-xs text-down">{error}</div>}
        <Button type="submit" disabled={loading} size="lg" className="w-full">
          {loading ? "註冊中…" : "建立帳號"}
        </Button>
        <div className="text-xs text-text-muted text-center pt-2">
          已有帳號？<Link href="/login" className="text-accent hover:underline">登入</Link>
        </div>
      </form>
    </Card>
  );
}

export default function RegisterPage() {
  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-md mx-auto px-6 py-16">
        <Suspense fallback={<div className="text-text-muted text-sm">載入中…</div>}>
          <RegisterInner />
        </Suspense>
      </main>
    </div>
  );
}
