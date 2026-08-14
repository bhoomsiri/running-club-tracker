"""The one Limiter instance, shared by the app and by routes that need a tighter limit
than the global default.

Per member, not per IP: several members behind one office NAT must not throttle each
other, and a limit tied to a verified identity is much harder to evade than one tied to
an address.

The limit values are read per request rather than at import, so `create_app(settings)`
configures them — which is also what lets the tests run with limits off.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import Settings, get_settings

_settings: Settings | None = None


def configure(settings: Settings) -> None:
    global _settings
    _settings = settings


def _current() -> Settings:
    return _settings or get_settings()


def member_or_ip(request: Request) -> str:
    member_id = getattr(request.state, "member_id", None)
    return str(member_id) if member_id else get_remote_address(request)


def default_limit() -> str:
    return _current().rate_limit


def extract_limit() -> str:
    """Each extract call costs real money at Gemini, which makes it the natural target
    for abuse — so it gets its own, much tighter limit."""
    return _current().extract_rate_limit


limiter = Limiter(key_func=member_or_ip, default_limits=[default_limit])
