"""Production refuses to start with a hole in its configuration.

This exists because of a real near-miss: an unset CLERK_JWKS_URL is invisible until the
first authenticated request, and then it is a 500 for every member at once — on a
revision Cloud Run has already sent traffic to. Failing at boot turns that into a failed
deploy that leaves the previous revision serving.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, missing_production_settings
from app.main import create_app

# A production environment with nothing missing.
COMPLETE: dict[str, Any] = {
    "app_env": "production",
    "database_url": "postgresql+psycopg://club:club@db.example.com/club",
    "clerk_issuer": "https://clerk.example.com",
    "clerk_jwks_url": "https://clerk.example.com/.well-known/jwks.json",
    "clerk_webhook_secret": "whsec_not_a_real_secret",
    "superuser_clerk_user_id": "user_boss",
    "frontend_url": "https://club.example.com",
    "s3_bucket": "running-club-evidence",
    "s3_endpoint_url": "https://account.r2.cloudflarestorage.com",
    "s3_access_key": "r2-access-key",
    "s3_secret_key": "r2-secret-key",
    "gemini_api_key": "gemini-key",
    "cf_origin_secret": "origin-secret",
    "rate_limit_enabled": False,
}


def production_settings(**overrides: Any) -> Settings:
    return Settings(**{**COMPLETE, **overrides})


def test_a_complete_production_config_starts() -> None:
    with TestClient(create_app(production_settings())) as client:
        assert client.get("/healthz").status_code == 200


def test_a_missing_setting_stops_the_boot() -> None:
    settings = production_settings(clerk_jwks_url="")

    with pytest.raises(RuntimeError, match="CLERK_JWKS_URL"), TestClient(create_app(settings)):
        pass  # pragma: no cover - the context manager never opens


def test_every_missing_name_is_reported_at_once() -> None:
    """One boot, one list. Reporting them one at a time would mean a deploy attempt per
    missing variable."""
    settings = production_settings(clerk_issuer="", gemini_api_key="", s3_secret_key=None)

    with pytest.raises(RuntimeError) as raised, TestClient(create_app(settings)):
        pass  # pragma: no cover

    message = str(raised.value)
    assert "CLERK_ISSUER" in message
    assert "GEMINI_API_KEY" in message
    assert "S3_SECRET_KEY" in message


def test_whitespace_is_not_a_value() -> None:
    """A variable set to a stray space is unset as far as anything downstream cares."""
    assert missing_production_settings(production_settings(cf_origin_secret="   ")) == [
        "CF_ORIGIN_SECRET"
    ]


def test_the_message_names_variables_but_never_their_values() -> None:
    """It lands in Cloud Run's logs, where golden rule #8 still applies."""
    settings = production_settings(clerk_jwks_url="")

    with pytest.raises(RuntimeError) as raised, TestClient(create_app(settings)):
        pass  # pragma: no cover

    message = str(raised.value)
    assert COMPLETE["clerk_webhook_secret"] not in message
    assert COMPLETE["s3_secret_key"] not in message
    assert COMPLETE["cf_origin_secret"] not in message


def test_local_boots_with_everything_blank() -> None:
    """Nothing about this check may get in the way of `uvicorn app.main:app --reload`."""
    settings = Settings(database_url="postgresql+psycopg://club:club@localhost/club")

    assert settings.app_env == "local"
    assert missing_production_settings(settings) == []
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").status_code == 200


def test_a_non_production_env_is_never_checked() -> None:
    """Staging and CI set what they need and no more; only production is held to the
    full list."""
    settings = Settings(app_env="staging", database_url="postgresql+psycopg://x@y/z")

    assert missing_production_settings(settings) == []
