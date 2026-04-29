import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";

export default function NotFound() {
  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-3xl mx-auto px-6 py-20 text-center">
        <div className="mono text-6xl text-text-muted">404</div>
        <h1 className="mt-4 text-xl text-text-bright">找不到這支股票</h1>
        <p className="mt-2 text-sm text-text-muted">
          可能尚未被資料收集器抓進資料庫，或代號不存在。
        </p>
        <Link
          href="/"
          className="mt-6 inline-block text-xs text-accent hover:underline"
        >
          ← 返回 Dashboard
        </Link>
      </main>
    </div>
  );
}
