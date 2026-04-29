# 🇹🇼 Taiwan Stock AI Platform

> 台灣最專業的 AI 台股選股平台 — 籌碼 × 基本面 × 技術面 × AI 評分

[![Next.js](https://img.shields.io/badge/Next.js-15-black)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com)
[![Postgres](https://img.shields.io/badge/PostgreSQL-16-336791)](https://www.postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D)](https://redis.io)

---

## ✨ 專案介紹

整合台股三大分析維度（籌碼、基本面、技術面），用統一 AI 評分模型每日產出 **TOP10 強勢股**，並提供會員訂閱制的專業交易員介面。

### 核心模組
- **籌碼分析** — 三大法人、主力分點、籌碼集中度
- **基本面分析** — EPS / ROE / 毛利率 / 營收 / PEG
- **技術分析** — MA / MACD / RSI / KD / 布林 / 爆量
- **AI 評分** — `Chip 40% + Fundamental 35% + Technical 25%`
- **回測系統** — 嚴守摩擦、風控、熔斷鐵律

---

## 🏗 架構圖

```
┌─────────────────────────────────────────────────────────────┐
│                         Users                               │
└────────────┬────────────────────────────────┬───────────────┘
             │                                │
      ┌──────▼──────┐                  ┌──────▼──────┐
      │  Next.js    │  ←─── REST ───→  │   FastAPI   │
      │  (Vercel)   │                  │  (Railway)  │
      └─────────────┘                  └──────┬──────┘
                                              │
                         ┌────────────────────┼────────────────────┐
                         │                    │                    │
                  ┌──────▼─────┐      ┌───────▼──────┐      ┌──────▼──────┐
                  │ PostgreSQL │      │    Redis     │      │  Scheduler  │
                  │   (Neon)   │      │  (Upstash)   │      │ (APScheduler)│
                  └────────────┘      └──────────────┘      └──────┬──────┘
                                                                   │
                                                     ┌─────────────┼─────────────┐
                                                     │             │             │
                                               ┌─────▼────┐  ┌─────▼────┐  ┌─────▼────┐
                                               │   TWSE   │  │   TPEX   │  │   MOPS   │
                                               └──────────┘  └──────────┘  └──────────┘
```

---

## 📁 目錄結構

```
taiwan-stock-ai-platform/
├── frontend/               # Next.js App
├── backend/                # FastAPI App
├── database/               # SQL migrations / seed
├── infra/                  # Docker / deploy scripts
├── docs/                   # 規格 / API / ADR
├── scripts/                # 一次性腳本
├── data/                   # raw / processed / cache
├── logs/
├── tests/
├── notebooks/              # 研究用 Jupyter
├── strategy/               # 交易策略程式碼
├── chip_analysis/
├── fundamental_analysis/
├── technical_analysis/
├── ai_engine/              # 統一評分模型
└── .github/workflows/      # CI/CD
```

---

## 🚀 啟動方式

### 1. Clone & 安裝

```bash
git clone <repo-url>
cd taiwan-stock-ai-platform
cp .env.example .env
```

### 2. 啟動 Backend

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

→ 打開 http://localhost:8000/docs

### 3. 啟動 Frontend

```bash
cd frontend
npm install
npm run dev
```

→ 打開 http://localhost:3000

### 4. Docker (可選)

```bash
docker compose -f infra/docker-compose.yml up -d
```

---

## 🛠 開發流程

1. 在 `CLAUDE.md` 補上需求 / 調整身份設定
2. 下命令給 Claude，Claude 自動拆解 → 建檔 → 寫 code → 測試 → 回報
3. `pytest` + `npm run test` 全綠後才 push
4. GitHub Actions 自動跑 lint / test / build
5. main 分支合併後 Vercel 與 Railway 自動部署

---

## 🚢 部署流程

| 元件 | 平台 | 方式 |
|---|---|---|
| Frontend | Vercel | 連 GitHub，auto-deploy main |
| Backend  | Railway / Render | Dockerfile 部署 |
| Postgres | Neon / Railway | Managed |
| Redis    | Upstash | Managed |

環境變數請參考 `.env.example`。

---

## 📜 授權

Private. All rights reserved.
