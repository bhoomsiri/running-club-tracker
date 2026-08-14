"""Token verification is the foundation of golden rule #2, so the rejection paths are
tested against a real signature, not mocked away.

A keypair is generated here, tokens are signed with it, and the authenticator is handed
a resolver backed by the matching public key — so "signed by someone else" and "expired"
fail for the same reasons they would in production, with no network involved.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.adapters.auth.clerk_authenticator import ClerkAuthenticator
from app.domain.errors import InvalidToken

ISSUER = "https://clerk.example.com"
FRONTEND = "https://club.example.com"


def _key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


REAL_KEY = _key()
OTHER_KEY = _key()


class StubResolver:
    def __init__(self, key: rsa.RSAPrivateKey) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str) -> Any:
        class _Key:
            key = self._key.public_key()

        return _Key()


def make_token(
    key: rsa.RSAPrivateKey = REAL_KEY,
    *,
    subject: str = "user_123",
    issuer: str = ISSUER,
    expires_in: timedelta = timedelta(minutes=30),
    **extra: Any,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": subject,
        "iss": issuer,
        "iat": now,
        "exp": now + expires_in,
        "azp": FRONTEND,
    }
    claims.update(extra)
    return jwt.encode(claims, key, algorithm="RS256")


def _b64(raw: bytes) -> str:
    return urlsafe_b64encode(raw).rstrip(b"=").decode()


def _hs256_by_hand(secret: bytes, claims: dict[str, Any]) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64(json.dumps(claims).encode())
    signing_input = f"{header}.{payload}".encode()
    signature = _b64(hmac.new(secret, signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{signature}"


def authenticator(key: rsa.RSAPrivateKey = REAL_KEY) -> ClerkAuthenticator:
    return ClerkAuthenticator(
        jwks_url="https://clerk.example.com/.well-known/jwks.json",
        issuer=ISSUER,
        authorized_parties=[FRONTEND],
        jwk_client=StubResolver(key),
    )


def test_a_valid_token_yields_the_clerk_user_id() -> None:
    identity = authenticator().verify(make_token(subject="user_abc"))

    assert identity.clerk_user_id == "user_abc"


def test_a_token_signed_by_someone_else_is_rejected() -> None:
    """The whole point: anyone can write `sub`, only Clerk can sign it."""
    forged = make_token(OTHER_KEY, subject="user_victim")

    with pytest.raises(InvalidToken):
        authenticator().verify(forged)


def test_an_expired_token_is_rejected() -> None:
    with pytest.raises(InvalidToken):
        authenticator().verify(make_token(expires_in=timedelta(minutes=-5)))


def test_a_token_from_another_issuer_is_rejected() -> None:
    with pytest.raises(InvalidToken):
        authenticator().verify(make_token(issuer="https://evil.example.com"))


def test_a_token_minted_for_another_application_is_rejected() -> None:
    with pytest.raises(InvalidToken):
        authenticator().verify(make_token(azp="https://someone-elses-app.example.com"))


def test_a_token_without_a_subject_is_rejected() -> None:
    with pytest.raises(InvalidToken):
        authenticator().verify(make_token(sub=None))


def test_garbage_is_rejected() -> None:
    with pytest.raises(InvalidToken):
        authenticator().verify("not-a-token")


def test_an_unsigned_token_is_rejected() -> None:
    """alg=none is the classic bypass; PyJWT is pinned to RS256 here."""
    unsigned = jwt.encode({"sub": "user_x", "iss": ISSUER}, key="", algorithm="none")

    with pytest.raises(InvalidToken):
        authenticator().verify(unsigned)


def test_an_hs256_token_signed_with_the_public_key_is_rejected() -> None:
    """Algorithm confusion: the attacker knows the public key (it is public), so if the
    verifier honoured the token's own `alg` they could sign with it as an HMAC secret.
    RS256 is pinned, so this is refused."""
    public_pem = REAL_KEY.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    now = int(datetime.now(UTC).timestamp())
    # Assembled by hand: PyJWT refuses to *encode* this, but an attacker isn't using
    # PyJWT — they just need our verifier to accept it.
    forged = _hs256_by_hand(
        public_pem,
        {"sub": "user_victim", "iss": ISSUER, "iat": now, "exp": now + 300, "azp": FRONTEND},
    )

    with pytest.raises(InvalidToken):
        authenticator().verify(forged)


class TestFailClosed:
    """If we cannot establish who the caller is, the answer is 401 — never a pass."""

    def test_an_unknown_kid_is_rejected(self) -> None:
        class MissingKeyResolver:
            def get_signing_key_from_jwt(self, token: str) -> Any:
                raise jwt.exceptions.PyJWKClientError("no key for kid")

        verifier = ClerkAuthenticator(
            jwks_url="https://clerk.example.com/.well-known/jwks.json",
            issuer=ISSUER,
            authorized_parties=[FRONTEND],
            jwk_client=MissingKeyResolver(),
        )

        with pytest.raises(InvalidToken):
            verifier.verify(make_token())

    def test_an_unreachable_jwks_endpoint_is_rejected(self) -> None:
        """Taking Clerk's endpoint offline must not become an authentication bypass."""

        class UnreachableResolver:
            def get_signing_key_from_jwt(self, token: str) -> Any:
                raise ConnectionError("jwks endpoint unreachable")

        verifier = ClerkAuthenticator(
            jwks_url="https://clerk.example.com/.well-known/jwks.json",
            issuer=ISSUER,
            authorized_parties=[FRONTEND],
            jwk_client=UnreachableResolver(),
        )

        with pytest.raises(InvalidToken):
            verifier.verify(make_token())


def test_the_error_never_echoes_the_token() -> None:
    token = make_token(OTHER_KEY)

    with pytest.raises(InvalidToken) as excinfo:
        authenticator().verify(token)

    assert token not in str(excinfo.value)


class TestDisplayName:
    def test_taken_from_a_name_claim_when_the_template_provides_one(self) -> None:
        identity = authenticator().verify(make_token(name="สมชาย"))

        assert identity.display_name == "สมชาย"

    def test_assembled_from_first_and_last_name(self) -> None:
        identity = authenticator().verify(make_token(first_name="Som", last_name="Chai"))

        assert identity.display_name == "Som Chai"

    def test_absent_when_the_token_carries_none(self) -> None:
        # Clerk's default session token has no name; the member gets a placeholder that
        # the webhook fills in later.
        assert authenticator().verify(make_token()).display_name is None
