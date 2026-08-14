"""Golden rule #5, proved against a real PostgreSQL with real concurrent transactions.

The fake-based unit tests show the logic is right when calls happen one after another.
These show it holds when two transactions genuinely overlap — which is the only way to
test what the locking is actually for.

How the overlap is forced: both threads start together on a barrier, and the injected
clock sleeps inside the transaction at the moment between reading the balance and
writing. Without the right lock the second transaction reads a stale balance during
that sleep; `test_without_serialization_the_balance_race_double_spends` demonstrates
exactly that, so these tests are known to be capable of failing.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from app.adapters.persistence.sqlalchemy_points_ledger_repository import (
    SqlAlchemyPointsLedgerRepository,
)
from app.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.application.use_cases.redeem_reward import RedeemReward, RedeemRewardCommand
from app.domain.errors import DomainError, InsufficientPoints, OutOfStock
from app.domain.redemption import PointsEntry

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
CAMPAIGN = UUID("22222222-2222-2222-2222-222222222222")
# Long enough that both transactions are certainly in flight together.
OVERLAP_SECONDS = 0.4


class _UnserializedLedger:
    """The ledger repository with ONLY the advisory lock removed — every other query is
    the real one."""

    def __init__(self, inner: SqlAlchemyPointsLedgerRepository) -> None:
        self._inner = inner

    def serialize_account(self, member_id: UUID, campaign_id: UUID) -> None:
        return None

    def balance(self, member_id: UUID, campaign_id: UUID) -> Decimal:
        return self._inner.balance(member_id, campaign_id)

    def add(self, entry: PointsEntry) -> None:
        self._inner.add(entry)


class UnserializedUnitOfWork(SqlAlchemyUnitOfWork):
    """Test-only: the production UnitOfWork minus the account lock."""

    @property
    def ledger(self) -> _UnserializedLedger:  # type: ignore[override]
        return _UnserializedLedger(super().ledger)


class SlowClock:
    """A Clock that pauses where the use case asks for the time — between reading the
    balance and writing the ledger row. That is precisely the window a second
    transaction must not be able to slip through."""

    def __init__(self, now: datetime, delay: float) -> None:
        self._now = now
        self._delay = delay

    def now(self) -> datetime:
        time.sleep(self._delay)
        return self._now


def seed(
    session_factory: sessionmaker[Session],
    *,
    members: dict[UUID, str],
    rewards: list[tuple[UUID, str, str, int]],
    points: dict[UUID, str],
) -> None:
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="rewards", name="Run for rewards", type="redeem_reward",
                starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
                config={"points_per_km": 1},
            )
        )
        for member_id, name in members.items():
            session.add(
                models.Member(id=member_id, clerk_user_id=f"clerk_{name}", display_name=name)
            )
        for reward_id, name, cost, stock in rewards:
            session.add(
                models.Reward(
                    id=reward_id, campaign_id=CAMPAIGN, name=name,
                    points_cost=Decimal(cost), stock=stock,
                )
            )
        session.flush()  # runs must exist before ledger rows can reference them

        for member_id, amount in points.items():
            run_id = uuid4()
            session.add(
                models.RunEntry(
                    id=run_id, member_id=member_id, distance_km=Decimal("10"),
                    duration_seconds=1800, run_date=date(2026, 6, 1),
                    evidence_key=f"k-{run_id}", evidence_sha256=f"{run_id.hex}{run_id.hex}",
                    source="app_screenshot",
                )
            )
            session.flush()
            session.add(
                models.PointsLedger(
                    id=uuid4(), member_id=member_id, campaign_id=CAMPAIGN,
                    delta=Decimal(amount), reason="run_earned", run_entry_id=run_id,
                )
            )
        session.commit()


def redeem_concurrently(
    session_factory: sessionmaker[Session],
    attempts: list[tuple[UUID, UUID]],
    *,
    serialize: bool = True,
) -> list[BaseException | None]:
    """Run every (member, reward) attempt in its own thread and transaction, released
    together. Returns each thread's error, or None where it succeeded."""
    barrier = threading.Barrier(len(attempts))
    errors: list[BaseException | None] = [None] * len(attempts)

    def attempt(index: int, member_id: UUID, reward_id: UUID) -> None:
        # Same use case either way; only the UnitOfWork's locking differs.
        uow_class = SqlAlchemyUnitOfWork if serialize else UnserializedUnitOfWork
        use_case = RedeemReward(uow_class(session_factory, SlowClock(NOW, OVERLAP_SECONDS)))
        barrier.wait()
        try:
            use_case.execute(RedeemRewardCommand(member_id=member_id, reward_id=reward_id))
        except Exception as e:
            errors[index] = e

    threads = [
        threading.Thread(target=attempt, args=(i, m, r)) for i, (m, r) in enumerate(attempts)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a redeem transaction hung"
    return errors


def balance_of(session_factory: sessionmaker[Session], member_id: UUID) -> Decimal:
    with session_factory() as session:
        return Decimal(
            session.execute(
                sa.select(sa.func.coalesce(sa.func.sum(models.PointsLedger.delta), 0)).where(
                    models.PointsLedger.member_id == member_id,
                    models.PointsLedger.campaign_id == CAMPAIGN,
                )
            ).scalar_one()
        )


def stock_of(session_factory: sessionmaker[Session], reward_id: UUID) -> int:
    with session_factory() as session:
        return session.execute(
            sa.select(models.Reward.stock).where(models.Reward.id == reward_id)
        ).scalar_one()


def count_redemptions(session_factory: sessionmaker[Session]) -> int:
    with session_factory() as session:
        return session.execute(
            sa.select(sa.func.count()).select_from(models.Redemption)
        ).scalar_one()


class TestStockRace:
    def test_last_item_cannot_be_sold_twice(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Two members, one item left, both redeem at the same instant."""
        alice, bob = uuid4(), uuid4()
        shirt = uuid4()
        seed(
            session_factory,
            members={alice: "alice", bob: "bob"},
            rewards=[(shirt, "Shirt", "50", 1)],
            points={alice: "100", bob: "100"},
        )

        errors = redeem_concurrently(session_factory, [(alice, shirt), (bob, shirt)])

        assert sum(e is None for e in errors) == 1, "exactly one redemption should succeed"
        failure = next(e for e in errors if e is not None)
        assert isinstance(failure, OutOfStock)
        assert stock_of(session_factory, shirt) == 0  # never negative
        assert count_redemptions(session_factory) == 1


class TestBalanceRace:
    """The case a row lock cannot catch: the balance is a SUM over rows that do not
    exist yet, so both transactions insert their own negative row (a phantom)."""

    def test_two_different_rewards_cannot_overdraw_one_account(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        alice = uuid4()
        shirt, cap = uuid4(), uuid4()
        # 100 points; each reward costs 60 — affordable alone, not together. The two
        # rewards are separate rows, so FOR UPDATE does not serialise these at all.
        seed(
            session_factory,
            members={alice: "alice"},
            rewards=[(shirt, "Shirt", "60", 5), (cap, "Cap", "60", 5)],
            points={alice: "100"},
        )

        errors = redeem_concurrently(session_factory, [(alice, shirt), (alice, cap)])

        assert sum(e is None for e in errors) == 1, "exactly one redemption should succeed"
        failure = next(e for e in errors if e is not None)
        assert isinstance(failure, InsufficientPoints)
        assert balance_of(session_factory, alice) == Decimal("40.00")
        assert balance_of(session_factory, alice) >= 0
        assert count_redemptions(session_factory) == 1

    def test_without_serialization_the_balance_race_double_spends(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        """Proof the test above is not passing by accident: with the advisory lock
        removed, the same scenario overdraws the account."""
        alice = uuid4()
        shirt, cap = uuid4(), uuid4()
        seed(
            session_factory,
            members={alice: "alice"},
            rewards=[(shirt, "Shirt", "60", 5), (cap, "Cap", "60", 5)],
            points={alice: "100"},
        )

        errors = redeem_concurrently(
            session_factory, [(alice, shirt), (alice, cap)], serialize=False
        )

        assert all(e is None for e in errors), "both should have slipped through"
        assert balance_of(session_factory, alice) == Decimal("-20.00")  # overdrawn
        assert count_redemptions(session_factory) == 2


class TestTransactionIntegrity:
    def test_a_rejected_redeem_leaves_nothing_behind(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        alice = uuid4()
        shirt = uuid4()
        seed(
            session_factory,
            members={alice: "alice"},
            rewards=[(shirt, "Shirt", "60", 3)],
            points={alice: "10"},
        )
        uow = SqlAlchemyUnitOfWork(session_factory, SlowClock(NOW, 0))

        with pytest.raises(InsufficientPoints):
            RedeemReward(uow).execute(RedeemRewardCommand(member_id=alice, reward_id=shirt))

        assert balance_of(session_factory, alice) == Decimal("10.00")
        assert stock_of(session_factory, shirt) == 3
        assert count_redemptions(session_factory) == 0

    def test_a_successful_redeem_writes_all_three_effects(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        alice = uuid4()
        shirt = uuid4()
        seed(
            session_factory,
            members={alice: "alice"},
            rewards=[(shirt, "Shirt", "60", 3)],
            points={alice: "100"},
        )
        uow = SqlAlchemyUnitOfWork(session_factory, SlowClock(NOW, 0))

        redemption = RedeemReward(uow).execute(
            RedeemRewardCommand(member_id=alice, reward_id=shirt)
        )

        assert redemption.points_spent == Decimal("60.00")
        assert balance_of(session_factory, alice) == Decimal("40.00")
        assert stock_of(session_factory, shirt) == 2
        assert count_redemptions(session_factory) == 1

    def test_domain_errors_are_not_swallowed(
        self, session_factory: sessionmaker[Session]
    ) -> None:
        uow = SqlAlchemyUnitOfWork(session_factory, SlowClock(NOW, 0))

        with pytest.raises(DomainError):
            RedeemReward(uow).execute(
                RedeemRewardCommand(member_id=uuid4(), reward_id=uuid4())
            )
