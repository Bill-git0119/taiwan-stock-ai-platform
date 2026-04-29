"use client";

import { useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { useState } from "react";

export function StockSearch() {
  const router = useRouter();
  const [q, setQ] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const val = q.trim();
    if (!val) return;
    router.push(`/stock/${encodeURIComponent(val)}`);
  };

  return (
    <form onSubmit={submit} className="relative max-w-sm">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
      <input
        type="text"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="搜尋股票代號 (例：2330)"
        className="w-full pl-9 pr-3 py-2 bg-bg-panel border border-line rounded-md
                   text-sm text-text-bright placeholder:text-text-muted mono
                   focus:outline-none focus:border-accent/70
                   transition-colors"
      />
    </form>
  );
}
