"use client";
import { useCallback, useEffect, useState } from "react";

const KEY = "tsa_watchlist";

function readAll(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.filter((s) => typeof s === "string") : [];
  } catch {
    return [];
  }
}

function writeAll(syms: string[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(syms));
    window.dispatchEvent(new CustomEvent("tsa-watchlist-changed"));
  } catch {}
}

export function useWatchlist() {
  const [symbols, setSymbols] = useState<string[]>([]);

  useEffect(() => {
    setSymbols(readAll());
    const handler = () => setSymbols(readAll());
    window.addEventListener("tsa-watchlist-changed", handler);
    window.addEventListener("storage", handler);
    return () => {
      window.removeEventListener("tsa-watchlist-changed", handler);
      window.removeEventListener("storage", handler);
    };
  }, []);

  const has = useCallback((sym: string) => symbols.includes(sym), [symbols]);

  const toggle = useCallback((sym: string) => {
    const cur = readAll();
    const next = cur.includes(sym) ? cur.filter((s) => s !== sym) : [...cur, sym];
    writeAll(next);
    setSymbols(next);
  }, []);

  const add = useCallback((sym: string) => {
    const cur = readAll();
    if (cur.includes(sym)) return;
    const next = [...cur, sym];
    writeAll(next);
    setSymbols(next);
  }, []);

  const remove = useCallback((sym: string) => {
    const next = readAll().filter((s) => s !== sym);
    writeAll(next);
    setSymbols(next);
  }, []);

  const clear = useCallback(() => {
    writeAll([]);
    setSymbols([]);
  }, []);

  return { symbols, has, toggle, add, remove, clear };
}
