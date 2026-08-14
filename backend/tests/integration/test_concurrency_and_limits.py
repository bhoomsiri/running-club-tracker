"""Two things that only misbehave under real conditions: a shared rate limiter, and
transactions that overlap.

The submit-vs-redeem race is the one the advisory lock exists for that had not been
tested: submitting a run recomputes the balance while a redemption is checking it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from app.adapters.persistence.run_submission_unit_of_work import (
    SqlAlchemyRunSubmissionUnitOfWork,
)
from app.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.api import deps
from app.application.use_cases.redeem_reward import RedeemReward, RedeemRewardCommand
from app.application.use_cases.submit_run import SubmitRun, SubmitRunCommand
from app.config import Settings
from app.domain.entities import RunSource
from app.main import create_app
from tests.fakes.fake_storage import FakeImageStorage, FakeRunExtractor
from tests.integration.conftest import StubVerifier

pytestmark = pytest.mark.integration

CAMPAIGN = UUID("33333333-3333-3333-3333-333333333333")
NOW = datetime(2026, 8, 21, 9, 0, tzinfo=UTC)
OVERLAP_SECONDS = 0.4


class SlowClock:
    """Pauses where the use case asks for the time — inside the transaction, after the
    balance has been read and before it is written."""

    def __init__(self, now: datetime, delay: float) -> None:
        self._now = now
        self._delay = delay

    def now(self) -> datetime:
        import time

        time.sleep(self._delay)
        return self._now


@pytest.fixture
def racing_seed(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    """Alice has 10 points and a reward costing 10 — she can afford exactly one."""
    ids = {"alice": uuid4(), "shirt": uuid4(), "run": uuid4()}
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="daily-10km", name="daily 10",
                type="daily_threshold_reward", starts_on=date(2026, 8, 15),
                ends_on=date(2026, 9, 30),
                config={
                    "qualifying_km": 10, "points_per_qualifying_day": 10,
                    "submit_within_days": 1,
                },
            )
        )
        session.add(
            models.Member(id=ids["alice"], clerk_user_id="user_alice", display_name="Alice")
        )
        session.add(
            models.Reward(
                id=ids["shirt"], campaign_id=CAMPAIGN, name="Shirt",
                points_cost=Decimal("10"), stock=5,
            )
        )
        session.flush()
        session.add(
            models.RunEntry(
                id=ids["run"], member_id=ids["alice"], distance_km=Decimal("11"),
                duration_seconds=1800, run_date=date(2026, 8, 20), evidence_key="k",
                evidence_sha256="a" * 64, source="app_screenshot", created_at=NOW,
            )
        )
        session.flush()
        session.add(
            models.PointsLedger(
                id=uuid4(), member_id=ids["alice"], campaign_id=CAMPAIGN,
                delta=Decimal("10"), reason="run_earned", run_entry_id=ids["run"],
            )
        )
        session.commit()
    return ids


def balance(session_factory: sessionmaker[Session], member_id: UUID) -> Decimal:
    with session_factory() as session:
        return Decimal(
            session.execute(
                sa.select(sa.func.coalesce(sa.func.sum(models.PointsLedger.delta), 0)).where(
                    models.PointsLedger.member_id == member_id
                )
            ).scalar_one()
        )


def test_submitting_a_run_and_redeeming_at_the_same_instant(
    session_factory: sessionmaker[Session], racing_seed: dict[str, UUID]
) -> None:
    """Both transactions touch the same account: one recomputes what was earned, the
    other spends it. Serialised by the advisory lock, the result is arithmetic; without
    it, the reconciliation would be computed against a balance that is about to change.
    """
    alice, shirt = racing_seed["alice"], racing_seed["shirt"]
    barrier = threading.Barrier(2)
    errors: dict[str, BaseException] = {}

    def submit() -> None:
        uow = SqlAlchemyRunSubmissionUnitOfWork(
            session_factory, SlowClock(NOW, OVERLAP_SECONDS)
        )
        barrier.wait()
        try:
            # A second qualifying day: +10 points once reconciled.
            SubmitRun(uow).execute(
                SubmitRunCommand(
                    member_id=alice, distance_km=Decimal("12"), duration_seconds=1800,
                    run_date=date(2026, 8, 21),
                    image_key=f"runs/{alice}/{'b' * 64}.jpeg",
                    source=RunSource.APP_SCREENSHOT,
                )
            )
        except BaseException as e:  # noqa: BLE001 - asserted on below
            errors["submit"] = e

    def redeem() -> None:
        uow = SqlAlchemyUnitOfWork(session_factory, SlowClock(NOW, OVERLAP_SECONDS))
        barrier.wait()
        try:
            RedeemReward(uow).execute(RedeemRewardCommand(member_id=alice, reward_id=shirt))
        except BaseException as e:  # noqa: BLE001 - asserted on below
            errors["redeem"] = e

    threads = [threading.Thread(target=submit), threading.Thread(target=redeem)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a transaction hung — check lock order"

    assert errors == {}, f"neither should fail: {errors}"
    # 10 earned + 10 earned - 10 spent, in whichever order they landed.
    assert balance(session_factory, alice) == Decimal("10.00")
    with session_factory() as session:
        assert session.execute(
            sa.select(sa.func.count()).select_from(models.Redemption)
        ).scalar_one() == 1


def test_cancelling_and_redeeming_the_same_reward_at_once(
    session_factory: sessionmaker[Session], racing_seed: dict[str, UUID]
) -> None:
    """Cancel takes the reward row then the account; redeem takes them in the same
    order. Opposite orders here would deadlock instead of queueing."""
    from app.adapters.persistence.admin_unit_of_work import SqlAlchemyAdminUnitOfWork
    from app.application.use_cases.manage_redemptions import (
        CancelRedemption,
        RedemptionCommand,
    )

    alice, shirt = racing_seed["alice"], racing_seed["shirt"]
    boss_id, redemption_id = uuid4(), uuid4()
    with session_factory() as session:
        session.add(
            models.Member(
                id=boss_id, clerk_user_id="user_boss", display_name="Boss", role="superuser"
            )
        )
        session.add(
            models.Redemption(
                id=redemption_id, member_id=alice, reward_id=shirt, campaign_id=CAMPAIGN,
                points_spent=Decimal("10"), status="pending",
            )
        )
        session.flush()
        session.add(
            models.PointsLedger(
                id=uuid4(), member_id=alice, campaign_id=CAMPAIGN, delta=Decimal("-10"),
                reason="redeemed", redemption_id=redemption_id,
            )
        )
        session.commit()

    barrier = threading.Barrier(2)
    errors: dict[str, BaseException] = {}

    def cancel() -> None:
        uow = SqlAlchemyAdminUnitOfWork(session_factory, SlowClock(NOW, OVERLAP_SECONDS))
        barrier.wait()
        try:
            CancelRedemption(uow).execute(
                RedemptionCommand(actor_id=boss_id, redemption_id=redemption_id)
            )
        except BaseException as e:  # noqa: BLE001 - asserted on below
            errors["cancel"] = e

    def redeem() -> None:
        uow = SqlAlchemyUnitOfWork(session_factory, SlowClock(NOW, OVERLAP_SECONDS))
        barrier.wait()
        try:
            RedeemReward(uow).execute(RedeemRewardCommand(member_id=alice, reward_id=shirt))
        except Exception as e:
            errors["redeem"] = e  # InsufficientPoints is a legitimate outcome here

    threads = [threading.Thread(target=cancel), threading.Thread(target=redeem)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "deadlock: check the lock order"

    assert "cancel" not in errors, f"the cancel should always succeed: {errors.get('cancel')}"
    assert balance(session_factory, alice) >= 0


# The evidence key embeds the owner's member id, so this member is seeded with a fixed
# id and the key is built from it — otherwise the ownership check would refuse.
EXTRACT_MEMBER = UUID("44444444-4444-4444-4444-444444444444")
EXTRACT_CLERK_ID = "user_extract"
EXTRACT_KEY = f"runs/{EXTRACT_MEMBER}/{'c' * 64}.jpeg"


@pytest.fixture
def limited_client(
    engine: Engine, session_factory: sessionmaker[Session], settings: Settings
) -> Iterator[TestClient]:
    """Limits on, and /runs/extract tightened to two calls."""
    throttled = settings.model_copy(
        update={
            "rate_limit_enabled": True,
            "rate_limit": "1000/minute",
            "extract_rate_limit": "2/minute",
        }
    )
    app = create_app(throttled)
    app.dependency_overrides[deps.get_settings_dep] = lambda: throttled
    app.dependency_overrides[deps.get_session_factory_dep] = lambda: session_factory
    app.dependency_overrides[deps.get_token_verifier] = StubVerifier
    with session_factory() as session:
        session.add(
            models.Member(
                id=EXTRACT_MEMBER, clerk_user_id=EXTRACT_CLERK_ID, display_name="Extractor"
            )
        )
        session.commit()

    storage = FakeImageStorage()
    storage.put(EXTRACT_KEY, b"\xff\xd8\xff\xe0" + b"jpeg" * 40, "image/jpeg")
    app.dependency_overrides[deps.get_image_storage] = lambda: storage
    app.dependency_overrides[deps.get_run_extractor] = lambda: FakeRunExtractor()
    with TestClient(app) as client:
        yield client


def test_the_extract_endpoint_has_its_own_tighter_limit(
    limited_client: TestClient,
) -> None:
    """Each extract call costs money at Gemini, so it is limited far below the global
    default — which is set to 1000/minute here to prove the per-route limit is what
    bites."""
    body = {"image_key": EXTRACT_KEY}
    headers = {"Authorization": f"Bearer {EXTRACT_CLERK_ID}"}

    codes = [
        limited_client.post("/runs/extract", headers=headers, json=body).status_code
        for _ in range(3)
    ]

    assert codes[:2] == [200, 200]
    assert codes[2] == 429


def test_the_tight_extract_limit_does_not_throttle_other_endpoints(
    limited_client: TestClient,
) -> None:
    headers = {"Authorization": f"Bearer {EXTRACT_CLERK_ID}"}
    for _ in range(3):
        limited_client.post("/runs/extract", headers=headers, json={"image_key": EXTRACT_KEY})

    assert limited_client.get("/me/summary", headers=headers).status_code == 200


def test_extracting_from_a_key_that_was_never_uploaded_is_404(
    limited_client: TestClient,
) -> None:
    """A well-formed key the caller owns but never uploaded is a client mistake, not a
    server fault."""
    response = limited_client.post(
        "/runs/extract",
        headers={"Authorization": f"Bearer {EXTRACT_CLERK_ID}"},
        json={"image_key": f"runs/{EXTRACT_MEMBER}/{'d' * 64}.jpeg"},
    )

    assert response.status_code == 404
