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

`CF_ORIGIN_SECRET` may hold SEVERAL secrets separated by commas, and a request matching
any of them is let through. That exists for one job: rotating the value without a window
where requests are refused. There is no instant at which Cloudflare and Cloud Run can
both change, so a single-valued setting means either the new secret arrives before the
service accepts it, or the service stops accepting the old one before Cloudflare stops
sending it — 403 for everyone either way. With a list, rotation is:

    1. set CF_ORIGIN_SECRET to "old,new"   (both work)
    2. change the Cloudflare Transform Rule to send "new"
    3. set CF_ORIGIN_SECRET to "new"       (old stops working)

The comma is the separator, so a secret must not contain one. Nothing that should be
used here does — a random hex or base64 string has no commas in its alphabet — but a
passphrase somebody types by hand could, and it would be silently cut in half.
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
        # Split here rather than in main.py so the setting stays one string everywhere
        # else — config, Secret Manager, the env var — and only this file knows the
        # comma means anything. A single value with no comma yields a one-item list and
        # behaves exactly as it did before.
        self._secrets = _accepted(secret)
        if not self._secrets:
            # A value like "," is truthy, so main.py would install this guard with
            # nothing it can ever accept and every request would 403. Loud at startup
            # beats discovering it from the outage.
            raise ValueError("CF_ORIGIN_SECRET is set but holds no usable value")

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        presented = request.headers.get(ORIGIN_SECRET_HEADER, "").encode()

        # Every secret is compared, even after one has matched. A loop that stopped early
        # would return sooner for a value matching the first secret than one matching the
        # second, which tells a caller which of them they hit and roughly how many there
        # are. `|=` rather than `any(...)`, because a generator inside `any` short-circuits
        # for exactly the same reason.
        #
        # compare_digest rather than ==: a plain comparison returns faster the earlier it
        # finds a difference, which hands the secret over one byte at a time. Compared as
        # bytes, because comparing str raises TypeError on a non-ASCII header — a 500
        # anybody could trigger from outside, where the answer should be 403.
        matched = False
        for secret in self._secrets:
            matched |= hmac.compare_digest(presented, secret)

        if not matched:
            # Deliberately blank: a caller who guessed wrong learns nothing about what
            # was expected, and the value they sent is never logged.
            return JSONResponse(status_code=403, content={"detail": "forbidden"})

        return await call_next(request)


def _accepted(secret: str) -> tuple[bytes, ...]:
    """The configured values, comma-separated, trimmed, blanks dropped.

    Trimmed because these are pasted into a console field and a stray space either side
    is invisible; dropped because `"old,,new"` and a trailing comma are what a
    half-finished edit looks like, and an empty accepted secret would let a request with
    no header through the guard entirely.
    """
    return tuple(part.strip().encode() for part in secret.split(",") if part.strip())
