from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import Settings
from src.api.dependencies import AppServices
from src.api.routers import (
    analysis,
    auth,
    limit_up_analysis,
    portfolio,
    raw,
    sectors,
    settings as settings_router,
    stocks,
    strategies,
    tail_end,
    wiki,
)
from src.utils.logger import logging_context, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    services: AppServices = app.state.services
    await services.init()
    services.start_job_worker()
    services.start_wiki_ingest_queue()
    services.start_scheduler()
    yield
    services.stop_scheduler()
    services.stop_wiki_ingest_queue()
    services.stop_job_worker()


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    setup_logging(log_dir=settings.data_dir / "logs", console=False)

    app = FastAPI(
        title="Personal AI Trader API",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.services = AppServices(settings)
    app.state.auth_tokens = set()

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        public_paths = {"/api/auth/login", "/api/health"}
        if path.startswith("/api") and path not in public_paths:
            auth_header = request.headers.get("Authorization", "")
            scheme, _, token = auth_header.partition(" ")
            if scheme.lower() != "bearer" or token not in app.state.auth_tokens:
                return JSONResponse(
                    {"detail": "Not authenticated"},
                    status_code=401,
                    headers={"WWW-Authenticate": "Bearer"},
                )
            request.state.user = "jason"

        return await call_next(request)

    @app.middleware("http")
    async def log_context_middleware(request: Request, call_next):
        trace_id = request.headers.get("X-Trace-Id") or uuid.uuid4().hex[:12]
        request.state.trace_id = trace_id
        with logging_context(trace_id=trace_id):
            response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response

    app.include_router(auth.router, prefix="/api")
    app.include_router(portfolio.router, prefix="/api")
    app.include_router(stocks.router, prefix="/api")
    app.include_router(analysis.router, prefix="/api")
    app.include_router(limit_up_analysis.router, prefix="/api")
    app.include_router(raw.router, prefix="/api")
    app.include_router(wiki.router, prefix="/api")
    app.include_router(settings_router.router, prefix="/api")
    app.include_router(sectors.router, prefix="/api")
    app.include_router(strategies.router, prefix="/api")
    app.include_router(tail_end.router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
