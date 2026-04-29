# Backend — Taiwan Stock AI Platform

FastAPI backend. Runs the data ingestion, scoring, and serves the REST API.

## Dev

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
cp ../.env.example .env

uvicorn app.main:app --reload --port 8000
```

→ http://localhost:8000/docs

## Test

```bash
pytest -q
```

## Layout

```
app/
  main.py              # FastAPI factory
  core/config.py       # pydantic-settings
  api/v1/
    router.py
    endpoints/
      health.py
      stocks.py
  db/                  # SQLAlchemy engine & session
  models/              # ORM models
  schemas/             # Pydantic I/O schemas
  services/            # business logic
  ingestion/           # TWSE / TPEX / MOPS crawlers
  scheduler/           # APScheduler jobs
  utils/
tests/
```
