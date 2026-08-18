"""Superuser endpoints over HTTP: who may call them, and what they do."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models

pytestmark = pytest.mark.integration

CAMPAIGN = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture
def club(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    """Alice (member), an admin, the superuser, one reward, one pending redemption."""
    ids = {"alice": uuid4(), "admin": uuid4(), "boss": uuid4(), "shirt": uuid4(),
           "redemption": uuid4(), "run": uuid4()}
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="daily-10km-2026", name="daily 10",
                type="daily_threshold_reward", starts_on=date(2026, 8, 15),
                ends_on=date(2026, 9, 30),
                config={
                    "qualifying_km": 10, "points_per_qualifying_day": 1,
                    "submit_within_days": 1,
                },
            )
        )
        session.add(
            models.Member(id=ids["alice"], clerk_user_id="user_alice", display_name="Alice")
        )
        session.add(
            models.Member(
                id=ids["admin"], clerk_user_id="user_admin", display_name="Admin", role="admin"
            )
        )
        session.add(
            models.Member(
                id=ids["boss"], clerk_user_id="user_boss", display_name="Boss",
                role="superuser",
            )
        )
        session.add(
            models.Reward(
                id=ids["shirt"], campaign_id=CAMPAIGN, name="Shirt",
                points_cost=Decimal("1"), stock=2,
            )
        )
        session.flush()
        session.add(
            models.RunEntry(
                id=ids["run"], member_id=ids["alice"], distance_km=Decimal("11"),
                duration_seconds=1800, run_date=date(2026, 8, 20), evidence_key="k",
                evidence_sha256="a" * 64, source="app_screenshot",
            )
        )
        session.flush()
        session.add(
            models.PointsLedger(
                id=uuid4(), member_id=ids["alice"], campaign_id=CAMPAIGN,
                # 11 km on one day = one qualifying day = 1 point, exactly what the
                # daily-threshold policy computes for the run seeded above.
                delta=Decimal("1"), reason="run_earned", run_entry_id=ids["run"],
            )
        )
        session.add(
            models.Redemption(
                id=ids["redemption"], member_id=ids["alice"], reward_id=ids["shirt"],
                campaign_id=CAMPAIGN, points_spent=Decimal("1"), status="pending",
            )
        )
        session.flush()
        session.add(
            models.PointsLedger(
                id=uuid4(), member_id=ids["alice"], campaign_id=CAMPAIGN,
                delta=Decimal("-1"), reason="redeemed", redemption_id=ids["redemption"],
            )
        )
        session.commit()
    return ids


def auth(who: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {who}"}


def audit_actions(session_factory: sessionmaker[Session]) -> list[str]:
    with session_factory() as session:
        return list(session.execute(sa.select(models.AuditLog.action)).scalars())


def balance(session_factory: sessionmaker[Session], member_id: UUID) -> Decimal:
    with session_factory() as session:
        return Decimal(
            session.execute(
                sa.select(sa.func.coalesce(sa.func.sum(models.PointsLedger.delta), 0)).where(
                    models.PointsLedger.member_id == member_id
                )
            ).scalar_one()
        )


NEW_CAMPAIGN = {
    "code": "next-year", "name": "ปีหน้า", "type": "cumulative_distance",
    "starts_on": "2027-01-01", "ends_on": "2027-03-31", "config": {"target_km": 50},
}


class TestOnlyTheSuperuserMayMutate:
    @pytest.mark.parametrize("who", ["user_alice", "user_admin"])
    def test_creating_a_campaign_is_403(
        self, client: TestClient, club: dict[str, UUID], who: str
    ) -> None:
        assert client.post(
            "/admin/campaigns", headers=auth(who), json=NEW_CAMPAIGN
        ).status_code == 403

    @pytest.mark.parametrize("who", ["user_alice", "user_admin"])
    def test_creating_a_reward_is_403(
        self, client: TestClient, club: dict[str, UUID], who: str
    ) -> None:
        response = client.post(
            "/admin/rewards",
            headers=auth(who),
            json={"campaign_id": str(CAMPAIGN), "name": "x", "points_cost": "5", "stock": 1},
        )

        assert response.status_code == 403

    def test_reviewing_a_run_is_403_for_an_ordinary_member(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        """Admins are not in this list any more — deciding runs is the work the club has
        helpers for, and test_api_admin_roles.py proves they can."""
        response = client.post(
            f"/admin/runs/{club['run']}/review",
            headers=auth("user_alice"),
            json={"decision": "rejected"},
        )

        assert response.status_code == 403

    @pytest.mark.parametrize("who", ["user_alice", "user_admin"])
    def test_fulfilling_a_redemption_is_403(
        self, client: TestClient, club: dict[str, UUID], who: str
    ) -> None:
        response = client.post(
            f"/admin/redemptions/{club['redemption']}/fulfill", headers=auth(who)
        )

        assert response.status_code == 403

    def test_an_admin_may_still_look(self, client: TestClient, club: dict[str, UUID]) -> None:
        """Admin = look at the club and decide runs. What the club *offers* — campaigns,
        rewards, notices, the redemption queue, and who else may look — stays with the
        one person answerable for it. The split is deliberate, not an oversight."""
        assert client.get("/admin/members", headers=auth("user_admin")).status_code == 200

    def test_none_of_the_refused_calls_left_an_audit_row(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        client.post("/admin/campaigns", headers=auth("user_admin"), json=NEW_CAMPAIGN)
        client.post(f"/admin/redemptions/{club['redemption']}/fulfill", headers=auth("user_alice"))

        assert audit_actions(session_factory) == []


class TestCampaignAndRewardCrud:
    def test_the_superuser_creates_a_campaign_and_it_is_audited(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        response = client.post("/admin/campaigns", headers=auth("user_boss"), json=NEW_CAMPAIGN)

        assert response.status_code == 201
        assert response.json()["code"] == "next-year"
        assert audit_actions(session_factory) == ["create_campaign"]

    def test_a_campaign_whose_config_the_policy_rejects_is_422(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        response = client.post(
            "/admin/campaigns",
            headers=auth("user_boss"),
            json={**NEW_CAMPAIGN, "code": "broken", "config": {}},
        )

        assert response.status_code == 422

    def test_creating_and_retiring_a_reward(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        created = client.post(
            "/admin/rewards",
            headers=auth("user_boss"),
            json={
                "campaign_id": str(CAMPAIGN), "name": "ผ้าบัฟ",
                "points_cost": "8", "stock": 5,
            },
        )
        assert created.status_code == 201

        catalogue = client.get("/rewards", headers=auth("user_alice")).json()
        assert {r["name"] for r in catalogue[0]["rewards"]} == {"Shirt", "ผ้าบัฟ"}

        retired = client.patch(
            f"/admin/rewards/{created.json()['id']}",
            headers=auth("user_boss"),
            json={"is_active": False},
        )

        assert retired.status_code == 200
        catalogue = client.get("/rewards", headers=auth("user_alice")).json()
        assert {r["name"] for r in catalogue[0]["rewards"]} == {"Shirt"}
        assert audit_actions(session_factory) == ["create_reward", "update_reward"]

    def test_retiring_a_reward_keeps_its_redemptions_readable(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        client.patch(
            f"/admin/rewards/{club['shirt']}", headers=auth("user_boss"),
            json={"is_active": False},
        )

        # Off the catalogue...
        catalogue = client.get("/rewards", headers=auth("user_alice")).json()
        assert catalogue[0]["rewards"] == []
        # ...but the member's history is intact.
        summary = client.get("/me/summary", headers=auth("user_alice")).json()
        assert len(summary["redemptions"]) == 1
        with session_factory() as session:
            assert session.get(models.Reward, club["shirt"]) is not None


class TestRedemptionHandling:
    def test_fulfilling_a_clean_redemption(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        response = client.post(
            f"/admin/redemptions/{club['redemption']}/fulfill", headers=auth("user_boss")
        )

        assert response.status_code == 200
        assert response.json()["status"] == "fulfilled"
        assert audit_actions(session_factory) == ["fulfill_redemption"]

    def test_a_rejected_run_blocks_fulfilment_until_it_is_resolved(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        """The whole point of the gate: rejecting the run that paid for this pulls the
        balance under, and the shirt must not be handed over."""
        rejected = client.post(
            f"/admin/runs/{club['run']}/review",
            headers=auth("user_boss"),
            json={"decision": "rejected"},
        )
        assert rejected.status_code == 200
        assert balance(session_factory, club["alice"]) == Decimal("-1.00")

        blocked = client.post(
            f"/admin/redemptions/{club['redemption']}/fulfill", headers=auth("user_boss")
        )

        assert blocked.status_code == 409
        # Cancelling is the way out: points back, item back.
        cancelled = client.post(
            f"/admin/redemptions/{club['redemption']}/cancel", headers=auth("user_boss")
        )
        assert cancelled.status_code == 200
        assert balance(session_factory, club["alice"]) == Decimal("0.00")
        with session_factory() as session:
            assert session.get(models.Reward, club["shirt"]).stock == 3  # type: ignore[union-attr]

    def test_a_flagged_run_blocks_fulfilment(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        client.post(
            f"/admin/runs/{club['run']}/review",
            headers=auth("user_boss"),
            json={"decision": "flagged"},
        )

        response = client.post(
            f"/admin/redemptions/{club['redemption']}/fulfill", headers=auth("user_boss")
        )

        assert response.status_code == 409

    def test_fulfilling_twice_is_409(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        client.post(f"/admin/redemptions/{club['redemption']}/fulfill", headers=auth("user_boss"))

        second = client.post(
            f"/admin/redemptions/{club['redemption']}/fulfill", headers=auth("user_boss")
        )

        assert second.status_code == 409

    def test_an_unknown_redemption_is_404(
        self, client: TestClient, club: dict[str, UUID]
    ) -> None:
        assert client.post(
            f"/admin/redemptions/{uuid4()}/fulfill", headers=auth("user_boss")
        ).status_code == 404


class TestChangingADecision:
    """Re-reviewing writes another ledger row attributed to the same run. Before
    migration 0002 the unique index refused that and the endpoint answered 500."""

    def test_reject_then_approve_the_same_run(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        assert balance(session_factory, club["alice"]) == Decimal("0.00")  # 1 earned, 1 spent

        rejected = client.post(
            f"/admin/runs/{club['run']}/review",
            headers=auth("user_boss"),
            json={"decision": "rejected"},
        )
        assert rejected.status_code == 200
        assert balance(session_factory, club["alice"]) == Decimal("-1.00")

        approved = client.post(
            f"/admin/runs/{club['run']}/review",
            headers=auth("user_boss"),
            json={"decision": "ok"},
        )

        assert approved.status_code == 200
        assert balance(session_factory, club["alice"]) == Decimal("0.00")
        assert audit_actions(session_factory) == ["review_run", "review_run"]

    def test_flipping_the_decision_several_times(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        for decision, expected in [
            ("rejected", "-1.00"),
            ("ok", "0.00"),
            ("rejected", "-1.00"),
            ("ok", "0.00"),
        ]:
            response = client.post(
                f"/admin/runs/{club['run']}/review",
                headers=auth("user_boss"),
                json={"decision": decision},
            )
            assert response.status_code == 200, response.text
            assert balance(session_factory, club["alice"]) == Decimal(expected)

    def test_a_run_rejected_after_the_campaign_closed_still_loses_its_points(
        self, client: TestClient, club: dict[str, UUID], session_factory: sessionmaker[Session]
    ) -> None:
        """The activity is over and the superuser has closed it; a late rejection must
        still take the points back."""
        closed = client.patch(
            f"/admin/campaigns/{CAMPAIGN}", headers=auth("user_boss"), json={"is_active": False}
        )
        assert closed.status_code == 200
        assert closed.json()["is_active"] is False

        rejected = client.post(
            f"/admin/runs/{club['run']}/review",
            headers=auth("user_boss"),
            json={"decision": "rejected"},
        )

        assert rejected.status_code == 200
        assert balance(session_factory, club["alice"]) == Decimal("-1.00")
