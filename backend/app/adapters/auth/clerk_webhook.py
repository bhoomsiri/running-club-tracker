"""Verify and parse Clerk webhooks.

`/webhooks/clerk` is a public endpoint: without signature verification anyone could POST
a fake "new member" event, or a role change. Every payload is checked with svix and
rejected on failure — this is security-pdpa safeguard #1.
"""

from __future__ import annotations

from typing import Any

from svix.webhooks import Webhook, WebhookVerificationError

from app.application.use_cases.sync_member_from_clerk import ClerkUserEvent
from app.domain.errors import InvalidToken

# Events we act on. Anything else is acknowledged and ignored — deletion is a separate,
# deliberate erasure flow, not a side effect of a webhook.
HANDLED_EVENTS = frozenset({"user.created", "user.updated"})


class ClerkWebhookVerifier:
    def __init__(self, secret: str) -> None:
        self._webhook = Webhook(secret)

    def verify(self, payload: bytes, headers: dict[str, str]) -> dict[str, Any]:
        try:
            verified: dict[str, Any] = self._webhook.verify(payload, headers)
        except WebhookVerificationError as e:
            raise InvalidToken("invalid webhook signature") from e
        return verified


def to_user_event(payload: dict[str, Any]) -> ClerkUserEvent | None:
    """Map a verified Clerk payload onto our own command, or None if it isn't an event
    we act on. Nothing from the payload is trusted beyond these fields."""
    event_type = payload.get("type")
    if event_type not in HANDLED_EVENTS:
        return None

    data = payload.get("data") or {}
    clerk_user_id = data.get("id")
    if not clerk_user_id:
        return None

    return ClerkUserEvent(
        clerk_user_id=str(clerk_user_id),
        display_name=_full_name(data),
        email=_primary_email(data),
        created=event_type == "user.created",
    )


def _full_name(data: dict[str, Any]) -> str | None:
    parts = [data.get("first_name"), data.get("last_name")]
    joined = " ".join(p.strip() for p in parts if isinstance(p, str) and p.strip())
    if joined:
        return joined
    username = data.get("username")
    return username.strip() if isinstance(username, str) and username.strip() else None


def _primary_email(data: dict[str, Any]) -> str | None:
    """Only ever used to derive a readable name. Never stored, never logged."""
    addresses = data.get("email_addresses") or []
    primary_id = data.get("primary_email_address_id")
    for address in addresses:
        if not isinstance(address, dict):
            continue
        if primary_id is None or address.get("id") == primary_id:
            email = address.get("email_address")
            if isinstance(email, str) and email:
                return email
    return None
