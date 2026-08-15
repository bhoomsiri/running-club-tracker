"""The three admin list endpoints: campaigns, rewards, and the redemption queue.

The queue is the one that mattered. Fulfil and cancel already existed, but the only way
to reach them was to know a redemption's id, which nobody does.
"""

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
CLOSED_CAMPAIGN = UUID("44444444-4444-4444-4444-444444444444")
NOW = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)

ALICE = uuid4()
BOSS = uuid4()
SHIRT = uuid4()
RETIRED = uuid4()


def auth(clerk_user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {clerk_user_id}"}


@pytest.fixture
def club(session_factory: sessionmaker[Session]) -> None:
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
            models.Campaign(
                id=CLOSED_CAMPAIGN, code="last-year", name="ปีที่แล้ว",
                type="cumulative_distance", starts_on=date(2025, 1, 1),
                ends_on=date(2025, 12, 31), config={"target_km": 100}, is_active=False,
            )
        )
        session.add(
            models.Member(
                id=ALICE, clerk_user_id="user_alice", display_name="Alice",
                full_name_th="สมหญิง วิ่งดี",
            )
        )
        session.add(
            models.Member(
                id=BOSS, clerk_user_id=BOSS_CLERK_ID, display_name="Boss", role="superuser"
            )
        )
        session.add(
            models.Reward(
                id=SHIRT, campaign_id=CAMPAIGN, name="เสื้อวิ่ง",
                points_cost=Decimal("10"), stock=5,
            )
        )
        session.add(
            models.Reward(
                id=RETIRED, campaign_id=CAMPAIGN, name="ของเก่าเลิกแจก",
                points_cost=Decimal("3"), stock=0, is_active=False,
            )
        )
        session.commit()


def redeem_for(
    session_factory: sessionmaker[Session], *, balance: Decimal, flagged: bool = False
) -> UUID:
    """Alice has redeemed the shirt, leaving her at `balance`, optionally with a run
    still awaiting a decision."""
    redemption_id = uuid4()
    with session_factory() as session:
        session.add(
            models.PointsLedger(
                id=uuid4(), member_id=ALICE, campaign_id=CAMPAIGN,
                delta=balance, reason="adjustment",
            )
        )
        session.add(
            models.Redemption(
                id=redemption_id, member_id=ALICE, reward_id=SHIRT, campaign_id=CAMPAIGN,
                points_spent=Decimal("10"), status="pending",
            )
        )
        if flagged:
            session.add(
                models.RunEntry(
                    id=uuid4(), member_id=ALICE, distance_km=Decimal("12"),
                    duration_seconds=1800, run_date=date(2026, 8, 18),
                    evidence_key="k", evidence_sha256="f" * 64,
                    source="app_screenshot", review_status="flagged", created_at=NOW,
                )
            )
        session.commit()
    return redemption_id


def get(client: TestClient, path: str) -> list[Any]:
    response = client.get(path, headers=auth(BOSS_CLERK_ID))
    assert response.status_code == 200, response.text
    rows: list[Any] = response.json()
    return rows


class TestCampaigns:
    def test_closed_campaigns_are_listed_too(self, client: TestClient, club: None) -> None:
        """A finished activity is still something to look at, and correcting one still
        has to be possible."""
        codes = {row["code"] for row in get(client, "/admin/campaigns")}

        assert codes == {"daily-10km", "last-year"}

    def test_a_member_may_not(self, client: TestClient, club: None) -> None:
        assert client.get("/admin/campaigns", headers=auth("user_alice")).status_code == 403


class TestRewards:
    def test_retired_rewards_are_listed(self, client: TestClient, club: None) -> None:
        """They are withdrawn, never deleted. One missing from this screen would look
        deleted, and someone would recreate it."""
        rows = get(client, f"/admin/rewards?campaign_id={CAMPAIGN}")

        by_name = {row["name"]: row for row in rows}
        assert by_name["ของเก่าเลิกแจก"]["is_active"] is False
        assert by_name["เสื้อวิ่ง"]["is_active"] is True

    def test_the_member_facing_list_still_shows_only_active_ones(
        self, client: TestClient, club: None
    ) -> None:
        catalogue = client.get("/rewards", headers=auth("user_alice")).json()

        names = {r["name"] for c in catalogue for r in c["rewards"]}
        assert names == {"เสื้อวิ่ง"}

    def test_a_member_may_not(self, client: TestClient, club: None) -> None:
        response = client.get(
            f"/admin/rewards?campaign_id={CAMPAIGN}", headers=auth("user_alice")
        )

        assert response.status_code == 403


class TestRedemptionQueue:
    def test_a_pending_redemption_appears_with_names(
        self, client: TestClient, club: None, session_factory: sessionmaker[Session]
    ) -> None:
        """Names, because an id tells whoever is handing over the shirt nothing."""
        redeem_for(session_factory, balance=Decimal("5"))

        rows = get(client, "/admin/redemptions")

        assert len(rows) == 1
        assert rows[0]["member_name"] == "สมหญิง วิ่งดี"
        assert rows[0]["reward_name"] == "เสื้อวิ่ง"
        assert Decimal(rows[0]["redemption"]["points_spent"]) == Decimal("10")

    def test_a_clear_redemption_is_not_blocked(
        self, client: TestClient, club: None, session_factory: sessionmaker[Session]
    ) -> None:
        redeem_for(session_factory, balance=Decimal("5"))

        assert get(client, "/admin/redemptions")[0]["blocked_by"] is None

    def test_a_negative_balance_blocks_it(
        self, client: TestClient, club: None, session_factory: sessionmaker[Session]
    ) -> None:
        """A rejected run has taken the member below zero; handing the item over now
        gives away something they no longer have the points for."""
        redeem_for(session_factory, balance=Decimal("-4"))

        assert get(client, "/admin/redemptions")[0]["blocked_by"] == "negative_balance"

    def test_a_run_awaiting_review_blocks_it(
        self, client: TestClient, club: None, session_factory: sessionmaker[Session]
    ) -> None:
        redeem_for(session_factory, balance=Decimal("5"), flagged=True)

        assert get(client, "/admin/redemptions")[0]["blocked_by"] == "unresolved_runs"

    def test_the_reason_shown_matches_what_fulfil_actually_does(
        self, client: TestClient, club: None, session_factory: sessionmaker[Session]
    ) -> None:
        """The queue predicts; the fulfil endpoint decides. If the two ever disagree, the
        button says one thing and the server does another."""
        redemption_id = redeem_for(session_factory, balance=Decimal("5"), flagged=True)
        assert get(client, "/admin/redemptions")[0]["blocked_by"] == "unresolved_runs"

        response = client.post(
            f"/admin/redemptions/{redemption_id}/fulfill", headers=auth(BOSS_CLERK_ID)
        )

        assert response.status_code == 409

    def test_a_fulfilled_redemption_leaves_the_queue(
        self, client: TestClient, club: None, session_factory: sessionmaker[Session]
    ) -> None:
        redemption_id = redeem_for(session_factory, balance=Decimal("5"))

        assert (
            client.post(
                f"/admin/redemptions/{redemption_id}/fulfill", headers=auth(BOSS_CLERK_ID)
            ).status_code
            == 200
        )

        assert get(client, "/admin/redemptions") == []

    def test_a_member_may_not_see_the_queue(self, client: TestClient, club: None) -> None:
        assert (
            client.get("/admin/redemptions", headers=auth("user_alice")).status_code == 403
        )
