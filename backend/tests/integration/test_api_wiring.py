"""The dependency graph as production builds it — no overrides on the auth path.

Every other API test stubs the token verifier, which means none of them ever construct
the real one. That gap hid a TypeError that would have made every authenticated request
in production a 500: the verifier was cached with @lru_cache keyed on the Settings
object, and pydantic models are unhashable.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api import deps
from app.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
def unstubbed_client(
    session_factory: sessionmaker[Session], settings: Settings
) -> Iterator[TestClient]:
    """Only the database is redirected. The real ClerkAuthenticator is constructed."""
    app = create_app(settings)
    app.dependency_overrides[deps.get_settings_dep] = lambda: settings
    app.dependency_overrides[deps.get_session_factory_dep] = lambda: session_factory
    with TestClient(app) as client:
        yield client


def test_the_real_token_verifier_can_be_built_and_rejects_a_bad_token(
    unstubbed_client: TestClient,
) -> None:
    """401, not 500. A 500 here means the dependency itself blew up before it ever got
    round to checking the token."""
    response = unstubbed_client.get(
        "/me/summary", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "token verification failed"}


def test_a_missing_token_is_still_401_on_the_real_path(
    unstubbed_client: TestClient,
) -> None:
    assert unstubbed_client.get("/me/summary").status_code == 401


def test_building_the_verifier_twice_reuses_the_same_instance(
    settings: Settings,
) -> None:
    """The cache is what keeps PyJWKClient's fetched signing keys alive between
    requests; losing it would mean hitting Clerk's JWKS endpoint on every call."""
    first = deps.get_token_verifier(settings)
    second = deps.get_token_verifier(settings)

    assert first is second


def test_different_settings_get_different_verifiers(settings: Settings) -> None:
    other = settings.model_copy(update={"clerk_issuer": "https://other.example.com"})

    assert deps.get_token_verifier(settings) is not deps.get_token_verifier(other)


def test_every_authenticated_route_survives_a_bad_token_without_a_500(
    unstubbed_client: TestClient,
) -> None:
    """A sweep, because the failure was in a shared dependency: one broken provider
    would have taken down every one of these at once."""
    headers = {"Authorization": "Bearer nonsense"}
    routes = [
        ("get", "/me/summary"),
        ("get", "/me/runs"),
        ("get", "/rewards"),
        ("post", "/consent"),
        ("delete", "/consent"),
        ("get", "/admin/members"),
    ]

    for method, path in routes:
        response = getattr(unstubbed_client, method)(path, headers=headers)
        assert response.status_code == 401, f"{method.upper()} {path} -> {response.status_code}"
