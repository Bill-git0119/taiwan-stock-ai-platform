"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { Topbar } from "@/components/layout/Topbar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Input, Label } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      router.push("/");
    } catch (e: any) {
      setError(e?.message ?? "登入失敗");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-md mx-auto px-6 py-16">
        <Card>
          <CardHeader title="登入" subtitle="使用您的 Email 與密碼" />
          <form onSubmit={onSubmit} className="p-6 space-y-4">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" required value={email}
                     onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
            </div>
            <div>
              <Label htmlFor="password">密碼</Label>
              <Input id="password" type="password" required value={password}
                     onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" />
            </div>
            {error && <div className="text-xs text-down">{error}</div>}
            <Button type="submit" disabled={loading} size="lg" className="w-full">
              {loading ? "登入中…" : "登入"}
            </Button>
            <div className="flex items-center justify-between text-xs text-text-muted pt-2">
              <Link href="/forgot-password" className="hover:text-accent">忘記密碼？</Link>
              <Link href="/register" className="hover:text-accent">建立新帳號</Link>
            </div>
          </form>
        </Card>
      </main>
    </div>
  );
}
