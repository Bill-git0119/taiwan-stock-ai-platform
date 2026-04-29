"use client";

import { useEffect, useRef } from "react";

interface Props {
  symbol: string;
  market?: "TWSE" | "TPEX";
}

export function TradingViewChart({ symbol, market = "TWSE" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const scriptRef = useRef<HTMLScriptElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.innerHTML =
      '<div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>';

    const script = document.createElement("script");
    script.src =
      "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.type = "text/javascript";
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: `${market}:${symbol}`,
      interval: "D",
      timezone: "Asia/Taipei",
      theme: "dark",
      style: "1",
      locale: "zh_TW",
      backgroundColor: "#0B0E11",
      gridColor: "rgba(42, 46, 57, 0.6)",
      withdateranges: true,
      hide_side_toolbar: false,
      allow_symbol_change: true,
      calendar: false,
      support_host: "https://www.tradingview.com",
    });
    container.appendChild(script);
    scriptRef.current = script;

    return () => {
      container.innerHTML = "";
    };
  }, [symbol, market]);

  return (
    <div
      ref={containerRef}
      className="tradingview-widget-container h-[520px] w-full rounded-lg overflow-hidden border border-line"
    />
  );
}
