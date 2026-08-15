"""The origin lock that keeps the raw Cloud Run URL from being a way around Cloudflare.

None of these touch the database: the guard answers from middleware, before routing and
before any dependency is resolved. That is the point — a request at the bare origin must
cost as little as possible.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.origin_guard import ORIGIN_SECRET_HEADER
from app.config import Settings
from app.main import create_app

SECRET = "an-origin-secret-nobody-can-guess"


def build_client(secret: str) -> Iterator[TestClient]:
    settings = Settings(
        database_url="unused-nothing-here-reaches-the-database",
        frontend_url="https://club.example.com",
        cf_origin_secret=secret,
        rate_limit_enabled=False,
    )
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def guarded() -> Iterator[TestClient]:
    """Cloudflare in front: the secret is configured, so the guard is on."""
    yield from build_client(SECRET)


@pytest.fixture
def unguarded() -> Iterator[TestClient]:
    """No Cloudflare — local, CI, or a club running without it for now."""
    yield from build_client("")


def test_a_request_without_the_header_is_refused(guarded: TestClient) -> None:
    """This is someone who found the *.run.app URL and called it directly."""
    response = guarded.get("/me/summary")

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}


def test_the_wrong_secret_is_refused(guarded: TestClient) -> None:
    response = guarded.get("/me/summary", headers={ORIGIN_SECRET_HEADER: "not-it"})

    assert response.status_code == 403


def test_a_prefix_of_the_secret_is_refused(guarded: TestClient) -> None:
    """Guessing byte by byte must not get any closer than guessing nothing."""
    response = guarded.get("/me/summary", headers={ORIGIN_SECRET_HEADER: SECRET[:-1]})

    assert response.status_code == 403


def test_the_refusal_says_nothing_about_the_secret(guarded: TestClient) -> None:
    response = guarded.get("/me/summary")

    body = response.text
    assert SECRET not in body
    assert ORIGIN_SECRET_HEADER.lower() not in body.lower()


def test_the_right_secret_passes_through(guarded: TestClient) -> None:
    response = guarded.get("/healthz", headers={ORIGIN_SECRET_HEADER: SECRET})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_the_header_name_is_matched_case_insensitively(guarded: TestClient) -> None:
    """Whatever casing Cloudflare's transform rule ends up sending."""
    response = guarded.get("/healthz", headers={"cf-origin-secret": SECRET})

    assert response.status_code == 200


def test_healthz_answers_without_the_header(guarded: TestClient) -> None:
    """Cloud Run's probe reaches the container directly and can never carry it. If this
    regresses, every deploy fails its health check."""
    assert guarded.get("/healthz").status_code == 200


def test_the_webhook_endpoint_is_not_exempt(guarded: TestClient) -> None:
    """Clerk's webhooks arrive through the club's domain like everything else, so they
    carry the header too — and this is the one public POST in the API."""
    response = guarded.post("/webhooks/clerk", content=b"{}")

    assert response.status_code == 403


def test_with_no_secret_configured_the_guard_is_off(unguarded: TestClient) -> None:
    """Local development and CI must not need a Cloudflare header to call the API."""
    assert unguarded.get("/healthz").status_code == 200


def test_with_no_secret_configured_a_stray_header_changes_nothing(
    unguarded: TestClient,
) -> None:
    response = unguarded.get("/healthz", headers={ORIGIN_SECRET_HEADER: "anything"})

    assert response.status_code == 200
