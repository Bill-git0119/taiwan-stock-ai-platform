"use client";

import Link from "next/link";
import { Activity, TrendingUp, LogOut, User as UserIcon } from "lucide-react";
import { useAuth } from "@/lib/auth";

const PLAN_BADGE: Record<string, string> = {
  free: "bg-line text-text-muted",
  pro: "bg-accent/20 text-accent border border-accent/40",
  elite: "bg-up/20 text-up border border-up/40",
};

export function Topbar() {
  const { user, loading, logout } = useAuth();

  return (
    <header className="h-14 border-b border-line bg-bg-panel flex items-center justify-between px-6">
      <div className="flex items-center gap-6">
        <Link href="/" className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-md bg-accent/20 border border-accent/40 flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-accent" />
          </div>
          <div>
            <div className="text-text-bright font-semibold tracking-tight">
              Taiwan Stock AI
            </div>
            <div className="text-[10px] text-text-muted uppercase tracking-widest">
              Chip · Fundamental · Technical
            </div>
          </div>
        </Link>
        <nav className="hidden md:flex items-center gap-5 text-sm text-text-muted">
          <Link href="/dashboard" className="hover:text-text-bright">Dashboard</Link>
          <Link href="/scanner" className="hover:text-accent font-medium text-text-bright">⚡ Scanner</Link>
          <Link href="/leaderboard" className="hover:text-text-bright">Leaderboard</Link>
          <Link href="/backtest" className="hover:text-text-bright">Backtest</Link>
          <Link href="/blog" className="hover:text-text-bright">Blog</Link>
          <Link href="/pricing" className="hover:text-text-bright">Pricing</Link>
          {user && <Link href="/referral" className="hover:text-accent">推薦</Link>}
          {user && <Link href="/account" className="hover:text-text-bright">Account</Link>}
          {user?.is_admin && <Link href="/admin" className="hover:text-accent">Admin</Link>}
        </nav>
      </div>
      <div className="flex items-center gap-4 text-xs text-text-muted">
        <div className="hidden sm:flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-up" />
          <span className="mono">API OK</span>
        </div>
        {!loading && (user ? (
          <div className="flex items-center gap-3">
            <span className={`px-2 py-0.5 rounded text-[10px] uppercase tracking-wider mono ${PLAN_BADGE[user.plan] ?? PLAN_BADGE.free}`}>
              {user.plan}
            </span>
            <Link href="/account" className="flex items-center gap-1.5 hover:text-text-bright">
              <UserIcon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{user.name || user.email}</span>
            </Link>
            <button onClick={logout} className="hover:text-down" title="登出">
              <LogOut className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <Link href="/login" className="hover:text-text-bright">登入</Link>
            <Link href="/register" className="px-3 py-1 rounded bg-accent text-white text-xs hover:bg-accent/90">
              免費註冊
            </Link>
          </div>
        ))}
      </div>
    </header>
  );
}
