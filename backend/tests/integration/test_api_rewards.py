"""The redeem endpoint over HTTP: the caller's own points, and the 409 family."""

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
def rewards_seed(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    """Alice has 100 points; Dao has none. A shirt costs 60."""
    ids = {"alice": uuid4(), "dao": uuid4(), "shirt": uuid4(), "sticker": uuid4()}
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="rewards", name="Run for rewards", type="redeem_reward",
                starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
                config={"points_per_km": 1},
            )
        )
        session.add(
            models.Member(id=ids["alice"], clerk_user_id="user_alice", display_name="Alice")
        )
        session.add(models.Member(id=ids["dao"], clerk_user_id="user_dao", display_name="Dao"))
        session.add(
            models.Reward(
                id=ids["shirt"], campaign_id=CAMPAIGN, name="Shirt",
                points_cost=Decimal("60"), stock=2,
            )
        )
        session.add(
            models.Reward(
                id=ids["sticker"], campaign_id=CAMPAIGN, name="Sticker",
                points_cost=Decimal("5"), stock=1, is_active=False,
            )
        )
        session.flush()

        run_id = uuid4()
        session.add(
            models.RunEntry(
                id=run_id, member_id=ids["alice"], distance_km=Decimal("100"),
                duration_seconds=3600, run_date=date(2026, 6, 1),
                evidence_key="k", evidence_sha256=f"{run_id.hex}{run_id.hex}",
                source="app_screenshot",
            )
        )
        session.flush()
        session.add(
            models.PointsLedger(
                id=uuid4(), member_id=ids["alice"], campaign_id=CAMPAIGN,
                delta=Decimal("100"), reason="run_earned", run_entry_id=run_id,
            )
        )
        session.commit()
    return ids


def auth(clerk_user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {clerk_user_id}"}


def balance(session_factory: sessionmaker[Session], member_id: UUID) -> Decimal:
    with session_factory() as session:
        return Decimal(
            session.execute(
                sa.select(sa.func.coalesce(sa.func.sum(models.PointsLedger.delta), 0)).where(
                    models.PointsLedger.member_id == member_id
                )
            ).scalar_one()
        )


def test_redeeming_spends_the_callers_own_points(
    client: TestClient, rewards_seed: dict[str, UUID], session_factory: sessionmaker[Session]
) -> None:
    response = client.post(
        f"/rewards/{rewards_seed['shirt']}/redeem", headers=auth("user_alice")
    )

    assert response.status_code == 201
    assert response.json()["points_spent"] == "60.00"
    assert balance(session_factory, rewards_seed["alice"]) == Decimal("40.00")


def test_redeeming_twice_without_enough_points_is_409(
    client: TestClient, rewards_seed: dict[str, UUID], session_factory: sessionmaker[Session]
) -> None:
    assert (
        client.post(
            f"/rewards/{rewards_seed['shirt']}/redeem", headers=auth("user_alice")
        ).status_code
        == 201
    )

    second = client.post(f"/rewards/{rewards_seed['shirt']}/redeem", headers=auth("user_alice"))

    assert second.status_code == 409
    # The balance never goes negative, whatever the client does.
    assert balance(session_factory, rewards_seed["alice"]) == Decimal("40.00")


def test_a_member_with_no_points_is_409(
    client: TestClient, rewards_seed: dict[str, UUID]
) -> None:
    response = client.post(f"/rewards/{rewards_seed['shirt']}/redeem", headers=auth("user_dao"))

    assert response.status_code == 409


def test_an_inactive_reward_is_409(
    client: TestClient, rewards_seed: dict[str, UUID]
) -> None:
    response = client.post(
        f"/rewards/{rewards_seed['sticker']}/redeem", headers=auth("user_alice")
    )

    assert response.status_code == 409


def test_an_unknown_reward_is_409(client: TestClient, rewards_seed: dict[str, UUID]) -> None:
    assert client.post(f"/rewards/{uuid4()}/redeem", headers=auth("user_alice")).status_code == 409


def test_redeeming_needs_a_token(client: TestClient, rewards_seed: dict[str, UUID]) -> None:
    assert client.post(f"/rewards/{rewards_seed['shirt']}/redeem").status_code == 401


def test_alices_points_are_not_spendable_by_dao(
    client: TestClient, rewards_seed: dict[str, UUID], session_factory: sessionmaker[Session]
) -> None:
    """There is no member_id anywhere in this request to tamper with."""
    response = client.post(f"/rewards/{rewards_seed['shirt']}/redeem", headers=auth("user_dao"))

    assert response.status_code == 409
    assert balance(session_factory, rewards_seed["alice"]) == Decimal("100.00")
