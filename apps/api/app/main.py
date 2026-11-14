from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.api.v1.admin import router as admin_v1_router
from app.api.v1.public import router as public_v1_router
from app.core.database import get_session_factory
from app.middleware.rate_limit import SlidingWindowRateLimitMiddleware
from app.services.platform_service import seed_platforms_catalog
from packages.common.config import get_settings
from packages.common.logging import configure_logging


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    factory = get_session_factory()
    async with factory() as session:
        await seed_platforms_catalog(session)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Jobre — Universal Job Board Indexer API",
        description="One index. Every opportunity. Public search & authenticated administration API across 78 ATS and Job-Board platforms.",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(SlidingWindowRateLimitMiddleware, max_requests_per_minute=300)

    app.include_router(public_v1_router, prefix=settings.jobre_api_v1_prefix)
    app.include_router(admin_v1_router, prefix=settings.jobre_api_v1_prefix)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
