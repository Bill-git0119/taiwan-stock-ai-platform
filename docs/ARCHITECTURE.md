# Architecture

## High-level flow

```
ingestion (TWSE/TPEX/MOPS) → raw storage (data/raw + Postgres)
      ↓
feature pipeline (chip / fundamental / technical)
      ↓
AI scoring (ai_engine) → daily_top10 table
      ↓
FastAPI (/api/v1/...)  ←→  Next.js Dashboard
```

## Service boundaries

| Service | Owns |
|---|---|
| `backend/app/ingestion` | 爬蟲、解析、raw insert |
| `backend/app/services/chip` | 籌碼指標計算 |
| `backend/app/services/fundamental` | 財報指標計算 |
| `backend/app/services/technical` | K 線指標計算 |
| `ai_engine/` | 評分模型、TOP10 產生器 |
| `backend/app/scheduler` | 日頻 pipeline，收盤後觸發 |
| `frontend/` | Dashboard、會員、計費 |

## Data model (draft)

- `stocks(symbol PK, name, market, industry)`
- `prices_daily(symbol, date, open, high, low, close, volume)`
- `chip_daily(symbol, date, foreign_net, inv_trust_net, dealer_net, concentration)`
- `fundamentals_quarterly(symbol, quarter, eps, roe, gross_margin, rev_yoy, pe, peg)`
- `scores_daily(symbol, date, chip, fundamental, technical, total)`
- `daily_top10(date, rank, symbol, total_score)`

## Deployment

- **Frontend:** Vercel, auto-deploy main
- **Backend:** Railway (Dockerfile)
- **Postgres:** Neon / Railway managed
- **Redis:** Upstash
- **Secrets:** platform env vars, `.env.example` lists keys
