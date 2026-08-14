"""The FastAPI application.

A factory rather than a module-level app, so tests can build an instance with their own
settings and dependency overrides.

Note what does NOT happen here: migrations. They run as their own CI step — several
instances starting at once would race on the schema.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import limiter as rate_limiting
from app.api.errors import register_error_handlers
from app.api.routers import admin, consent, health, me, rewards, runs, webhooks
from app.config import Settings, get_settings


def _too_many_requests(request: Request, exc: Exception) -> Response:
    return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Running Club API", version="0.1.0")

    # One shared limiter, so the global default and the per-route limit on
    # /runs/extract come from the same instance (slowapi enforces via app.state).
    rate_limiting.configure(settings)
    rate_limiting.limiter.enabled = settings.rate_limit_enabled
    app.state.limiter = rate_limiting.limiter
    # Our own handler rather than slowapi's, so a throttled caller gets the same
    # {"detail": ...} shape as every other error in this API.
    app.add_exception_handler(RateLimitExceeded, _too_many_requests)
    app.add_middleware(SlowAPIMiddleware)

    # Locked to the frontend origin — never "*", which with credentials would let any
    # site call this API with a member's session.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)

    app.include_router(me.router)
    app.include_router(consent.router)
    app.include_router(health.router)
    app.include_router(runs.router)
    app.include_router(rewards.router)
    app.include_router(admin.router)
    app.include_router(webhooks.router)

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
