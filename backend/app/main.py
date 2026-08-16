"""The FastAPI application.

A factory rather than a module-level app, so tests can build an instance with their own
settings and dependency overrides.

Note what does NOT happen here: migrations. They run as their own CI step — several
instances starting at once would race on the schema.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import limiter as rate_limiting
from app.api.errors import register_error_handlers
from app.api.origin_guard import CloudflareOriginGuard
from app.api.routers import (
    admin,
    announcements,
    consent,
    health,
    me,
    rewards,
    runs,
    screening,
    webhooks,
)
from app.config import Settings, get_settings, missing_production_settings


def _too_many_requests(request: Request, exc: Exception) -> Response:
    return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})


def _lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Refuse to start production with a hole in its configuration.

    Nothing here reads the environment lazily: an empty CLERK_JWKS_URL is not a problem
    until the first authenticated request, at which point it is a 500 for every member at
    once, on a revision already serving traffic. Failing at boot instead means the
    container never becomes ready, Cloud Run keeps the previous revision, and the deploy
    fails cleanly with the missing names in the log.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        missing = missing_production_settings(settings)
        if missing:
            # The names only — never the values that are present.
            raise RuntimeError(
                "refusing to start: APP_ENV=production but these are unset or empty: "
                + ", ".join(missing)
            )
        yield

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Running Club API", version="0.1.0", lifespan=_lifespan(settings))

    # One shared limiter, so the global default and the per-route limit on
    # /runs/extract come from the same instance (slowapi enforces via app.state).
    rate_limiting.configure(settings)
    rate_limiting.limiter.enabled = settings.rate_limit_enabled
    app.state.limiter = rate_limiting.limiter
    # Our own handler rather than slowapi's, so a throttled caller gets the same
    # {"detail": ...} shape as every other error in this API.
    app.add_exception_handler(RateLimitExceeded, _too_many_requests)
    app.add_middleware(SlowAPIMiddleware)

    # Added after the limiter and before CORS, which puts it between the two: requests
    # that did not come through Cloudflare are dropped before they cost the limiter
    # anything, while genuine errors still come back with CORS headers on them.
    if settings.cf_origin_secret:
        app.add_middleware(CloudflareOriginGuard, secret=settings.cf_origin_secret)
    elif settings.app_env != "local":
        # Not fatal — the club may be running without Cloudflare in front for a while —
        # but the *.run.app URL is then an open door around the WAF, so say so loudly.
        logging.getLogger(__name__).warning(
            "CF_ORIGIN_SECRET is not set: the origin is reachable without Cloudflare"
        )

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

    # Public: no token, so it is registered like any other router but guards nothing.
    app.include_router(announcements.router)
    app.include_router(me.router)
    app.include_router(consent.router)
    app.include_router(health.router)
    app.include_router(screening.router)
    app.include_router(runs.router)
    app.include_router(rewards.router)
    app.include_router(admin.router)
    app.include_router(webhooks.router)

    # Two names for one answer, because Google's frontend reserves /healthz on
    # *.run.app: a request for it never reaches the container, it gets Google's own
    # HTML 404 back. Cloud Run's probes talk to the container directly and are
    # unaffected, so /healthz stays as it is — /livez is the one anything outside can
    # actually reach.
    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/livez", tags=["ops"])
    def livez() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
