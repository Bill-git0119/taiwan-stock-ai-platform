"""Datahub — the local research workstation's data plane.

Layout:
  collectors/   one module per external source (yfinance, twse, tpex, mops, etc.)
  validators/   integrity checks (missing bars, monotonic dates, gaps, duplicates)
  transforms/   raw → canonical OHLCV / chip / fundamentals
  loaders/      canonical → SQLite (operational) / DuckDB (research)
  integrity/    cross-source consistency reports
  schedules/    APScheduler entry points (referenced from app/services/scheduler.py)

Every collector inherits from BaseCollector and gets:
  * retry/backoff with jitter
  * freshness timestamp updates (DataFreshness table)
  * structured logging
  * deterministic source tag ("yfinance.daily", "twse.chips", ...)
  * never_silent contract: caller must distinguish empty-real from failure
"""
