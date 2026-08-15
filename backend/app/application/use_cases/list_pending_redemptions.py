"""The queue of rewards waiting to be handed over.

Without this the superuser could fulfil a redemption only by knowing its id, which is
not something anyone knows — the endpoints existed but there was no way to reach them.

Each row says whether it can be handed over yet, and if not, why. The same two checks
`FulfillRedemption` makes, computed here so the answer appears next to the item rather
than as a 409 after pressing the button. The check there is still the control: this is a
read, and the world can move between the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.reward_repository import RewardRepository
from app.application.ports.run_repository import RunRepository
from app.domain.entities import MemberRole
from app.domain.errors import MemberNotFound, NotAuthorized
from app.domain.redemption import Redemption

NEGATIVE_BALANCE = "negative_balance"
UNRESOLVED_RUNS = "unresolved_runs"


@dataclass(frozen=True)
class PendingRedemption:
    redemption: Redemption
    member_name: str
    reward_name: str
    balance: Decimal
    # None when it can be handed over; otherwise which of the two rules is in the way.
    blocked_by: str | None


class ListPendingRedemptions:
    def __init__(
        self,
        members: MemberRepository,
        redemptions: RedemptionRepository,
        rewards: RewardRepository,
        ledger: PointsLedgerRepository,
        runs: RunRepository,
    ) -> None:
        self._members = members
        self._redemptions = redemptions
        self._rewards = rewards
        self._ledger = ledger
        self._runs = runs

    def execute(self, actor_id: UUID) -> list[PendingRedemption]:
        actor = self._members.get(actor_id)
        if actor is None:
            raise MemberNotFound(str(actor_id))
        if actor.role is not MemberRole.SUPERUSER:
            raise NotAuthorized("superuser only")

        rows = []
        for redemption in self._redemptions.list_pending():
            member = self._members.get(redemption.member_id)
            reward = self._rewards.get(redemption.reward_id)
            balance = self._ledger.balance(redemption.member_id, redemption.campaign_id)

            rows.append(
                PendingRedemption(
                    redemption=redemption,
                    # A member awaiting erasure reads as gone; the redemption still
                    # exists and should not vanish from the queue without explanation.
                    member_name=member.preferred_name if member else "(ไม่พบสมาชิก)",
                    reward_name=reward.name if reward else "(ไม่พบของรางวัล)",
                    balance=balance,
                    blocked_by=self._blocked_by(redemption, balance),
                )
            )
        return rows

    def _blocked_by(self, redemption: Redemption, balance: Decimal) -> str | None:
        # Order matters only for which reason is shown first; both are real blocks.
        if balance < 0:
            return NEGATIVE_BALANCE
        if self._runs.has_flagged(redemption.member_id):
            return UNRESOLVED_RUNS
        return None
