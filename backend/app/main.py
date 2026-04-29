from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.services import scheduler as scheduler_svc

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Taiwan Stock AI Platform starting up (env={})", settings.app_env)
    if settings.scheduler_enabled and settings.app_env != "test":
        try:
            scheduler_svc.start()
        except Exception as e:
            logger.warning("scheduler failed to start: {}", e)
    yield
    scheduler_svc.stop()
    logger.info("Taiwan Stock AI Platform shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Taiwan Stock AI Platform API",
        version="0.2.0",
        description="Chip × Fundamental × Technical × AI scoring for Taiwan equities.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_origin_regex=r"https://.*\.vercel\.app",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/", tags=["root"])
    async def root():
        return {
            "service": "taiwan-stock-ai-platform",
            "version": "0.2.0",
            "docs": "/docs",
            "health": "/api/v1/health",
        }

    return app


app = create_app()
