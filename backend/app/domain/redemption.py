"""Rewards, redemptions, and ledger entries — the money-like side of the app.

Every number here is a Decimal. A points balance is always SUM(delta) over the ledger;
nothing in this module caches one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.errors import (
    InvalidLedgerEntry,
    OutOfStock,
    RewardUnavailable,
)

POINTS = Decimal("0.01")


class RedemptionStatus(StrEnum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class LedgerReason(StrEnum):
    RUN_EARNED = "run_earned"
    REDEEMED = "redeemed"
    ADJUSTMENT = "adjustment"
    REVERSAL = "reversal"


@dataclass(frozen=True)
class Reward:
    id: UUID
    campaign_id: UUID
    name: str
    points_cost: Decimal
    stock: int
    is_active: bool

    def ensure_redeemable(self) -> None:
        """Rules that don't depend on who is redeeming. The balance check lives in the
        use case, because it needs the ledger."""
        if not self.is_active:
            raise RewardUnavailable(f"reward {self.name!r} is not available")
        if self.stock <= 0:
            raise OutOfStock(f"reward {self.name!r} is out of stock")


@dataclass(frozen=True)
class Redemption:
    id: UUID
    member_id: UUID
    reward_id: UUID
    campaign_id: UUID
    points_spent: Decimal
    status: RedemptionStatus
    created_at: datetime

    @classmethod
    def create(cls, *, member_id: UUID, reward: Reward, now: datetime) -> Redemption:
        reward.ensure_redeemable()
        return cls(
            id=uuid4(),
            member_id=member_id,
            reward_id=reward.id,
            campaign_id=reward.campaign_id,
            # Snapshot: the catalogue price may change after this redemption.
            points_spent=reward.points_cost.quantize(POINTS),
            status=RedemptionStatus.PENDING,
            created_at=now,
        )


@dataclass(frozen=True)
class PointsEntry:
    """One append-only ledger row. `delta` is signed: positive earns, negative spends."""

    id: UUID
    member_id: UUID
    campaign_id: UUID
    delta: Decimal
    reason: LedgerReason
    run_entry_id: UUID | None
    redemption_id: UUID | None
    created_at: datetime

    def __post_init__(self) -> None:
        # Mirrors the ck_points_ledger_ref_matches_reason CHECK, so an entry the domain
        # accepts is always one the database will accept.
        if self.reason is LedgerReason.RUN_EARNED:
            if self.run_entry_id is None or self.redemption_id is not None:
                raise InvalidLedgerEntry("run_earned must reference exactly a run")
        elif self.reason is LedgerReason.REDEEMED:
            if self.redemption_id is None or self.run_entry_id is not None:
                raise InvalidLedgerEntry("redeemed must reference exactly a redemption")
        elif self.run_entry_id is not None and self.redemption_id is not None:
            raise InvalidLedgerEntry(f"{self.reason} cannot reference both a run and a redemption")

    @classmethod
    def for_run(
        cls, *, member_id: UUID, campaign_id: UUID, points: Decimal, run_entry_id: UUID,
        now: datetime,
    ) -> PointsEntry:
        if points <= 0:
            raise InvalidLedgerEntry("earned points must be positive")
        return cls(
            id=uuid4(),
            member_id=member_id,
            campaign_id=campaign_id,
            delta=points.quantize(POINTS),
            reason=LedgerReason.RUN_EARNED,
            run_entry_id=run_entry_id,
            redemption_id=None,
            created_at=now,
        )

    @classmethod
    def reversal(
        cls, *, member_id: UUID, campaign_id: UUID, points: Decimal, run_entry_id: UUID,
        now: datetime,
    ) -> PointsEntry:
        """Take back points that were awarded and are no longer earned — a rejected run,
        or a day that fell below its threshold once one of its runs was rejected."""
        if points <= 0:
            raise InvalidLedgerEntry("reversed points must be positive")
        return cls(
            id=uuid4(),
            member_id=member_id,
            campaign_id=campaign_id,
            delta=-points.quantize(POINTS),
            reason=LedgerReason.REVERSAL,
            run_entry_id=run_entry_id,
            redemption_id=None,
            created_at=now,
        )

    @classmethod
    def refund_of(cls, *, redemption: Redemption, now: datetime) -> PointsEntry:
        """Give the points back when a redemption is cancelled.

        References the redemption, not a run, so `credited_total` (which only counts
        earning rows — those tied to a run) is unaffected and reconciliation cannot
        mistake a refund for something the member earned.
        """
        return cls(
            id=uuid4(),
            member_id=redemption.member_id,
            campaign_id=redemption.campaign_id,
            delta=redemption.points_spent,
            reason=LedgerReason.REVERSAL,
            run_entry_id=None,
            redemption_id=redemption.id,
            created_at=now,
        )

    @classmethod
    def for_redemption(cls, *, redemption: Redemption, now: datetime) -> PointsEntry:
        return cls(
            id=uuid4(),
            member_id=redemption.member_id,
            campaign_id=redemption.campaign_id,
            delta=-redemption.points_spent,  # spending is a negative row, never an update
            reason=LedgerReason.REDEEMED,
            run_entry_id=None,
            redemption_id=redemption.id,
            created_at=now,
        )
