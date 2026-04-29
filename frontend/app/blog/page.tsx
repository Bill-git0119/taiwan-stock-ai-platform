import Link from "next/link";
import { Topbar } from "@/components/layout/Topbar";
import { Card } from "@/components/ui/Card";
import { API_BASE } from "@/lib/api";

export const dynamic = "force-dynamic";
export const metadata = {
  title: "Blog · 台股 AI 觀點",
  description: "外資籌碼、AI 選股實證、技術分析教學 · 每日更新",
};

interface Post {
  slug: string;
  title: string;
  summary: string;
  tags: string[];
  published_at: string;
}

async function fetchPosts(): Promise<Post[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/blog/`, { cache: "no-store" });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export default async function BlogIndex() {
  const posts = await fetchPosts();
  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-4xl mx-auto px-6 py-10 space-y-6">
        <header>
          <h1 className="text-3xl font-semibold text-text-bright tracking-tight">部落格</h1>
          <p className="text-sm text-text-muted mt-2">
            外資籌碼、AI 選股實證、技術分析教學 · 每日更新
          </p>
        </header>

        {posts.length === 0 ? (
          <Card className="p-8 text-center text-text-muted text-sm">尚無文章</Card>
        ) : (
          <div className="space-y-4">
            {posts.map((p) => (
              <Link key={p.slug} href={`/blog/${p.slug}`} className="block">
                <Card hover className="p-5">
                  <div className="flex items-baseline justify-between gap-3">
                    <h2 className="text-lg font-semibold text-text-bright">{p.title}</h2>
                    <span className="text-[11px] text-text-muted font-mono whitespace-nowrap">
                      {p.published_at?.slice(0, 10)}
                    </span>
                  </div>
                  <p className="text-sm text-text-muted mt-2">{p.summary}</p>
                  {p.tags?.length > 0 && (
                    <div className="mt-3 flex gap-2 flex-wrap">
                      {p.tags.map((t) => (
                        <span key={t} className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded bg-bg-elevated border border-line text-text-muted">
                          {t}
                        </span>
                      ))}
                    </div>
                  )}
                </Card>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
