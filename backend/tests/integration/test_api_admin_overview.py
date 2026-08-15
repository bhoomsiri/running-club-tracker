"""GET /admin/overview — everyone's standing, and nothing that needs an audit row."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from tests.integration.conftest import BOSS_CLERK_ID

pytestmark = pytest.mark.integration

CAMPAIGN = UUID("33333333-3333-3333-3333-333333333333")
NOW = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)

ALICE = uuid4()
SOMCHAI = uuid4()
BOSS = uuid4()


def auth(clerk_user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {clerk_user_id}"}


@pytest.fixture
def club(session_factory: sessionmaker[Session]) -> None:
    """Alice with two runs (one flagged, one rejected) and some points; Somchai with
    nothing; the boss."""
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="daily-10km", name="วันละ 10 กม.",
                type="daily_threshold_reward", starts_on=date(2026, 8, 15),
                ends_on=date(2026, 9, 30),
                config={
                    "qualifying_km": 10, "points_per_qualifying_day": 1,
                    "submit_within_days": 1,
                },
            )
        )
        session.add(
            models.Member(
                id=ALICE, clerk_user_id="user_alice", display_name="Alice",
                full_name_th="สมหญิง วิ่งดี",
            )
        )
        session.add(
            models.Member(id=SOMCHAI, clerk_user_id="user_somchai", display_name="Somchai")
        )
        session.add(
            models.Member(
                id=BOSS, clerk_user_id=BOSS_CLERK_ID, display_name="Boss", role="superuser"
            )
        )
        session.flush()

        for suffix, status, distance in (
            ("a", "flagged", Decimal("12")),
            ("b", "rejected", Decimal("99")),
            ("c", "ok", Decimal("11")),
        ):
            session.add(
                models.RunEntry(
                    id=uuid4(), member_id=ALICE, distance_km=distance,
                    duration_seconds=1800, run_date=date(2026, 8, 18),
                    evidence_key=f"k{suffix}", evidence_sha256=suffix * 64,
                    source="app_screenshot", review_status=status, created_at=NOW,
                )
            )
        session.flush()
        session.add(
            models.PointsLedger(
                id=uuid4(), member_id=ALICE, campaign_id=CAMPAIGN,
                delta=Decimal("3"), reason="adjustment",
            )
        )
        session.commit()


def members_of(client: TestClient) -> list[Any]:
    response = client.get("/admin/overview", headers=auth(BOSS_CLERK_ID))
    assert response.status_code == 200
    rows: list[Any] = response.json()["members"]
    return rows


def row_for(client: TestClient, name: str) -> Any:
    return next(row for row in members_of(client) if row["name"] == name)


class TestAccess:
    def test_an_ordinary_member_is_refused(self, client: TestClient, club: None) -> None:
        assert client.get("/admin/overview", headers=auth("user_alice")).status_code == 403

    def test_an_admin_is_refused_too(
        self, client: TestClient, club: None, session_factory: sessionmaker[Session]
    ) -> None:
        """An admin may read health data with an audit trail. A list of everyone's
        standing is a different thing, and the club has one person running it."""
        with session_factory() as session:
            session.add(
                models.Member(
                    id=uuid4(), clerk_user_id="user_admin", display_name="Admin",
                    role="admin",
                )
            )
            session.commit()

        assert client.get("/admin/overview", headers=auth("user_admin")).status_code == 403

    def test_it_needs_a_token(self, client: TestClient, club: None) -> None:
        assert client.get("/admin/overview").status_code == 401


class TestContent:
    def test_every_member_appears(self, client: TestClient, club: None) -> None:
        names = {row["name"] for row in members_of(client)}

        assert names >= {"สมหญิง วิ่งดี", "Somchai", "Boss"}

    def test_the_thai_name_is_used_when_there_is_one(
        self, client: TestClient, club: None
    ) -> None:
        """Alice's Clerk display name is "Alice"; the club calls her by her Thai name."""
        names = {row["name"] for row in members_of(client)}

        assert "สมหญิง วิ่งดี" in names
        assert "Alice" not in names

    def test_a_member_with_no_runs_still_appears_at_zero(
        self, client: TestClient, club: None
    ) -> None:
        """An empty row is the point of an overview — it shows who has not started."""
        somchai = row_for(client, "Somchai")

        assert somchai["run_count"] == 0
        assert Decimal(str(somchai["total_distance_km"])) == 0

    def test_rejected_runs_do_not_count_toward_distance(
        self, client: TestClient, club: None
    ) -> None:
        """Same rule as the member's own screen, so the two cannot disagree: the 99 km
        rejected run is not in the total."""
        alice = row_for(client, "สมหญิง วิ่งดี")

        assert Decimal(str(alice["total_distance_km"])) == Decimal("23.000")

    def test_the_run_count_is_everything_submitted(
        self, client: TestClient, club: None
    ) -> None:
        """Including the rejected one: this is the admin's view of what was sent in, not
        of what counted."""
        assert row_for(client, "สมหญิง วิ่งดี")["run_count"] == 3

    def test_runs_awaiting_a_decision_are_counted(
        self, client: TestClient, club: None
    ) -> None:
        assert row_for(client, "สมหญิง วิ่งดี")["pending_review_count"] == 1
        assert row_for(client, "Somchai")["pending_review_count"] == 0

    def test_points_come_from_the_ledger(self, client: TestClient, club: None) -> None:
        campaigns = row_for(client, "สมหญิง วิ่งดี")["campaigns"]
        daily = next(c for c in campaigns if c["code"] == "daily-10km")

        assert Decimal(str(daily["points_balance"])) == Decimal("3")

    def test_a_member_with_no_ledger_rows_reads_as_zero_not_null(
        self, client: TestClient, club: None
    ) -> None:
        """The GROUP BY leaves them out entirely; a blank cell would look like a bug."""
        campaigns = row_for(client, "Somchai")["campaigns"]

        assert Decimal(str(campaigns[0]["points_balance"])) == 0


class TestWhatItMustNotReturn:
    """Health, screening and the sensitive profile fields are read through an audited
    path, one named member at a time. A hundred-row table cannot do that and mean
    anything, so none of it may appear here — this is the test that fails if it starts
    to."""

    FORBIDDEN = (
        "health",
        "screening",
        "answers",
        "weight_kg",
        "height_cm",
        "bmi",
        "sex",
        "phone",
        "birth_year",
        "emergency_contact_name",
        "emergency_contact_phone",
    )

    def test_no_sensitive_field_appears_anywhere_in_the_payload(
        self, client: TestClient, club: None
    ) -> None:
        body = client.get("/admin/overview", headers=auth(BOSS_CLERK_ID)).text

        for field in self.FORBIDDEN:
            assert f'"{field}"' not in body, f"{field} must not be in the overview"

    def test_viewing_the_overview_writes_no_audit_row(
        self, client: TestClient, club: None, session_factory: sessionmaker[Session]
    ) -> None:
        """Nothing here is an audited access, so nothing here should be audited — an
        audit log full of glances is one nobody reads."""
        client.get("/admin/overview", headers=auth(BOSS_CLERK_ID))

        with session_factory() as session:
            assert session.query(models.AuditLog).count() == 0
