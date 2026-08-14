from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VerifiedIdentity:
    """What a *cryptographically verified* token tells us about the caller.

    Nothing outside this type may be trusted from a request. In particular there is no
    role here: a role claim in a token is client-adjacent data, so roles are always read
    from the member record in the database instead.
    """

    clerk_user_id: str
    display_name: str | None = None


class TokenVerifier(Protocol):
    def verify(self, token: str) -> VerifiedIdentity:
        """Check the token's signature, issuer, audience and expiry.

        Raises InvalidToken for anything that doesn't verify. Decoding a token without
        verifying it would make golden rule #2 meaningless — anyone could mint a `sub`.
        """
        ...
