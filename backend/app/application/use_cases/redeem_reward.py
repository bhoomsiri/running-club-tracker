"""Spend points on a reward.

This touches money-like state, so the whole sequence runs inside ONE transaction:

    lock the reward row -> check stock -> check balance -> insert redemption
    -> insert the negative ledger row -> decrement stock -> commit

The lock is what makes two concurrent redeems serialise; the balance check and the
negative ledger row share a transaction so they cannot interleave and double-spend.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.unit_of_work import UnitOfWork
from app.domain.errors import InsufficientPoints, RewardUnavailable
from app.domain.redemption import PointsEntry, Redemption


@dataclass(frozen=True)
class RedeemRewardCommand:
    member_id: UUID  # from the verified token, never from the request body
    reward_id: UUID


class RedeemReward:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: RedeemRewardCommand) -> Redemption:
        with self._uow as uow:
            reward = uow.rewards.get_for_update(cmd.reward_id)
            if reward is None:
                raise RewardUnavailable(f"reward {cmd.reward_id} does not exist")

            # Raises OutOfStock / RewardUnavailable before any write happens.
            reward.ensure_redeemable()

            # Take the account for the rest of the transaction BEFORE reading the
            # balance. The reward row lock above only serialises redeems of the SAME
            # reward; two different rewards charged to the same account would otherwise
            # both read the old balance and both insert a negative row.
            uow.ledger.serialize_account(cmd.member_id, reward.campaign_id)

            balance = uow.ledger.balance(cmd.member_id, reward.campaign_id)
            if balance < reward.points_cost:
                raise InsufficientPoints(
                    f"balance {balance} is below the cost {reward.points_cost}"
                )

            now = uow.clock.now()
            redemption = Redemption.create(member_id=cmd.member_id, reward=reward, now=now)
            uow.redemptions.add(redemption)
            uow.ledger.add(PointsEntry.for_redemption(redemption=redemption, now=now))
            uow.rewards.decrement_stock(reward.id)

            uow.commit()
        return redemption
