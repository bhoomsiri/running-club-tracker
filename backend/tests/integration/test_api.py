"""End-to-end HTTP tests: the real app, the real database, the real dependency graph.

Only the token verifier is stubbed — signature checking has its own tests in
tests/adapters/, and reproducing Clerk's signing here would test PyJWT, not this API.
Everything after the verifier (JIT provisioning, role gates, consent gates, audit,
error mapping) is the genuine wiring.
"""

from __future__ import annotations

import json
from base64 import b64encode
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from svix.webhooks import Webhook

from app.adapters.persistence import models
from app.api import deps
from app.config import Settings
from app.main import create_app
from tests.integration.conftest import BOSS_CLERK_ID, WEBHOOK_SECRET, StubVerifier

pytestmark = pytest.mark.integration

CAMPAIGN = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture
def seeded(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    """Alice (member), Dao (member), Admin (admin) — plus a campaign to hang data off."""
    ids = {"alice": uuid4(), "dao": uuid4(), "admin": uuid4()}
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="100km", name="100 km", type="cumulative_distance",
                starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
                config={"target_km": 100},
            )
        )
        session.add(
            models.Member(id=ids["alice"], clerk_user_id="user_alice", display_name="Alice")
        )
        session.add(models.Member(id=ids["dao"], clerk_user_id="user_dao", display_name="Dao"))
        session.add(
            models.Member(
                id=ids["admin"], clerk_user_id="user_admin", display_name="Admin", role="admin"
            )
        )
        session.commit()
    return ids


def auth(clerk_user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {clerk_user_id}"}


def grant_consent(client: TestClient, clerk_user_id: str) -> None:
    assert client.post("/consent", headers=auth(clerk_user_id)).status_code == 201


def audit_rows(session_factory: sessionmaker[Session]) -> list[models.AuditLog]:
    with session_factory() as session:
        return list(session.execute(sa.select(models.AuditLog)).scalars())


# --------------------------------------------------------------------------- auth

class TestAuthentication:
    def test_no_token_is_401(self, client: TestClient, seeded: dict[str, UUID]) -> None:
        assert client.get("/me/summary").status_code == 401

    def test_a_token_that_fails_verification_is_401(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        assert client.get("/me/summary", headers=auth("bad-token")).status_code == 401

    def test_a_malformed_authorization_header_is_401(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        response = client.get("/me/summary", headers={"Authorization": "user_alice"})

        assert response.status_code == 401

    def test_a_valid_token_gets_that_members_own_summary(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        response = client.get("/me/summary", headers=auth("user_alice"))

        assert response.status_code == 200
        assert response.json()["member"]["id"] == str(seeded["alice"])

    def test_an_unknown_but_verified_member_is_provisioned_on_the_spot(
        self, client: TestClient, seeded: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        """The webhook hasn't arrived yet; the token is valid, so they are let in as an
        ordinary member."""
        response = client.get("/me/summary", headers=auth("user_brand_new"))

        assert response.status_code == 200
        assert response.json()["member"]["role"] == "member"

    def test_jit_provisioning_never_grants_the_superuser_role(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        """Even the configured bootstrap id gets no privileges from a bare login — the
        promotion only happens through the signed webhook."""
        response = client.get("/me/summary", headers=auth(BOSS_CLERK_ID))

        assert response.json()["member"]["role"] == "member"


class TestAuthorization:
    def test_an_ordinary_member_cannot_list_members(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        assert client.get("/admin/members", headers=auth("user_alice")).status_code == 403

    def test_an_ordinary_member_cannot_read_anyones_health(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        response = client.get(
            f"/admin/members/{seeded['dao']}/health", headers=auth("user_alice")
        )

        assert response.status_code == 403

    def test_an_admin_can_list_members(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        response = client.get("/admin/members", headers=auth("user_admin"))

        assert response.status_code == 200
        assert {m["display_name"] for m in response.json()} == {"Alice", "Dao", "Admin"}

    def test_the_member_list_carries_no_health_data_and_writes_no_audit_row(
        self, client: TestClient, seeded: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        response = client.get("/admin/members", headers=auth("user_admin"))

        body = json.dumps(response.json())
        assert "weight" not in body and "bmi" not in body
        assert audit_rows(session_factory) == []


class TestIdorProtection:
    """member_id comes from the token. These prove there is no way to say otherwise."""

    def test_an_id_in_the_body_does_not_redirect_a_health_write(
        self, client: TestClient, seeded: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        grant_consent(client, "user_alice")

        response = client.post(
            "/health",
            headers=auth("user_alice"),
            json={
                "member_id": str(seeded["dao"]),  # ignored: not part of the DTO
                "campaign_id": str(CAMPAIGN),
                "phase": "before",
                "measured_on": "2026-06-01",
                "weight_kg": "70.5",
            },
        )

        assert response.status_code == 201
        with session_factory() as session:
            owners = list(
                session.execute(sa.select(models.HealthRecord.member_id)).scalars()
            )
        assert owners == [seeded["alice"]]  # written to the caller, not the named id

    def test_one_members_data_never_appears_in_anothers_summary(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        grant_consent(client, "user_dao")
        client.post(
            "/health",
            headers=auth("user_dao"),
            json={
                "campaign_id": str(CAMPAIGN), "phase": "before",
                "measured_on": "2026-06-01", "weight_kg": "99.9",
            },
        )

        alice = client.get("/me/summary", headers=auth("user_alice")).json()

        assert alice["member"]["id"] == str(seeded["alice"])
        assert alice["health"] == []
        assert "99.9" not in json.dumps(alice)

    def test_the_summary_route_takes_no_member_id_at_all(self, client: TestClient) -> None:
        # There is no /me/summary/{id} to attack.
        assert client.get(f"/me/summary/{uuid4()}").status_code == 404


class TestConsentAndHealth:
    def test_writing_health_without_consent_is_403(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        response = client.post(
            "/health",
            headers=auth("user_alice"),
            json={
                "campaign_id": str(CAMPAIGN), "phase": "before",
                "measured_on": "2026-06-01", "weight_kg": "70.5",
            },
        )

        assert response.status_code == 403

    def test_granting_consent_then_writing_works(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        grant_consent(client, "user_alice")

        response = client.post(
            "/health",
            headers=auth("user_alice"),
            json={
                "campaign_id": str(CAMPAIGN), "phase": "before",
                "measured_on": "2026-06-01", "weight_kg": "70.5", "height_cm": "172.5",
            },
        )

        assert response.status_code == 201
        assert response.json()["weight_kg"] == "70.5"  # exact, not a float

    def test_withdrawing_consent_closes_the_gate_again(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        grant_consent(client, "user_alice")
        assert client.delete("/consent", headers=auth("user_alice")).status_code == 204

        response = client.post(
            "/health",
            headers=auth("user_alice"),
            json={
                "campaign_id": str(CAMPAIGN), "phase": "after",
                "measured_on": "2026-06-02", "weight_kg": "69.0",
            },
        )

        assert response.status_code == 403

    def test_withdrawing_twice_is_still_204(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        assert client.delete("/consent", headers=auth("user_alice")).status_code == 204
        assert client.delete("/consent", headers=auth("user_alice")).status_code == 204

    def test_an_implausible_measurement_is_422(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        grant_consent(client, "user_alice")

        response = client.post(
            "/health",
            headers=auth("user_alice"),
            json={
                "campaign_id": str(CAMPAIGN), "phase": "before",
                "measured_on": "2026-06-01", "height_cm": "300",
            },
        )

        assert response.status_code == 422

    def test_withdrawing_stops_the_summary_returning_health(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        """Consent is the club's basis for processing health data, and handing it back to
        the member is processing — so withdrawal closes this too.

        This reverses what the endpoint used to do. It previously kept answering with the
        measurements after a withdrawal, on the reading that withdrawal stops the CLUB
        processing the data and is not a lockout of the owner. Both readings are
        defensible; the club chose this one, and the deciding argument was that the gate
        lived only in the health screen's UI, so the next screen to read /me/summary would
        have shown the data with nobody noticing the gate had been left behind.

        Nothing is deleted: granting again brings it back, which the test below shows.
        """
        grant_consent(client, "user_alice")
        client.post(
            "/health",
            headers=auth("user_alice"),
            json={
                "campaign_id": str(CAMPAIGN), "phase": "before",
                "measured_on": "2026-06-01", "weight_kg": "70.5", "height_cm": "172.5",
            },
        )
        client.delete("/consent", headers=auth("user_alice"))

        summary = client.get("/me/summary", headers=auth("user_alice")).json()

        assert summary["health"] == []

    def test_granting_again_brings_the_records_back(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        """Withdrawal is not erasure. The rows are still there and the member can have
        them back by agreeing again — which is what makes closing the door acceptable."""
        grant_consent(client, "user_alice")
        client.post(
            "/health",
            headers=auth("user_alice"),
            json={
                "campaign_id": str(CAMPAIGN), "phase": "before",
                "measured_on": "2026-06-01", "weight_kg": "70.5", "height_cm": "172.5",
            },
        )
        client.delete("/consent", headers=auth("user_alice"))
        grant_consent(client, "user_alice")

        summary = client.get("/me/summary", headers=auth("user_alice")).json()

        assert summary["health"][0]["bmi_before"] == "23.7"


class TestAdminHealthAccess:
    def test_an_admin_read_returns_data_and_writes_exactly_one_audit_row(
        self, client: TestClient, seeded: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        grant_consent(client, "user_dao")
        client.post(
            "/health",
            headers=auth("user_dao"),
            json={
                "campaign_id": str(CAMPAIGN), "phase": "before",
                "measured_on": "2026-06-01", "weight_kg": "70.5", "height_cm": "172.5",
            },
        )

        response = client.get(
            f"/admin/members/{seeded['dao']}/health", headers=auth("user_admin")
        )

        assert response.status_code == 200
        assert response.json()["health"][0]["bmi_before"] == "23.7"
        rows = audit_rows(session_factory)
        assert len(rows) == 1
        assert rows[0].action == "view_health"
        assert rows[0].actor_member_id == seeded["admin"]
        assert rows[0].subject_member_id == seeded["dao"]
        assert rows[0].detail == {"campaign_count": 1}

    def test_a_withdrawn_subject_is_403_with_no_audit_row(
        self, client: TestClient, seeded: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        grant_consent(client, "user_dao")
        client.delete("/consent", headers=auth("user_dao"))

        response = client.get(
            f"/admin/members/{seeded['dao']}/health", headers=auth("user_admin")
        )

        assert response.status_code == 403
        assert audit_rows(session_factory) == []

    def test_an_unknown_member_is_404(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        response = client.get(f"/admin/members/{uuid4()}/health", headers=auth("user_admin"))

        assert response.status_code == 404


class TestWebhook:
    def signed(self, body: bytes, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
        message_id = "msg_1"
        timestamp = datetime.now(UTC)
        return {
            "svix-id": message_id,
            "svix-timestamp": str(int(timestamp.timestamp())),
            "svix-signature": Webhook(secret).sign(message_id, timestamp, body.decode()),
            "content-type": "application/json",
        }

    def payload(self, clerk_id: str = "user_webhook", **data: object) -> bytes:
        return json.dumps(
            {
                "type": "user.created",
                "data": {"id": clerk_id, "first_name": "Som", "last_name": "Chai", **data},
            }
        ).encode()

    def test_an_unsigned_webhook_is_rejected(self, client: TestClient) -> None:
        response = client.post("/webhooks/clerk", content=self.payload())

        assert response.status_code == 401

    def test_a_wrongly_signed_webhook_is_rejected(self, client: TestClient) -> None:
        body = self.payload()
        other_secret = "whsec_" + b64encode(b"ffffffffffffffffffffffffffffffff").decode()

        response = client.post(
            "/webhooks/clerk", content=body, headers=self.signed(body, other_secret)
        )

        assert response.status_code == 401

    def test_a_forged_member_is_not_created(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        body = self.payload("user_forged")

        client.post("/webhooks/clerk", content=body)

        with session_factory() as session:
            count = session.execute(
                sa.select(sa.func.count())
                .select_from(models.Member)
                .where(models.Member.clerk_user_id == "user_forged")
            ).scalar_one()
        assert count == 0

    def test_a_correctly_signed_webhook_creates_the_member(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        body = self.payload()

        response = client.post("/webhooks/clerk", content=body, headers=self.signed(body))

        assert response.status_code == 204
        with session_factory() as session:
            row = session.execute(
                sa.select(models.Member).where(models.Member.clerk_user_id == "user_webhook")
            ).scalar_one()
        assert row.display_name == "Som Chai"
        assert row.role == "member"

    def test_the_signed_webhook_bootstraps_the_superuser(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        body = self.payload(BOSS_CLERK_ID)

        client.post("/webhooks/clerk", content=body, headers=self.signed(body))

        with session_factory() as session:
            row = session.execute(
                sa.select(models.Member).where(models.Member.clerk_user_id == BOSS_CLERK_ID)
            ).scalar_one()
        assert row.role == "superuser"

    def test_the_superuser_can_then_read_health(
        self, client: TestClient, seeded: dict[str, UUID]
    ) -> None:
        body = self.payload(BOSS_CLERK_ID)
        client.post("/webhooks/clerk", content=body, headers=self.signed(body))
        grant_consent(client, "user_dao")

        response = client.get(
            f"/admin/members/{seeded['dao']}/health", headers=auth(BOSS_CLERK_ID)
        )

        assert response.status_code == 200


def test_the_rate_limiter_is_wired_and_can_be_tightened(
    engine: Engine, session_factory: sessionmaker[Session], settings: Settings
) -> None:
    """Proves the hook works end to end. The real per-route limits belong on the
    expensive endpoints (/runs/extract calls Gemini) once they exist."""
    throttled = settings.model_copy(update={"rate_limit_enabled": True, "rate_limit": "2/minute"})
    app = create_app(throttled)
    app.dependency_overrides[deps.get_settings_dep] = lambda: throttled
    app.dependency_overrides[deps.get_session_factory_dep] = lambda: session_factory
    app.dependency_overrides[deps.get_token_verifier] = StubVerifier

    with TestClient(app) as client:
        codes = [client.get("/healthz").status_code for _ in range(3)]

    assert codes == [200, 200, 429]


def test_healthz_needs_no_token(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}


def test_cors_is_locked_to_the_frontend_origin(client: TestClient) -> None:
    allowed = client.get(
        "/healthz", headers={"Origin": "https://club.example.com"}
    ).headers.get("access-control-allow-origin")
    other = client.get(
        "/healthz", headers={"Origin": "https://evil.example.com"}
    ).headers.get("access-control-allow-origin")

    assert allowed == "https://club.example.com"
    assert other is None


def test_decimals_are_exact_strings_not_floats(
    client: TestClient, seeded: dict[str, UUID]
) -> None:
    """Distances and points must survive the wire without float rounding (rule #6)."""
    grant_consent(client, "user_alice")
    body = client.post(
        "/health",
        headers=auth("user_alice"),
        json={
            "campaign_id": str(CAMPAIGN), "phase": "before",
            "measured_on": "2026-06-01", "weight_kg": "70.55",
        },
    ).json()

    assert body["weight_kg"] == "70.55"
    assert Decimal(body["weight_kg"]) == Decimal("70.55")
