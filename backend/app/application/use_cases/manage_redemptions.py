"""Handing over a reward, or putting it back.

`FulfillRedemption` is the real gate. Redeeming is optimistic — it happens the moment a
member taps, on points that may still be under review — so the check that matters is the
one made when the physical item changes hands:

  - the member's balance must not be negative. A rejected run can pull it below zero
    after the fact, and this is where that surfaces;
  - the member must have no run still flagged and awaiting a decision. Handing over a
    shirt on points that are still in question is the thing that cannot be undone.

Neither check needs a separate "hold" mechanism: a redemption that doesn't pass simply
stays `pending` until the balance clears or the superuser cancels it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.application.ports.admin_unit_of_work import AdminUnitOfWork
from app.application.use_cases.manage_campaigns import _require_superuser
from app.domain.audit import AuditAction, AuditEntry
from app.domain.errors import (
    InsufficientPoints,
    RedemptionNotFound,
    RedemptionNotPending,
    UnresolvedRuns,
)
from app.domain.redemption import PointsEntry, Redemption, RedemptionStatus


@dataclass(frozen=True)
class RedemptionCommand:
    actor_id: UUID
    redemption_id: UUID


class FulfillRedemption:
    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: RedemptionCommand) -> Redemption:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            redemption = uow.redemptions.get(cmd.redemption_id)
            if redemption is None:
                raise RedemptionNotFound(str(cmd.redemption_id))
            if redemption.status is not RedemptionStatus.PENDING:
                raise RedemptionNotPending(f"redemption is already {redemption.status.value}")

            # Reading the balance means taking the account lock first, like every other
            # caller (CLAUDE.md rule #5) — a concurrent redeem must not slip between the
            # check and the decision.
            uow.ledger.serialize_account(redemption.member_id, redemption.campaign_id)
            balance = uow.ledger.balance(redemption.member_id, redemption.campaign_id)
            if balance < 0:
                raise InsufficientPoints(
                    f"balance is {balance}: a rejected run has taken it below zero"
                )
            if uow.runs.has_flagged(redemption.member_id):
                raise UnresolvedRuns(
                    "this member has a run awaiting review; resolve it before handing over"
                )

            uow.redemptions.set_status(redemption.id, RedemptionStatus.FULFILLED)
            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.FULFILL_REDEMPTION,
                    subject_member_id=redemption.member_id,
                    now=uow.clock.now(),
                    detail={"redemption_id": redemption.id},
                )
            )
            uow.commit()

        return Redemption(
            id=redemption.id,
            member_id=redemption.member_id,
            reward_id=redemption.reward_id,
            campaign_id=redemption.campaign_id,
            points_spent=redemption.points_spent,
            status=RedemptionStatus.FULFILLED,
            created_at=redemption.created_at,
        )


class CancelRedemption:
    """Undo a redemption that will not be handed over: points back, item back on the
    shelf. Everything moves together or not at all."""

    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: RedemptionCommand) -> Redemption:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            redemption = uow.redemptions.get(cmd.redemption_id)
            if redemption is None:
                raise RedemptionNotFound(str(cmd.redemption_id))
            if redemption.status is not RedemptionStatus.PENDING:
                raise RedemptionNotPending(f"redemption is already {redemption.status.value}")

            now = uow.clock.now()
            # Lock order is reward row -> account, the same order redeem_reward uses.
            # Taking them the other way round here would deadlock against a concurrent
            # redemption of this reward (CLAUDE.md rule #5).
            uow.rewards.get_for_update(redemption.reward_id)
            uow.ledger.serialize_account(redemption.member_id, redemption.campaign_id)
            # A refund references the redemption, not a run, so reconciliation cannot
            # mistake it for something the member earned.
            uow.ledger.add(PointsEntry.refund_of(redemption=redemption, now=now))
            uow.rewards.increment_stock(redemption.reward_id)
            uow.redemptions.set_status(redemption.id, RedemptionStatus.CANCELLED)

            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.CANCEL_REDEMPTION,
                    subject_member_id=redemption.member_id,
                    now=now,
                    detail={"redemption_id": redemption.id},
                )
            )
            uow.commit()

        return Redemption(
            id=redemption.id,
            member_id=redemption.member_id,
            reward_id=redemption.reward_id,
            campaign_id=redemption.campaign_id,
            points_spent=redemption.points_spent,
            status=RedemptionStatus.CANCELLED,
            created_at=redemption.created_at,
        )


def refunded_total(entries: list[PointsEntry]) -> Decimal:
    """Helper for tests and reporting: how much has been refunded."""
    return sum(
        (e.delta for e in entries if e.redemption_id is not None and e.delta > 0),
        start=Decimal("0"),
    )
