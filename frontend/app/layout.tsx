import type { Metadata, Viewport } from "next";
import Script from "next/script";
import "./globals.css";
import { AuthProvider } from "@/lib/auth";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://taiwan-stock-ai.example.com";
const GA_ID = process.env.NEXT_PUBLIC_GA_ID;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "Taiwan Stock AI Platform — 台股 AI 智能選股",
    template: "%s · Taiwan Stock AI",
  },
  description:
    "AI 驅動的台股每日 TOP 10 強勢股 · 籌碼 × 基本面 × 技術面三維評分 · LINE 即時推播 · 真實 TWSE/TPEX/MOPS 資料",
  keywords: ["台股", "選股", "AI", "籌碼", "外資", "TOP10", "技術分析", "基本面"],
  manifest: "/manifest.json",
  applicationName: "Taiwan Stock AI",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "TW Stock AI",
  },
  icons: {
    icon: [{ url: "/icon-192.svg", type: "image/svg+xml" }],
    apple: [{ url: "/icon-192.svg" }],
  },
  openGraph: {
    type: "website",
    title: "Taiwan Stock AI Platform",
    description: "AI 驅動的台股每日 TOP 10 強勢股 · 三維評分系統",
    url: SITE_URL,
    siteName: "Taiwan Stock AI",
    locale: "zh_TW",
  },
  twitter: { card: "summary_large_image", title: "Taiwan Stock AI Platform" },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#0B0E11",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-Hant" className="dark">
      <body>
        {GA_ID && (
          <>
            <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
            <Script id="ga-init" strategy="afterInteractive">
              {`window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}gtag('js',new Date());gtag('config','${GA_ID}');`}
            </Script>
          </>
        )}
        <Script id="sw-register" strategy="afterInteractive">
          {`if ('serviceWorker' in navigator) { window.addEventListener('load', function () { navigator.serviceWorker.register('/sw.js').catch(function(){}); }); }`}
        </Script>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
