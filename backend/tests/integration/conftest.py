"""Fixtures for tests that need a real PostgreSQL.

These run against a throwaway database (`<db>_test`) created from DATABASE_URL, so a
developer's local data is never touched. Skipped when no database is reachable; CI
always has one, so the concurrency proofs always run there.
"""

from __future__ import annotations

import os
from base64 import b64encode
from collections.abc import Iterator

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.models import Base
from app.api import deps
from app.api import limiter as rate_limiting
from app.application.ports.token_verifier import VerifiedIdentity
from app.config import Settings
from app.domain.errors import InvalidToken
from app.main import create_app

TEST_DB_SUFFIX = "_test"

WEBHOOK_SECRET = "whsec_" + b64encode(b"0123456789abcdef0123456789abcdef").decode()
CONSENT_VERSION = "v2"
BOSS_CLERK_ID = "user_boss"


class StubVerifier:
    """Maps a bearer token straight onto a clerk_user_id, so the API tests can act as
    any member. `bad-token` fails, which is what a forged or expired token looks like
    to everything downstream.

    Only the verifier is stubbed: signature checking has its own tests against real
    signatures in tests/adapters/, and reproducing Clerk's signing here would test
    PyJWT rather than this API.
    """

    def verify(self, token: str) -> VerifiedIdentity:
        if token == "bad-token":
            raise InvalidToken("token verification failed")
        return VerifiedIdentity(clerk_user_id=token, display_name=None)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url_value = os.environ.get("DATABASE_URL")
    if not url_value:
        pytest.skip("DATABASE_URL is not set — skipping integration tests")

    url = make_url(url_value)
    test_db = f"{url.database}{TEST_DB_SUFFIX}"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))
            conn.execute(sa.text(f'CREATE DATABASE "{test_db}"'))
    except sa.exc.OperationalError as e:  # pragma: no cover - environment dependent
        pytest.skip(f"cannot reach PostgreSQL: {e}")
    finally:
        admin.dispose()

    test_engine = create_engine(url.set(database=test_db))
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        database_url="unused-the-session-factory-is-overridden",
        frontend_url="https://club.example.com",
        # Shaped like the real thing so the production auth dependency can actually be
        # constructed (see test_api_wiring.py). No network is reached: a syntactically
        # invalid token is rejected before any JWKS fetch.
        clerk_issuer="https://clerk.example.com",
        clerk_jwks_url="https://clerk.example.com/.well-known/jwks.json",
        clerk_webhook_secret=WEBHOOK_SECRET,
        consent_version=CONSENT_VERSION,
        superuser_clerk_user_id=BOSS_CLERK_ID,
        rate_limit_enabled=False,  # limits have their own test; they'd throttle these
        # Pinned rather than left to default: a developer's .env would otherwise switch
        # the origin guard on and every request in this suite would come back 403.
        cf_origin_secret="",
        trust_proxy=False,
    )


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], settings: Settings
) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[deps.get_settings_dep] = lambda: settings
    app.dependency_overrides[deps.get_session_factory_dep] = lambda: session_factory
    app.dependency_overrides[deps.get_token_verifier] = StubVerifier
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> Iterator[None]:
    """The limiter is a module-level singleton with in-memory counters, so without this
    one test's requests would eat another's budget and fail it at random."""
    storage = getattr(rate_limiting.limiter, "_storage", None)
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()
    yield
    if storage is not None and hasattr(storage, "reset"):
        storage.reset()


@pytest.fixture(autouse=True)
def clean_tables(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as conn:
        tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        conn.execute(sa.text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
