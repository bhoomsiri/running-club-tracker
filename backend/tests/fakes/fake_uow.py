"""In-memory fakes: no DB, no network.

The fake UnitOfWork STAGES writes and only applies them on commit(), so a test can
assert that an aborted redemption left nothing behind — the same guarantee the real
SQLAlchemy transaction gives.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from types import TracebackType
from uuid import UUID

from app.domain.audit import AuditEntry
from app.domain.redemption import (
    LedgerReason,
    PointsEntry,
    Redemption,
    RedemptionStatus,
    Reward,
)
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeMemberRepository,
    FakeRunRepository,
)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeRewardRepository:
    def __init__(self, rewards: list[Reward] | None = None) -> None:
        self._items: dict[UUID, Reward] = {r.id: r for r in rewards or []}
        self.locked: list[UUID] = []  # records that get_for_update was used
        self._staged_decrements: list[UUID] = []
        self._staged_increments: list[UUID] = []

    def get(self, reward_id: UUID) -> Reward | None:
        return self._items.get(reward_id)

    def get_for_update(self, reward_id: UUID) -> Reward | None:
        self.locked.append(reward_id)
        return self._items.get(reward_id)

    def list_for_campaign(self, campaign_id: UUID) -> list[Reward]:
        return [r for r in self._items.values() if r.campaign_id == campaign_id]

    def list_active_for_campaign(self, campaign_id: UUID) -> list[Reward]:
        return [
            r for r in self._items.values() if r.campaign_id == campaign_id and r.is_active
        ]

    def add(self, reward: Reward) -> None:
        self._items[reward.id] = reward

    def save(self, reward: Reward) -> None:
        self._items[reward.id] = reward

    def increment_stock(self, reward_id: UUID) -> None:
        self._staged_increments.append(reward_id)

    def decrement_stock(self, reward_id: UUID) -> None:
        self._staged_decrements.append(reward_id)

    def commit(self) -> None:
        for reward_id in self._staged_increments:
            current = self._items[reward_id]
            self._items[reward_id] = replace(current, stock=current.stock + 1)
        self._staged_increments.clear()
        for reward_id in self._staged_decrements:
            current = self._items[reward_id]
            self._items[reward_id] = Reward(
                id=current.id,
                campaign_id=current.campaign_id,
                name=current.name,
                points_cost=current.points_cost,
                stock=current.stock - 1,
                is_active=current.is_active,
            )
        self._staged_decrements.clear()

    def rollback(self) -> None:
        self._staged_decrements.clear()
        self._staged_increments.clear()


class FakePointsLedgerRepository:
    def __init__(self, entries: list[PointsEntry] | None = None) -> None:
        self._items: list[PointsEntry] = list(entries or [])
        self._staged: list[PointsEntry] = []
        self.serialized: list[tuple[UUID, UUID]] = []

    def serialize_account(self, member_id: UUID, campaign_id: UUID) -> None:
        # No-op: the fake runs single-threaded, so there is nothing to serialise. The
        # SQLAlchemy adapter takes a real advisory lock here.
        self.serialized.append((member_id, campaign_id))

    def balance(self, member_id: UUID, campaign_id: UUID) -> Decimal:
        return sum(
            (e.delta for e in self._items if e.member_id == member_id
             and e.campaign_id == campaign_id),
            start=Decimal("0"),
        )

    def balances_for_campaign(self, campaign_id: UUID) -> dict[UUID, Decimal]:
        totals: dict[UUID, Decimal] = {}
        for entry in self._items:
            if entry.campaign_id == campaign_id:
                totals[entry.member_id] = totals.get(entry.member_id, Decimal("0")) + entry.delta
        # Members with no rows are absent, exactly as the GROUP BY leaves them.
        return totals

    def credited_total(self, member_id: UUID, campaign_id: UUID) -> Decimal:
        return sum(
            (
                e.delta
                for e in self._items
                if e.member_id == member_id
                and e.campaign_id == campaign_id
                and e.reason in (LedgerReason.RUN_EARNED, LedgerReason.REVERSAL)
                # Earning rows only: a cancelled redemption's refund is a reversal too,
                # but it references the redemption, not a run.
                and e.run_entry_id is not None
            ),
            start=Decimal("0"),
        )

    def has_entries_for_campaign(self, campaign_id: UUID) -> bool:
        return any(e.campaign_id == campaign_id for e in self._items)

    def add(self, entry: PointsEntry) -> None:
        self._staged.append(entry)

    def all_entries(self) -> list[PointsEntry]:
        return list(self._items)

    def commit(self) -> None:
        self._items.extend(self._staged)
        self._staged.clear()

    def rollback(self) -> None:
        self._staged.clear()


class FakeRedemptionRepository:
    def __init__(self, redemptions: list[Redemption] | None = None) -> None:
        self._items: list[Redemption] = list(redemptions or [])
        self._staged: list[Redemption] = []
        self._staged_status: dict[UUID, RedemptionStatus] = {}

    def add(self, redemption: Redemption) -> None:
        self._staged.append(redemption)

    def get(self, redemption_id: UUID) -> Redemption | None:
        return next((r for r in self._items if r.id == redemption_id), None)

    def list_pending(self) -> list[Redemption]:
        return [r for r in self._items if r.status is RedemptionStatus.PENDING]

    def set_status(self, redemption_id: UUID, status: RedemptionStatus) -> None:
        self._staged_status[redemption_id] = status

    def exists_for_reward(self, reward_id: UUID) -> bool:
        return any(r.reward_id == reward_id for r in self._items)

    def list_by_member(self, member_id: UUID) -> list[Redemption]:
        return [r for r in self._items if r.member_id == member_id]

    def commit(self) -> None:
        self._items.extend(self._staged)
        self._staged.clear()

    def rollback(self) -> None:
        self._staged.clear()


class FakeUnitOfWork:
    def __init__(
        self,
        *,
        rewards: FakeRewardRepository,
        ledger: FakePointsLedgerRepository,
        clock: FixedClock,
        redemptions: FakeRedemptionRepository | None = None,
    ) -> None:
        self.rewards = rewards
        self.ledger = ledger
        self.redemptions = redemptions or FakeRedemptionRepository()
        self.clock = clock
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeUnitOfWork:
        self.committed = False
        self.rolled_back = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Leaving without an explicit commit discards everything — an exception on the
        # way out must never leave a half-finished redemption behind.
        if not self.committed:
            self.rollback()

    def commit(self) -> None:
        self.rewards.commit()
        self.ledger.commit()
        self.redemptions.commit()
        self.committed = True

    def rollback(self) -> None:
        self.rewards.rollback()
        self.ledger.rollback()
        self.redemptions.rollback()
        self.rolled_back = True


class FakeAuditRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self._items: list[AuditEntry] = []
        self._staged: list[AuditEntry] = []
        self._fail = fail

    def record(self, entry: AuditEntry) -> None:
        if self._fail:
            raise RuntimeError("audit backend is down")
        self._staged.append(entry)

    def committed_entries(self) -> list[AuditEntry]:
        return list(self._items)

    def commit(self) -> None:
        self._items.extend(self._staged)
        self._staged.clear()

    def rollback(self) -> None:
        self._staged.clear()


class FakeRunSubmissionUnitOfWork:
    """Runs + campaigns + ledger in one transaction, like the real submission UoW."""

    def __init__(
        self,
        *,
        runs: FakeRunRepository,
        campaigns: FakeCampaignRepository,
        ledger: FakePointsLedgerRepository,
        clock: FixedClock,
    ) -> None:
        self.runs = runs
        self.campaigns = campaigns
        self.ledger = ledger
        self.clock = clock
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeRunSubmissionUnitOfWork:
        self.committed = False
        self.rolled_back = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self.rollback()

    def commit(self) -> None:
        self.ledger.commit()
        self.committed = True

    def rollback(self) -> None:
        self.ledger.rollback()
        self.rolled_back = True


class FakeRunReviewUnitOfWork:
    """An admin decision: the run, its points, and the audit row in one transaction."""

    def __init__(
        self,
        *,
        members: FakeMemberRepository,
        runs: FakeRunRepository,
        campaigns: FakeCampaignRepository,
        ledger: FakePointsLedgerRepository,
        audit: FakeAuditRepository,
        clock: FixedClock,
    ) -> None:
        self.members = members
        self.runs = runs
        self.campaigns = campaigns
        self.ledger = ledger
        self.audit = audit
        self.clock = clock
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeRunReviewUnitOfWork:
        self.committed = False
        self.rolled_back = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self.rollback()

    def commit(self) -> None:
        self.ledger.commit()
        self.audit.commit()
        self.committed = True

    def rollback(self) -> None:
        self.ledger.rollback()
        self.audit.rollback()
        self.rolled_back = True


class FakeAdminUnitOfWork:
    """A superuser mutation: the change and its audit row commit together."""

    def __init__(
        self,
        *,
        members: FakeMemberRepository,
        campaigns: FakeCampaignRepository,
        rewards: FakeRewardRepository,
        redemptions: FakeRedemptionRepository,
        ledger: FakePointsLedgerRepository,
        runs: FakeRunRepository,
        audit: FakeAuditRepository,
        clock: FixedClock,
    ) -> None:
        self.members = members
        self.campaigns = campaigns
        self.rewards = rewards
        self.redemptions = redemptions
        self.ledger = ledger
        self.runs = runs
        self.audit = audit
        self.clock = clock
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeAdminUnitOfWork:
        self.committed = False
        self.rolled_back = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self.rollback()

    def commit(self) -> None:
        self.ledger.commit()
        self.rewards.commit()
        self.redemptions.commit()
        self.audit.commit()
        self.committed = True

    def rollback(self) -> None:
        self.ledger.rollback()
        self.rewards.rollback()
        self.redemptions.rollback()
        self.audit.rollback()
        self.rolled_back = True
