import Link from "next/link";
import { ArrowRight, BarChart3, Brain, LineChart, Shield, TrendingUp } from "lucide-react";
import { Topbar } from "@/components/layout/Topbar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { API_BASE } from "@/lib/api";

export const dynamic = "force-dynamic";

export const metadata = {
  title: "AI 幫你每天找出台股最強股票 · Taiwan Stock AI",
  description: "籌碼 + 財報 + 技術面 + AI 預測，幫你快速找到高勝率機會。每日 TOP 10 強勢股自動推送。",
};

interface LbItem { symbol: string; name: string; rank: number; return_pct: number; entry_price: number; date: string }

async function fetchLeaderboard(): Promise<LbItem[]> {
  try {
    const res = await fetch(`${API_BASE}/api/v1/leaderboard/weekly`, { cache: "no-store" });
    if (!res.ok) return [];
    const j = await res.json();
    return (j.items as LbItem[]).slice(0, 5);
  } catch { return []; }
}

const FAQ: Array<{ q: string; a: string }> = [
  { q: "資料來源是真的嗎？", a: "全部來自 TWSE / TPEX / MOPS 公開資料，每日盤後自動同步，可在 /admin 後台驗證。" },
  { q: "AI 評分會看未來資料嗎？", a: "不會。所有訊號計算嚴格使用當日及之前資料，回測同樣禁用 lookahead，遵守鐵律 IRON_RULES。" },
  { q: "Free 方案有什麼？", a: "每日 TOP 3 強勢股、市場概況、基本搜尋，足夠驗證系統能力。" },
  { q: "Elite 方案能回測嗎？", a: "可以。Elite 方案開放完整回測中心，含 AI Top Rank、均線突破、籌碼跟單三套策略，輸出 CAGR/Sharpe/MaxDD/權益曲線。" },
  { q: "推薦獎勵怎麼運作？", a: "邀請朋友註冊並升級付費後，雙方都有獎勵：1 人 +7 天 Pro、3 人 +30 天 Elite。" },
  { q: "可以隨時取消訂閱嗎？", a: "可以。訂閱由 Stripe 管理，可隨時於 Account 頁面進入 Customer Portal 取消，當期到期後不續扣。" },
];

const FEATURES = [
  { icon: Shield, title: "籌碼分析", desc: "外資 / 投信 / 自營商買賣超 + 主力分點集中度" },
  { icon: BarChart3, title: "基本面分析", desc: "EPS / ROE / 毛利率 / 營收成長 / PEG" },
  { icon: LineChart, title: "技術分析", desc: "MA / MACD / RSI / KD / 布林 / 量能突破" },
  { icon: Brain, title: "AI 預測模型", desc: "5 日上漲機率、10 日報酬區間、勝率與信心度" },
];

export default async function LandingPage() {
  const top = await fetchLeaderboard();

  return (
    <div className="min-h-screen">
      <Topbar />

      {/* Hero */}
      <section className="relative overflow-hidden border-b border-line">
        <div className="absolute inset-0 pointer-events-none opacity-30"
             style={{ background: "radial-gradient(ellipse at top, #2962FF 0%, transparent 60%)" }} />
        <div className="relative max-w-6xl mx-auto px-6 pt-20 pb-24 text-center">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-line bg-bg-panel text-[11px] uppercase tracking-widest text-text-muted">
            <span className="w-1.5 h-1.5 rounded-full bg-up animate-pulse" />
            台股 AI 智能選股 · 真實 TWSE/TPEX/MOPS 資料
          </div>
          <h1 className="mt-6 text-4xl md:text-6xl font-bold tracking-tight text-text-bright leading-tight">
            AI 幫你<span className="text-accent">每天</span>找出台股<br className="hidden md:block" />
            <span className="bg-gradient-to-r from-up to-accent bg-clip-text text-transparent">最強股票</span>
          </h1>
          <p className="mt-6 text-base md:text-lg text-text-muted max-w-2xl mx-auto leading-relaxed">
            籌碼＋財報＋技術面＋AI 預測，幫你快速找到高勝率機會。<br />
            每日盤後自動更新 · LINE 即時推播 · 三維評分一目了然。
          </p>
          <div className="mt-9 flex items-center justify-center gap-3 flex-wrap">
            <Link href="/register">
              <Button size="lg" className="gap-2">立即免費試用 <ArrowRight className="w-4 h-4" /></Button>
            </Link>
            <Link href="/terminal">
              <Button variant="secondary" size="lg">🧠 進入研究終端機</Button>
            </Link>
            <Link href="/scanner">
              <Button variant="secondary" size="lg">⚡ 強勢股 Scanner</Button>
            </Link>
          </div>
          <p className="mt-4 text-[11px] text-text-muted">免信用卡 · 30 秒開通 · Free 方案永久免費</p>
        </div>
      </section>

      {/* Trust signals — verifiable claims only */}
      <section className="border-b border-line">
        <div className="max-w-6xl mx-auto px-6 py-10 grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
          {[
            { num: "3,291", label: "Walk-forward 評估訊號" },
            { num: "TOP 100", label: "5 年 OHLCV 回測" },
            { num: "0", label: "Lookahead bias" },
            { num: "TWSE / TPEX", label: "公開資料源" },
          ].map((s) => (
            <div key={s.label}>
              <div className="text-2xl md:text-3xl font-bold font-mono text-text-bright">{s.num}</div>
              <div className="mt-1 text-xs uppercase tracking-widest text-text-muted">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Feature Grid */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <div className="text-center mb-10">
          <h2 className="text-3xl font-semibold text-text-bright tracking-tight">三維評分 · AI 統一打分</h2>
          <p className="text-sm text-text-muted mt-2">Score = 籌碼 × 0.40 + 基本面 × 0.35 + 技術面 × 0.25</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {FEATURES.map((f) => (
            <Card key={f.title} className="p-6" hover>
              <div className="w-10 h-10 rounded-md bg-accent/15 border border-accent/30 flex items-center justify-center mb-4">
                <f.icon className="w-5 h-5 text-accent" />
              </div>
              <h3 className="text-base font-semibold text-text-bright">{f.title}</h3>
              <p className="text-xs text-text-muted mt-2 leading-relaxed">{f.desc}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* Leaderboard Preview */}
      <section className="border-y border-line bg-bg-panel/50">
        <div className="max-w-5xl mx-auto px-6 py-16">
          <div className="flex items-end justify-between mb-6 flex-wrap gap-3">
            <div>
              <h2 className="text-2xl md:text-3xl font-semibold text-text-bright tracking-tight">本週績效榜</h2>
              <p className="text-sm text-text-muted mt-1">真實透明 · 公開可驗證</p>
            </div>
            <Link href="/leaderboard" className="text-sm text-accent hover:underline">完整榜單 →</Link>
          </div>
          <Card>
            <table className="w-full text-sm">
              <thead className="text-[11px] uppercase tracking-wider text-text-muted">
                <tr>
                  <th className="text-left px-4 py-3">#</th>
                  <th className="text-left px-4 py-3">代號</th>
                  <th className="text-left px-4 py-3">名稱</th>
                  <th className="text-right px-4 py-3">7 日報酬</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {top.length === 0 && (
                  <tr><td colSpan={4} className="px-4 py-6 text-center text-text-muted">資料載入中…</td></tr>
                )}
                {top.map((it) => (
                  <tr key={`${it.date}-${it.symbol}`} className="border-t border-line">
                    <td className="px-4 py-3 text-text-muted">{it.rank}</td>
                    <td className="px-4 py-3 text-text-bright">{it.symbol}</td>
                    <td className="px-4 py-3 font-sans">{it.name}</td>
                    <td className={`px-4 py-3 text-right font-semibold ${it.return_pct >= 0 ? "text-up" : "text-down"}`}>
                      {it.return_pct >= 0 ? "+" : ""}{it.return_pct.toFixed(2)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </section>

      {/* Pricing CTA */}
      <section className="max-w-6xl mx-auto px-6 py-16">
        <div className="text-center mb-10">
          <h2 className="text-3xl font-semibold text-text-bright tracking-tight">選擇你的方案</h2>
          <p className="text-sm text-text-muted mt-2">每月只要一杯咖啡的錢，換來整月的 AI 選股助力</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {[
            { name: "Free", price: "NT$0", desc: "TOP 3 / 日", features: ["每日 TOP 3 強勢股", "市場概況", "基本搜尋"], cta: "立即開始", href: "/register" },
            { name: "Pro", price: "NT$299", desc: "TOP 10 / 日", features: ["每日 TOP 10 強勢股", "AI 預測模型", "LINE 即時推播", "進階篩選"], cta: "升級 Pro", href: "/pricing", featured: true },
            { name: "Elite", price: "NT$599", desc: "TOP 30 + 回測", features: ["每日 TOP 30 強勢股", "完整回測中心", "三套量化策略", "API 存取"], cta: "升級 Elite", href: "/pricing" },
          ].map((p) => (
            <Card key={p.name} className={`p-6 ${p.featured ? "border-accent/60 shadow-[0_0_0_1px_rgba(41,98,255,0.4)]" : ""}`}>
              {p.featured && <div className="text-[10px] uppercase tracking-widest text-accent font-semibold mb-2">最受歡迎</div>}
              <div className="flex items-baseline justify-between">
                <h3 className="text-xl font-semibold text-text-bright">{p.name}</h3>
                <div className="text-right">
                  <div className="text-2xl font-bold text-text-bright font-mono">{p.price}</div>
                  <div className="text-[11px] text-text-muted">/ 月</div>
                </div>
              </div>
              <div className="text-xs text-text-muted mt-1">{p.desc}</div>
              <ul className="mt-5 space-y-2 text-sm text-text">
                {p.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <span className="text-up mt-0.5">✓</span><span>{f}</span>
                  </li>
                ))}
              </ul>
              <Link href={p.href} className="block mt-6">
                <Button className="w-full" variant={p.featured ? "primary" : "secondary"} size="lg">{p.cta}</Button>
              </Link>
            </Card>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t border-line bg-bg-panel/40">
        <div className="max-w-3xl mx-auto px-6 py-16">
          <h2 className="text-3xl font-semibold text-text-bright tracking-tight text-center">常見問題</h2>
          <div className="mt-8 space-y-3">
            {FAQ.map((f) => (
              <details key={f.q} className="group panel p-5 [&_summary::-webkit-details-marker]:hidden">
                <summary className="cursor-pointer flex items-center justify-between text-text-bright font-medium">
                  {f.q}
                  <span className="text-text-muted text-xl group-open:rotate-45 transition-transform">＋</span>
                </summary>
                <p className="mt-3 text-sm text-text-muted leading-relaxed">{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="border-t border-line">
        <div className="max-w-4xl mx-auto px-6 py-20 text-center">
          <TrendingUp className="w-10 h-10 text-accent mx-auto mb-5" />
          <h2 className="text-3xl md:text-4xl font-semibold text-text-bright tracking-tight">
            今天就讓 AI 幫你篩選台股
          </h2>
          <p className="mt-4 text-sm md:text-base text-text-muted">
            交易鐵律自動把關 · 免信用卡 · 30 秒開通
          </p>
          <div className="mt-8 flex items-center justify-center gap-3 flex-wrap">
            <Link href="/register">
              <Button size="lg" className="gap-2">立即免費試用 <ArrowRight className="w-4 h-4" /></Button>
            </Link>
            <Link href="/leaderboard">
              <Button variant="secondary" size="lg">查看績效</Button>
            </Link>
          </div>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="max-w-6xl mx-auto px-6 py-8 text-[11px] text-text-muted text-center">
          Taiwan Stock AI Platform · v0.5.0 · data source: TWSE / TPEX / MOPS · 投資有風險，本平台僅提供分析參考，不構成投資建議
        </div>
      </footer>
    </div>
  );
}
