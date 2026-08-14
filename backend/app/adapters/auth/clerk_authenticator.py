"""Verify a Clerk session token.

This is the foundation golden rule #2 stands on: `member_id` is only ever derived from a
token whose signature we checked against Clerk's published keys. Decoding claims without
verifying them would let anyone mint any `sub` and read anybody's data.

Checked here: RS256 signature against Clerk's JWKS, issuer, expiry and not-before (with
a small leeway for clock skew), and `azp` — the authorised party — against the frontend
origin, so a token minted for a different app cannot be replayed at this API.

Implementation note: this uses PyJWT against Clerk's JWKS endpoint rather than the
`clerk-backend-api` SDK. Same verification, but it is a plain library call, so the tests
below can generate a keypair and prove the rejection paths without touching the network.
The port (`TokenVerifier`) means swapping to the SDK later is a one-file change.
"""

from __future__ import annotations

from typing import Any, Protocol

import jwt
from jwt import PyJWKClient

from app.application.ports.token_verifier import VerifiedIdentity
from app.domain.errors import InvalidToken

LEEWAY_SECONDS = 30


class SigningKeyResolver(Protocol):
    """Just enough of PyJWKClient to be substitutable: the tests below hand in a
    resolver backed by a locally generated keypair, so signature rejection is proven
    without reaching out to Clerk."""

    def get_signing_key_from_jwt(self, token: str) -> Any: ...


class ClerkAuthenticator:
    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        authorized_parties: list[str],
        *,
        jwk_client: SigningKeyResolver | None = None,
    ) -> None:
        self._issuer = issuer
        self._authorized_parties = authorized_parties
        # Caches keys between requests; refetches when Clerk rotates them.
        self._jwks = jwk_client or PyJWKClient(jwks_url, cache_keys=True)

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                # Pinned. NEVER derive this from the token's own header: `alg: none`
                # skips verification entirely, and `alg: HS256` turns the public key
                # into an HMAC secret that anyone holding it can sign with.
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub"], "verify_aud": False},
            )
        except jwt.PyJWTError as e:
            # Never echo the token or the reason back to the caller.
            raise InvalidToken("token verification failed") from e
        except Exception as e:
            # Fail closed. A JWKS endpoint that is unreachable, or a `kid` that isn't in
            # the key set, means we could not establish who this is — which is a 401,
            # never a pass. An "allow on infrastructure error" path here would be an
            # authentication bypass triggerable by taking Clerk's endpoint offline.
            raise InvalidToken("token could not be verified") from e

        self._check_authorized_party(claims)

        subject = claims.get("sub")
        if not subject:
            raise InvalidToken("token has no subject")

        return VerifiedIdentity(
            clerk_user_id=str(subject),
            display_name=_name_from(claims),
        )

    def _check_authorized_party(self, claims: dict[str, Any]) -> None:
        """`azp` is the origin the token was minted for. Clerk omits it in some token
        templates, so it is only enforced when present — and always when we have a list
        of parties to compare against."""
        if not self._authorized_parties:
            return
        azp = claims.get("azp")
        if azp is None:
            return
        if azp not in self._authorized_parties:
            raise InvalidToken("token was issued for a different application")


def _name_from(claims: dict[str, Any]) -> str | None:
    """Clerk's default session token carries no name; a custom JWT template may add one.
    Absent is fine — the member gets a placeholder the webhook fills in later."""
    name = claims.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()

    parts = [claims.get("first_name"), claims.get("last_name")]
    joined = " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
    return joined or None
