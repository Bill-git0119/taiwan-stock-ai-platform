"use client";

import { Star } from "lucide-react";
import { useWatchlist } from "@/lib/watchlist";
import { cn } from "@/lib/utils";

export function WatchlistToggle({ symbol }: { symbol: string }) {
  const wl = useWatchlist();
  const starred = wl.has(symbol);
  return (
    <button
      onClick={() => wl.toggle(symbol)}
      title={starred ? "從 watchlist 移除" : "加入 watchlist"}
      className={cn(
        "inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-[11px] font-medium transition-colors",
        starred
          ? "bg-amber-400/15 text-amber-300 border-amber-400/40"
          : "bg-bg-elevated text-text-muted border-line hover:text-text-bright",
      )}
    >
      <Star className={cn("w-3.5 h-3.5", starred && "fill-amber-300")} />
      {starred ? "已加入" : "加入 Watchlist"}
    </button>
  );
}
