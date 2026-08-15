"""Origin lock: in production, only Cloudflare may reach this service.

Cloud Run publishes every service on its own `*.run.app` URL, and that URL keeps working
after the real domain is moved behind Cloudflare. Anyone who finds it gets the API with
no WAF, no Cloudflare rate-limiting rules and no bot filtering in front of it.

So Cloudflare attaches a shared secret to each request it forwards, and a request that
arrives without it did not come through Cloudflare. Reject it before it reaches anything
else — including the limiter, so a flood at the raw origin costs nothing but a header
comparison.

The Cloudflare side of this is a Transform Rule adding the request header
`CF-Origin-Secret`, whose value is this service's `CF_ORIGIN_SECRET`.
"""

from __future__ import annotations

import hmac

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

ORIGIN_SECRET_HEADER = "CF-Origin-Secret"

# Health is the one thing that must answer regardless of where the request came from.
# /healthz because Cloud Run's own probes hit the container directly rather than through
# Cloudflare and so can never carry the header; /livez because an uptime monitor has to
# be able to check the origin without being handed the shared secret. Neither says
# anything but {"status": "ok"}.
EXEMPT_PATHS = frozenset({"/healthz", "/livez"})


class CloudflareOriginGuard(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, secret: str) -> None:
        super().__init__(app)
        self._secret = secret

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        presented = request.headers.get(ORIGIN_SECRET_HEADER, "")
        # compare_digest rather than ==: a plain comparison returns faster the earlier it
        # finds a difference, which hands the secret over one byte at a time.
        if not hmac.compare_digest(presented, self._secret):
            # Deliberately blank: a caller who guessed wrong learns nothing about what
            # was expected, and the value they sent is never logged.
            return JSONResponse(status_code=403, content={"detail": "forbidden"})

        return await call_next(request)
