# Taiwan Stock AI · Local Research Desk

> Single-user research workstation for Taiwan equities.
> Phase 1-9 (P0 audit + 9 phases) shipped 2026-05-15.

---

## 1. System architecture

```
                       ┌────────────────────────────────────────┐
                       │  Workspace UI (Next.js — /workspace)   │
                       │  market_state · datahub · decisions    │
                       │  long-term buckets · LLM brief         │
                       └──────────────────┬─────────────────────┘
                                          │  HTTP
              ┌───────────────────────────┴───────────────────────────┐
              │                FastAPI /api/v1                        │
              │                                                       │
              │   /market/state    /datahub/*    /decisions/short-term│
              │   /long-term/*     /narrative-v2/daily-brief          │
              │   /scheduler/*     legacy: scanner, brief, terminal   │
              └───────────────────────────┬───────────────────────────┘
                                          │
   ┌──────────────────────────────────────┼──────────────────────────────────────┐
   │                                      │                                      │
   ▼                                      ▼                                      ▼
┌────────────────────────┐   ┌────────────────────────┐    ┌────────────────────────┐
│  Decision plane        │   │  Research plane        │    │  Data plane            │
│                        │   │                        │    │  (app/datahub/)        │
│  decision_engine       │   │  edge_signals          │    │                        │
│   ↑ market_state       │   │  strategy_metrics      │    │  collectors/           │
│   ↑ scanner_service    │   │  strategy_registry     │    │   yfinance_daily       │
│   ↑ ranker (gate)      │   │   ranker (Phase 4)     │    │   twse_chips           │
│  long_term_engine      │   │   research_quality     │    │   macro_signals        │
│  llm_narrative         │   │  correlation_analyzer  │    │  validators/integrity  │
└──────────┬─────────────┘   │  stress_runner         │    │                        │
           │                 └────────────────────────┘    │  DataFreshness         │
           ▼                                               │  DataIntegrityReport   │
┌────────────────────────┐                                 └──────────┬─────────────┘
│   strategy/            │                                            │
│   trade_plan_engine    │                                            ▼
│   market_regime        │                          ┌──────────────────────────────┐
└────────────────────────┘                          │  SQLite (operational)        │
                                                    │  + DuckDB (future research)  │
                                                    └──────────────────────────────┘
                                                                │
                                                                ▼
                                              ┌──────────────────────────────────┐
                                              │  APScheduler  (Asia/Taipei)      │
                                              │  12 weekday jobs + 1 weekend     │
                                              └──────────────────────────────────┘
```

---

## 2. Daily SOP (`backend/app/services/scheduler.py`)

| 時間 (TPE) | Job | 內容 |
|---|---|---|
| 08:30 | `premarket_prep`       | 拉 macro snapshot（VIX/DXY/^GSPC/^TWII/US10Y）+ run integrity checks |
| 09:00 | `opening_regime`       | 計算 `MarketState` 並 warm cache（workspace 早盤打開即時讀到） |
| 12:00 | `midday_refresh`       | yfinance rolling 5 日刷新（盤中觀察 gap fill） |
| 13:30 | `close_prep`           | 預先跑一輪 scanner 快取結果 |
| 15:10 | `ingest_daily`         | yfinance.daily + twse.chips 完整當日抓取 |
| 15:30 | `run_scoring`          | 重算 Scores，更新 `stocks:top30` cache |
| 15:35 | `persist_signals`      | scanner(persist=True) 寫今日 LONG 進 `edge_signals` |
| 16:00 | `evaluate_signals`     | 走 7 個交易日對未評估 signal 標 TP/SL/timeout |
| 17:00 | `research_refresh`     | `rank_all` + 寫 `StrategyPerformanceDaily` 快照 |
| 18:00 | `narrative_warm`       | 產生隔天的 daily brief（LLM 或 stub）+ 14h cache |
| 23:00 | `strategy_validation`  | 相關性矩陣 + universe rebuild |
| Sat 02:00 | `integrity_check`  | 跑所有 integrity validators，severity 寫進 DB |

每個 job 都會在 `data_freshness` 表留下 `last_attempted_at` / `last_succeeded_at` / `consecutive_failures` / `last_error`。Workspace UI 直接讀出顯示。

---

## 3. 真實 edge 統計（本地 DB · 2026-05-14 close）

**資料規模：** 94 stocks · 114,765 OHLCV bars · 3,297 EdgeSignals (3,291 evaluated)

### 3.1 by setup（90 日窗口）

| Setup | n | win-rate | expectancy R | profit factor | avg MFE R | avg MAE R |
|---|---|---|---|---|---|---|
| `ma20_support_bounce`    | 2,778 | **52.7%** | **+0.090** | (見 ranker) | +0.58 | −0.48 |
| `trend_breakout_retest`  |   513 | 47.8%     | +0.023     | (見 ranker) | +0.41 | −0.40 |

### 3.2 by regime

| Regime | n | avg R |
|---|---|---|
| `trending_up`       | 2,712 | **+0.096** |
| `trending_up_weak`  |   579 | +0.001 |

**結論：** 兩個 setup 在 `trending_up` 中都有正期望值；`trending_up_weak` 邊際持平 → MarketState 的 exposure_mult 在弱多頭時降到 0.75 是合理的。

### 3.3 by sector（top by sample size）

| 族群 | n | avg R |
|---|---|---|
| **半導體**     | 601 | **+0.240** |
| **電子零組件** | 391 | **+0.211** |
| **塑膠**       | 120 | +0.181 |
| 金融           | 658 | +0.148 |
| ETF            | 118 | +0.124 |
| 電信網路       | 308 | +0.058 |
| 電腦週邊       | 226 | −0.061 |
| 其他電子       | 157 | −0.070 |
| 電腦           | 115 | −0.058 |
| 航運           | 178 | **−0.204** |

**結論：** 半導體 / 電子零組件兩個族群上 setup 期望值最高；航運在 90 日窗口表現最差 → 在 cyclical bucket 標記但短線進場要先看相對強度（RS）。

---

## 4. 哪些策略真的有效（Phase 4 gate verdict）

`ma20_support_bounce` 與 `trend_breakout_retest` 的當前狀態，依 Phase 4 強化後的 GATE：

| Strategy | Live n | Win | Exp R | Phase-4 status | 阻擋條件（若有）|
|---|---|---|---|---|---|
| `ma20_support_bounce`    | 2,778 | 52.7% | +0.090 | **`ACTIVE`** *（heuristic gate）* 但 OOS Sharpe / regime-consistency 尚未跑 lab → research_quality 為 RESEARCH_ONLY → 最終取較保守者 = `WATCH` |
| `trend_breakout_retest`  |   513 | 47.8% | +0.023 | **`WATCH`** — expectancy 接近 0；需要更多樣本或 lab 驗證 |

**判讀：** 兩個 setup 都還沒進入 `ACTIVE` —— 因為 Phase 4 提高了門檻並引入 research_quality 共識制。要進 `ACTIVE` 還需要：
- 跑 strategy_lab walk-forward → 補 OOS Sharpe ≥ 1.0
- 跑 Monte Carlo → 補 MC profitable ≥ 65%
- 跑 cross-regime consistency 評估 ≥ 60%

這就是 Phase 4 想達到的效果：**不靠單一指標就讓策略上線，要全面通過才能 ACTIVE。**

---

## 5. 哪些策略已被淘汰

目前 codebase 沒有 explicit DISABLED 的 setup（兩個 setup 都還在 WATCH）。被 disable 的條件：

- sample_size < 100 + lab 也沒跑 → `UNKNOWN`（從未上線）
- live expectancy 連續 < 0 + 連續虧損 > 8 → `DISABLED`
- 與其他 ACTIVE 策略高度相關（`correlation_flagged`）且樣本不足 → `DISABLED`
- decay label = "broken"（最近表現急遽劣化）→ research_quality `DISABLED`

舊版本曾經測試過的、未進 codebase 的：盲目 chase momentum、無 stop 的 mean-reversion → 都在設計階段被 iron rule（RR ≥ 1.5, risk ≤ 1%, hard stop）擋掉。

---

## 6. 下一步研究方向（不寫程式只列方向）

按優先序：

1. **接 MOPS / FinMind fundamentals**
   - fundamentals_wired 一旦 true，COMPOUNDER bucket 才真的能信
   - confidence formula 才能完整使用 chip × 0.40 + fund × 0.35 + tech × 0.25 而不是 0.65 重新加權

2. **strategy_lab 跑 walk-forward + Monte Carlo on the 2 active setups**
   - 補齊 OOS Sharpe / OOS PF / MC profitable / regime consistency
   - 這是兩個 setup 從 WATCH 進 ACTIVE 的唯一途徑

3. **VWAP + 開盤區間（ORB）setup 第三個**
   - 目前都是 EOD-only 訊號；當沖手會抱怨
   - 需要 intraday 5-min OHLCV pipeline（TWSE quote 拉 + transform）

4. **接真實 LLM key（Claude / GPT）**
   - 目前 narrative 是 stub，內容紮實但格式扁
   - 一旦接上模型，daily brief 會升級為實際 prose

5. **PTT / Dcard / Threads 情緒源**
   - 警告：每 2-3 個月會壞一次，需要長期維護成本評估
   - 不該成為主訊號，只是 catalyst tag

6. **DuckDB research database**
   - SQLite 已撐起 operational；DuckDB 給 ad-hoc 分析（columnar 比 SQLite 快 10-100×）
   - 把 evaluated edge_signals 同步進 DuckDB，可以用 pandas 直接分析

7. **stress 測試 6 個歷史 regime segment**
   - 2020 covid crash / 2022 bear / 2024 AI rally / 2025 sideways …
   - 對每個 setup 跑 stress_runner 看跨 regime 表現

8. **portfolio_backtester 多策略並行**
   - 目前只測單策略；真實 desk 會同時跑 ma20 + breakout
   - 加上 max_concurrent_positions cap 看 portfolio 等級績效

---

## 7. 每日使用流程（5 分鐘）

```
08:30   排程跑完 → workspace 已準備好
09:00   你打開瀏覽器 → /workspace
        ① 看 Market State：今天 regime / risk_on / allowed setups
        ② 看 Daily Brief：6 段，1 分鐘讀完
        ③ 看 Short-Term Decisions：actionable 區塊（已被 gate 過）
            - 每列：信心 / RR / 進場 / SL / TP / RS / 族群 / status / why_now
            - 點 symbol 進 /stock/X 看完整 TradePlanCard + position sizer
        ④ 看 Long-Term Buckets：COMPOUNDER / TURNAROUND（如 fundamentals OK）
        ⑤ 看 Data Sources：確認 freshness 都綠燈
盤中    /workspace 每 30 分鐘按 Refresh
15:30+  排程自動 ingest + score + persist signals → 17 點看完整研究刷新
```

---

## 8. 鐵律快查（hard-coded 不可商量）

| 規則 | 數值 | 位置 |
|---|---|---|
| RR 最小            | ≥ 1.5     | `trade_plan_engine.MIN_RR` |
| 單筆風險           | ≤ 1%      | `RISK_PCT_CAP` |
| 手續費（單邊）     | 0.05%     | `COMMISSION_BPS` |
| 滑點（單邊）       | 0.05%     | `SLIPPAGE_BPS` |
| OOS Sharpe         | ≥ 1.0     | `ranker.GATE['min_oos_sharpe']` |
| OOS PF             | ≥ 1.3     | `ranker.GATE['min_oos_pf']` |
| Max DD（R）        | ≥ −25     | `ranker.GATE['max_drawdown_r']` |
| Sample size        | ≥ 100     | `ranker.GATE['min_sample_size']` |
| Monte Carlo 獲利率 | ≥ 65%     | `ranker.GATE['min_mc_profitable']` |
| Regime consistency | ≥ 60%     | `ranker.GATE['min_regime_consist']` |
| 連續虧損上限       | ≤ 8       | `ranker.GATE['max_consec_loss']` |

任何 setup / signal 違反任一條，自動被 gate → 不會出現在 `actionable` 區塊。

---

## 9. 沒有做的、不該做的

- ❌ **多人 / 訂閱 / Stripe / auth** —— Phase 1 已全部移除
- ❌ **Render / Vercel 雲端部署** —— 改本地單機
- ❌ **合成 / mock 資料** —— P0 audit 已全部清除並用測試釘住
- ❌ **PTT 自動爬蟲** —— 維護成本太高，未進排程
- ❌ **個股 narrative LLM 整合** —— Phase 7 是 daily brief，個股級別未做

—— *End of Phase 10 — local research desk is feature-complete.*
