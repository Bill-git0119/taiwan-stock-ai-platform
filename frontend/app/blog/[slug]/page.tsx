import Link from "next/link";
import { notFound } from "next/navigation";
import { Topbar } from "@/components/layout/Topbar";
import { API_BASE } from "@/lib/api";

export const dynamic = "force-dynamic";

interface Post {
  slug: string;
  title: string;
  summary: string;
  body_md: string;
  tags: string[];
  published_at: string;
}

async function fetchPost(slug: string): Promise<Post | null> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/blog/${encodeURIComponent(slug)}`, { cache: "no-store" });
    if (res.status === 404) return null;
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = await fetchPost(slug);
  if (!post) return { title: "Not found" };
  return { title: post.title, description: post.summary };
}

function renderMarkdown(md: string): string {
  const escape = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = md.split(/\r?\n/);
  const out: string[] = [];
  let inList = false;
  const closeList = () => { if (inList) { out.push("</ul>"); inList = false; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (line.startsWith("# ")) { closeList(); out.push(`<h1 class="text-3xl font-semibold text-text-bright mt-8 mb-4">${escape(line.slice(2))}</h1>`); continue; }
    if (line.startsWith("## ")) { closeList(); out.push(`<h2 class="text-2xl font-semibold text-text-bright mt-7 mb-3">${escape(line.slice(3))}</h2>`); continue; }
    if (line.startsWith("### ")) { closeList(); out.push(`<h3 class="text-xl font-semibold text-text-bright mt-6 mb-2">${escape(line.slice(4))}</h3>`); continue; }
    if (line.startsWith("- ") || line.startsWith("* ")) {
      if (!inList) { out.push(`<ul class="list-disc pl-6 my-3 space-y-1 text-text">`); inList = true; }
      out.push(`<li>${escape(line.slice(2))}</li>`);
      continue;
    }
    if (!line.trim()) { closeList(); continue; }
    closeList();
    let html = escape(line);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="text-text-bright">$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    html = html.replace(/`([^`]+)`/g, '<code class="px-1.5 py-0.5 rounded bg-bg-elevated text-accent font-mono text-sm">$1</code>');
    out.push(`<p class="my-3 text-text leading-relaxed">${html}</p>`);
  }
  closeList();
  return out.join("\n");
}

export default async function BlogPostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const post = await fetchPost(slug);
  if (!post) notFound();
  return (
    <div className="min-h-screen">
      <Topbar />
      <main className="max-w-3xl mx-auto px-6 py-10">
        <Link href="/blog" className="text-xs text-text-muted hover:text-text-bright">← 返回部落格</Link>
        <article className="mt-4">
          <header className="border-b border-line pb-6">
            <h1 className="text-3xl md:text-4xl font-semibold text-text-bright tracking-tight">{post.title}</h1>
            <div className="mt-3 flex items-center gap-3 text-xs text-text-muted">
              <span className="font-mono">{post.published_at?.slice(0, 10)}</span>
              <div className="flex gap-2 flex-wrap">
                {post.tags?.map((t) => (
                  <span key={t} className="px-2 py-0.5 rounded bg-bg-elevated border border-line">{t}</span>
                ))}
              </div>
            </div>
          </header>
          <div
            className="prose prose-invert max-w-none mt-6"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(post.body_md) }}
          />
        </article>
      </main>
    </div>
  );
}
