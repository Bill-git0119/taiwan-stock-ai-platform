"""API router — local research workstation.

Phase 1 removed: auth, billing, admin, referral, blog (public-marketing),
notify (was tied to user prefs — kept for now, can be re-added once local
LINE config exists).
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    backtest, brief, correlation, datahub, decisions, health, intelligence,
    intraday, leaderboard, long_term, market, narrative, performance,
    persistence, portfolio, quality, research_report, risk, scanner, stocks,
    strategy_lab, strategy_ranking, stress, trade_plan, universe,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(datahub.router, prefix="/datahub", tags=["datahub"])
api_router.include_router(decisions.router, prefix="/decisions", tags=["decisions"])
api_router.include_router(long_term.router, prefix="/long-term", tags=["long-term"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(backtest.router, prefix="/backtest", tags=["backtest"])
api_router.include_router(leaderboard.router, prefix="/leaderboard", tags=["leaderboard"])
api_router.include_router(trade_plan.router, prefix="/trade-plan", tags=["trade-plan"])
api_router.include_router(scanner.router, prefix="/scanner", tags=["scanner"])
api_router.include_router(intraday.router, prefix="/intraday", tags=["intraday"])
api_router.include_router(intelligence.router, prefix="/intelligence", tags=["intelligence"])
api_router.include_router(brief.router, prefix="/brief", tags=["brief"])
api_router.include_router(strategy_lab.router, prefix="/lab", tags=["strategy-lab"])
api_router.include_router(performance.router, prefix="/performance", tags=["performance"])
api_router.include_router(narrative.router, prefix="/narrative", tags=["narrative"])
api_router.include_router(universe.router, prefix="/universe", tags=["universe"])
api_router.include_router(strategy_ranking.router, prefix="/strategy-rank", tags=["strategy-rank"])
api_router.include_router(research_report.router, prefix="/research", tags=["research"])
api_router.include_router(stress.router, prefix="/stress", tags=["stress"])
api_router.include_router(correlation.router, prefix="/correlation", tags=["correlation"])
api_router.include_router(risk.router, prefix="/risk", tags=["risk"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
api_router.include_router(persistence.router, prefix="/persistence", tags=["persistence"])
api_router.include_router(quality.router, prefix="/quality", tags=["quality"])

# Convenience shortcut: GET /api/v1/top10
api_router.add_api_route("/top10", stocks.get_top10, methods=["GET"], tags=["stocks"])
