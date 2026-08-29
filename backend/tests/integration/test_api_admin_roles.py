"""What an admin may and may not do, over HTTP against a real database.

The club has one superuser and up to a few admins. The line between them is the whole
point of this file, so every capability is asserted from both sides: the admin who may,
and the admin who may not. A gap on the "may not" side is not a missing feature — it is
somebody reading data the club never agreed to show them.

The role is read from the member row on every request and never from the token, which is
what makes `test_a_demoted_admin_loses_access_on_the_next_request` meaningful rather than
theoretical.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from tests.integration.conftest import CONSENT_VERSION

pytestmark = pytest.mark.integration

CAMPAIGN = UUID("33333333-3333-3333-3333-333333333333")
GRANTED_AT = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)

ALICE, ADMIN, BOSS = "user_alice", "user_admin", "user_boss"

# Everything an admin must still be refused. Each one either changes what the club offers
# or changes who may look at the club — neither is a helper's to decide.
SUPERUSER_ONLY = [
    # The workbook is the third kind: not what the club offers or who may look, but
    # everyone's records at once. An admin is accountable for reading one named member's
    # data; taking all of it is a different act.
    ("GET", "/admin/export", None),
    ("GET", "/admin/campaigns", None),
    ("GET", "/admin/announcements", None),
    ("GET", "/admin/redemptions", None),
    (
        "POST",
        "/admin/campaigns",
        {
            "code": "next-year", "name": "ปีหน้า", "type": "cumulative_distance",
            "starts_on": "2027-01-01", "ends_on": "2027-03-31",
            "config": {"target_km": 50},
        },
    ),
    (
        "POST",
        "/admin/announcements",
        {"title": "ประกาศ", "body": "ข้อความ", "is_published": True},
    ),
    (
        "POST",
        "/admin/rewards",
        {"campaign_id": str(CAMPAIGN), "name": "x", "points_cost": "5", "stock": 1},
    ),
]


@pytest.fixture
def club(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    """Alice with one run, a helper, and the superuser."""
    ids = {"alice": uuid4(), "admin": uuid4(), "boss": uuid4(), "run": uuid4()}
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="hundred-km-2026", name="100 km",
                type="cumulative_distance", starts_on=date(2026, 8, 1),
                ends_on=date(2026, 12, 31), config={"target_km": 100},
            )
        )
        session.add(
            models.Member(
                id=ids["alice"], clerk_user_id=ALICE, display_name="Alice",
                full_name_th="อลิศ ใจดี", sex="female", birth_date=date(1990, 5, 20),
                phone="0812345678", emergency_contact_name="สมหญิง ใจดี",
                emergency_contact_phone="0898765432",
            )
        )
        session.add(
            models.Member(
                id=ids["admin"], clerk_user_id=ADMIN, display_name="Admin", role="admin"
            )
        )
        session.add(
            models.Member(
                id=ids["boss"], clerk_user_id=BOSS, display_name="Boss", role="superuser"
            )
        )
        session.flush()
        session.add(
            models.RunEntry(
                id=ids["run"], member_id=ids["alice"], distance_km=Decimal("11"),
                duration_seconds=1800, run_date=date(2026, 8, 20), evidence_key="k",
                evidence_sha256="b" * 64, source="app_screenshot",
            )
        )
        # Alice has consented to the current wording, so the health read below is lawful
        # and reaches the audit row. Without it the answer is 403 for a different reason
        # entirely, and the test would prove nothing about roles.
        session.add(
            models.Consent(
                id=uuid4(), member_id=ids["alice"], purpose="health_data",
                version=CONSENT_VERSION, granted_at=GRANTED_AT,
            )
        )
        session.commit()
    return ids


def auth(who: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {who}"}


def audit_rows(session_factory: sessionmaker[Session]) -> list[models.AuditLog]:
    with session_factory() as session:
        return list(session.execute(sa.select(models.AuditLog)).scalars())


def role_of(session_factory: sessionmaker[Session], member_id: UUID) -> str:
    with session_factory() as session:
        return session.get(models.Member, member_id).role  # type: ignore[union-attr]


class TestWhatAnAdminMayRead:
    def test_the_club_overview(self, client: TestClient, club: dict[str, UUID]) -> None:
        assert client.get("/admin/overview", headers=auth(ADMIN)).status_code == 200

    def test_the_member_list(self, client: TestClient, club: dict[str, UUID]) -> None:
        assert client.get("/admin/members", headers=auth(ADMIN)).status_code == 200

    def test_one_members_progress(self, client: TestClient, club: dict[str, UUID]) -> None:
        response = client.get(
            f"/admin/members/{club['alice']}/summary", headers=auth(ADMIN)
        )

        assert response.status_code == 200

    def test_reading_progress_writes_no_audit_row(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        """Distance and points are activity records. Auditing every glance at them would
        bury the rows that matter under noise nobody reads."""
        client.get(f"/admin/members/{club['alice']}/summary", headers=auth(ADMIN))

        assert audit_rows(session_factory) == []

    def test_contact_details_are_audited_under_the_admins_own_name(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        response = client.get(
            f"/admin/members/{club['alice']}/contact", headers=auth(ADMIN)
        )

        assert response.status_code == 200
        rows = audit_rows(session_factory)
        assert [row.action for row in rows] == ["view_contact"]
        # Three people can open this now, so "an admin looked" is not an answer.
        assert rows[0].actor_member_id == club["admin"]
        assert rows[0].subject_member_id == club["alice"]

    def test_screening_is_audited_under_the_admins_own_name(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        response = client.get(
            f"/admin/members/{club['alice']}/screening", headers=auth(ADMIN)
        )

        assert response.status_code == 200
        rows = audit_rows(session_factory)
        assert [row.action for row in rows] == ["view_screening"]
        assert rows[0].actor_member_id == club["admin"]

    def test_health_is_audited_under_the_admins_own_name(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        """Alice has consented but has no measurements yet, so there is nothing to
        return — the audit row is written anyway, because the looking is the event."""
        response = client.get(f"/admin/members/{club['alice']}/health", headers=auth(ADMIN))

        assert response.status_code == 200
        rows = audit_rows(session_factory)
        assert [row.action for row in rows] == ["view_health"]
        assert rows[0].actor_member_id == club["admin"]

    def test_an_ordinary_member_may_read_none_of_it(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        for path in (
            "/admin/overview",
            "/admin/members",
            f"/admin/members/{club['alice']}/summary",
            f"/admin/members/{club['alice']}/contact",
            f"/admin/members/{club['alice']}/screening",
            f"/admin/members/{club['alice']}/health",
        ):
            assert client.get(path, headers=auth(ALICE)).status_code == 403, path

        assert audit_rows(session_factory) == []


class TestWhatAnAdminMayDecide:
    def test_an_admin_can_review_a_run(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        response = client.post(
            f"/admin/runs/{club['run']}/review",
            headers=auth(ADMIN),
            json={"decision": "rejected"},
        )

        assert response.status_code == 200
        assert response.json()["review_status"] == "rejected"
        rows = audit_rows(session_factory)
        assert [row.action for row in rows] == ["review_run"]
        assert rows[0].actor_member_id == club["admin"]


class TestWhatStaysWithTheSuperuser:
    @pytest.mark.parametrize(("method", "path", "body"), SUPERUSER_ONLY)
    def test_an_admin_is_refused(
        self,
        client: TestClient,
        club: dict[str, UUID],
        method: str,
        path: str,
        body: dict[str, object] | None,
    ) -> None:
        response = client.request(method, path, headers=auth(ADMIN), json=body)

        assert response.status_code == 403

    def test_an_admin_cannot_list_rewards(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        # Its own case: this one needs a campaign_id query parameter.
        response = client.get(
            "/admin/rewards", headers=auth(ADMIN), params={"campaign_id": str(CAMPAIGN)}
        )

        assert response.status_code == 403

    def test_an_admin_cannot_upload_a_reward_photo(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        response = client.post(
            "/admin/rewards/image",
            headers=auth(ADMIN),
            files={"file": ("r.png", b"\x89PNG\r\n\x1a\n", "image/png")},
        )

        assert response.status_code == 403

    def test_an_admin_cannot_hand_out_the_role(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        """An admin who could appoint another admin could appoint a hundred, and nobody
        would have decided it."""
        response = client.patch(
            f"/admin/members/{club['alice']}/role", headers=auth(ADMIN), json={"role": "admin"}
        )

        assert response.status_code == 403
        assert role_of(session_factory, club["alice"]) == "member"

    def test_none_of_the_refused_calls_left_an_audit_row(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        client.patch(
            f"/admin/members/{club['alice']}/role", headers=auth(ADMIN), json={"role": "admin"}
        )
        client.get("/admin/redemptions", headers=auth(ADMIN))

        assert audit_rows(session_factory) == []


class TestHandingOutTheRole:
    def test_the_superuser_promotes_and_it_is_audited(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        response = client.patch(
            f"/admin/members/{club['alice']}/role", headers=auth(BOSS), json={"role": "admin"}
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"
        assert role_of(session_factory, club["alice"]) == "admin"
        rows = audit_rows(session_factory)
        assert [row.action for row in rows] == ["change_role"]
        assert rows[0].detail == {"from_role": "member", "to_role": "admin"}

    def test_a_promoted_member_can_use_the_capability_at_once(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        assert client.get("/admin/overview", headers=auth(ALICE)).status_code == 403

        client.patch(
            f"/admin/members/{club['alice']}/role", headers=auth(BOSS), json={"role": "admin"}
        )

        assert client.get("/admin/overview", headers=auth(ALICE)).status_code == 200

    def test_a_demoted_admin_loses_access_on_the_next_request(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        """The role is read from the member row on every request, so there is no cached
        claim to wait out — this is the reason roles never come from the token."""
        assert client.get("/admin/overview", headers=auth(ADMIN)).status_code == 200

        client.patch(
            f"/admin/members/{club['admin']}/role", headers=auth(BOSS), json={"role": "member"}
        )

        assert client.get("/admin/overview", headers=auth(ADMIN)).status_code == 403

    def test_the_superusers_own_role_cannot_be_changed(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        response = client.patch(
            f"/admin/members/{club['boss']}/role", headers=auth(BOSS), json={"role": "member"}
        )

        assert response.status_code == 403
        assert role_of(session_factory, club["boss"]) == "superuser"

    def test_nobody_can_be_made_a_superuser_through_it(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        """422 rather than 403: the DTO refuses the word before any use case runs. The
        database permits exactly one superuser row, and this endpoint is not how a second
        one would appear."""
        response = client.patch(
            f"/admin/members/{club['alice']}/role",
            headers=auth(BOSS),
            json={"role": "superuser"},
        )

        assert response.status_code == 422
        assert role_of(session_factory, club["alice"]) == "member"

    def test_setting_the_role_twice_is_idempotent(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        for _ in range(2):
            response = client.patch(
                f"/admin/members/{club['alice']}/role",
                headers=auth(BOSS),
                json={"role": "admin"},
            )
            assert response.status_code == 200

        assert role_of(session_factory, club["alice"]) == "admin"
        # Both calls are recorded: the log answers "who did what and when", and the second
        # press happened whether or not it changed anything.
        assert [row.action for row in audit_rows(session_factory)] == [
            "change_role",
            "change_role",
        ]

    def test_an_unknown_member_is_404(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        response = client.patch(
            f"/admin/members/{uuid4()}/role", headers=auth(BOSS), json={"role": "admin"}
        )

        assert response.status_code == 404

    def test_promoting_never_touches_the_superuser_row(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        """The partial unique index allows one superuser. Making two admins must leave it
        exactly as it was, or the next deploy's migration is the one that finds out."""
        client.patch(
            f"/admin/members/{club['alice']}/role", headers=auth(BOSS), json={"role": "admin"}
        )

        with session_factory() as session:
            superusers = list(
                session.execute(
                    sa.select(models.Member.id).where(models.Member.role == "superuser")
                ).scalars()
            )

        assert superusers == [club["boss"]]
