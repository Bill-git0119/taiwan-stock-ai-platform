from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin, auth, backtest, billing, blog, brief, health, intelligence,
    intraday, leaderboard, market, narrative, notify, performance,
    referral, research_report, scanner, stocks, strategy_lab,
    strategy_ranking, trade_plan, universe,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(stocks.router, prefix="/stocks", tags=["stocks"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(notify.router, prefix="/notify", tags=["notify"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(backtest.router, prefix="/backtest", tags=["backtest"])
api_router.include_router(referral.router, prefix="/referral", tags=["referral"])
api_router.include_router(leaderboard.router, prefix="/leaderboard", tags=["leaderboard"])
api_router.include_router(blog.router, prefix="/blog", tags=["blog"])
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

# Convenience shortcut: GET /api/v1/top10
api_router.add_api_route("/top10", stocks.get_top10, methods=["GET"], tags=["stocks"])
