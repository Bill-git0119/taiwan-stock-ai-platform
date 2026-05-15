"use client";

import Link from "next/link";
import { Activity, TrendingUp } from "lucide-react";

export function Topbar() {
  return (
    <header className="h-14 border-b border-line bg-bg-panel flex items-center justify-between px-6">
      <div className="flex items-center gap-6">
        <Link href="/" className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-md bg-accent/20 border border-accent/40 flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-accent" />
          </div>
          <div>
            <div className="text-text-bright font-semibold tracking-tight">
              Taiwan Stock AI · Research Desk
            </div>
            <div className="text-[10px] text-text-muted uppercase tracking-widest">
              Local single-user · Chip · Fundamental · Technical
            </div>
          </div>
        </Link>
        <nav className="hidden md:flex items-center gap-5 text-sm text-text-muted">
          <Link href="/terminal" className="hover:text-accent font-medium text-text-bright">🧠 Terminal</Link>
          <Link href="/dashboard" className="hover:text-text-bright">Dashboard</Link>
          <Link href="/scanner" className="hover:text-accent font-medium text-text-bright">⚡ Scanner</Link>
          <Link href="/leaderboard" className="hover:text-text-bright">Leaderboard</Link>
          <Link href="/backtest" className="hover:text-text-bright">Backtest</Link>
        </nav>
      </div>
      <div className="flex items-center gap-4 text-xs text-text-muted">
        <div className="hidden sm:flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-up" />
          <span className="mono">API OK</span>
        </div>
        <span className="mono text-[10px] uppercase tracking-widest text-text-muted">
          LOCAL MODE
        </span>
      </div>
    </header>
  );
}
