"""Which address the rate limiter counts against, in front of Cloudflare and behind it.

Getting this wrong fails in one of two directions: trust the header nowhere and the
whole club shares one bucket behind Cloudflare's edge; trust it everywhere and anyone
calling the origin directly invents a new address per request and is never limited.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.api import limiter as rate_limiting
from app.config import Settings

EDGE_ADDRESS = "172.71.0.9"  # what a Cloudflare edge looks like to us
REAL_CALLER = "203.0.113.7"


def make_request(headers: dict[str, str] | None = None) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/me/summary",
        "headers": [
            (name.lower().encode(), value.encode())
            for name, value in (headers or {}).items()
        ],
        "client": (EDGE_ADDRESS, 51234),
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def restore_limiter_settings() -> Iterator[None]:
    """`configure()` writes a module global; put it back so these tests can't change how
    any other test is limited."""
    original = rate_limiting._settings
    yield
    rate_limiting._settings = original


def settings_with(*, trust_proxy: bool) -> Settings:
    return Settings(database_url="unused", trust_proxy=trust_proxy)


def test_without_trust_proxy_the_header_is_ignored() -> None:
    """An untrusted deployment: the header is attacker-controlled, so only the socket
    address counts."""
    rate_limiting.configure(settings_with(trust_proxy=False))

    assert (
        rate_limiting.client_ip(make_request({"CF-Connecting-IP": REAL_CALLER}))
        == EDGE_ADDRESS
    )


def test_with_trust_proxy_the_real_caller_is_used() -> None:
    rate_limiting.configure(settings_with(trust_proxy=True))

    assert (
        rate_limiting.client_ip(make_request({"CF-Connecting-IP": REAL_CALLER}))
        == REAL_CALLER
    )


def test_trusting_the_proxy_still_falls_back_when_the_header_is_absent() -> None:
    """A request that reached the container some other way — a probe, a direct call —
    still gets limited rather than sailing past on a missing header."""
    rate_limiting.configure(settings_with(trust_proxy=True))

    assert rate_limiting.client_ip(make_request()) == EDGE_ADDRESS


def test_an_empty_header_is_not_treated_as_an_address() -> None:
    """Otherwise every caller sending a blank header shares one bucket."""
    rate_limiting.configure(settings_with(trust_proxy=True))

    assert rate_limiting.client_ip(make_request({"CF-Connecting-IP": ""})) == EDGE_ADDRESS


def test_an_identified_member_is_limited_by_id_not_by_address() -> None:
    """Identity beats address wherever we have it: several members behind one office
    connection must not throttle each other."""
    rate_limiting.configure(settings_with(trust_proxy=True))
    request = make_request({"CF-Connecting-IP": REAL_CALLER})
    member_id = uuid4()
    request.state.member_id = member_id

    assert rate_limiting.member_or_ip(request) == str(member_id)


def test_an_anonymous_caller_falls_back_to_the_address() -> None:
    """Before the token is verified there is no member id — the 401 flood is limited by
    address or not at all."""
    rate_limiting.configure(settings_with(trust_proxy=True))

    assert (
        rate_limiting.member_or_ip(make_request({"CF-Connecting-IP": REAL_CALLER}))
        == REAL_CALLER
    )
