"""`/webhooks/clerk` is public, so the signature is the only thing standing between an
attacker and a forged "new member" (or a role change). Tested with real svix signatures."""

from __future__ import annotations

import json
from base64 import b64encode
from datetime import UTC, datetime
from typing import Any

import pytest
from svix.webhooks import Webhook

from app.adapters.auth.clerk_webhook import ClerkWebhookVerifier, to_user_event
from app.domain.errors import InvalidToken

SECRET = "whsec_" + b64encode(b"0123456789abcdef0123456789abcdef").decode()


def payload(event_type: str = "user.created", **data: Any) -> bytes:
    body = {
        "type": event_type,
        "data": {
            "id": "user_123",
            "first_name": "Som",
            "last_name": "Chai",
            "email_addresses": [
                {"id": "idn_1", "email_address": "som@example.com"},
            ],
            "primary_email_address_id": "idn_1",
            **data,
        },
    }
    return json.dumps(body).encode()


def signed_headers(body: bytes, secret: str = SECRET) -> dict[str, str]:
    message_id = "msg_test"
    timestamp = datetime.now(UTC)
    signature = Webhook(secret).sign(message_id, timestamp, body.decode())
    return {
        "svix-id": message_id,
        "svix-timestamp": str(int(timestamp.timestamp())),
        "svix-signature": signature,
    }


def test_a_correctly_signed_payload_is_accepted() -> None:
    body = payload()

    verified = ClerkWebhookVerifier(SECRET).verify(body, signed_headers(body))

    assert verified["type"] == "user.created"


def test_an_unsigned_payload_is_rejected() -> None:
    body = payload()

    with pytest.raises(InvalidToken):
        ClerkWebhookVerifier(SECRET).verify(body, {})


def test_a_payload_signed_with_the_wrong_secret_is_rejected() -> None:
    body = payload()
    other = "whsec_" + b64encode(b"ffffffffffffffffffffffffffffffff").decode()

    with pytest.raises(InvalidToken):
        ClerkWebhookVerifier(SECRET).verify(body, signed_headers(body, other))


def test_a_tampered_body_is_rejected() -> None:
    """Signed one payload, delivered another — e.g. swapping in a different user id."""
    headers = signed_headers(payload())
    tampered = payload(id="user_someone_else")

    with pytest.raises(InvalidToken):
        ClerkWebhookVerifier(SECRET).verify(tampered, headers)


class TestEventMapping:
    def test_user_created_maps_to_an_event(self) -> None:
        event = to_user_event(json.loads(payload()))

        assert event is not None
        assert event.clerk_user_id == "user_123"
        assert event.display_name == "Som Chai"
        assert event.created is True

    def test_username_is_used_when_there_is_no_real_name(self) -> None:
        event = to_user_event(json.loads(payload(first_name=None, last_name=None,
                                                 username="runner01")))

        assert event is not None
        assert event.display_name == "runner01"

    def test_unhandled_event_types_are_ignored(self) -> None:
        # Deletion is a deliberate erasure flow, never a webhook side effect.
        assert to_user_event(json.loads(payload("user.deleted"))) is None
        assert to_user_event(json.loads(payload("session.created"))) is None

    def test_a_payload_without_a_user_id_is_ignored(self) -> None:
        assert to_user_event({"type": "user.created", "data": {}}) is None
