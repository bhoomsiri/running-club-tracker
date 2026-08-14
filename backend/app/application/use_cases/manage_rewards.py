"""Superuser edits to the reward catalogue.

A reward that anyone has ever redeemed is never deleted. Retiring it with
`is_active=False` takes it out of the catalogue while leaving every past redemption
readable — deleting it would leave members holding a redemption pointing at nothing, and
the database's ON DELETE RESTRICT would refuse anyway.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from uuid import UUID, uuid4

from app.application.ports.admin_unit_of_work import AdminUnitOfWork
from app.application.use_cases.manage_campaigns import _require_superuser
from app.domain.audit import AuditAction, AuditEntry
from app.domain.errors import CampaignNotFound, InvalidRewardError, RewardUnavailable
from app.domain.redemption import Reward


@dataclass(frozen=True)
class CreateRewardCommand:
    actor_id: UUID
    campaign_id: UUID
    name: str
    points_cost: Decimal
    stock: int


@dataclass(frozen=True)
class UpdateRewardCommand:
    actor_id: UUID
    reward_id: UUID
    name: str | None = None
    points_cost: Decimal | None = None
    stock: int | None = None
    is_active: bool | None = None


class CreateReward:
    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: CreateRewardCommand) -> Reward:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            campaign = uow.campaigns.get(cmd.campaign_id)
            if campaign is None:
                raise CampaignNotFound(str(cmd.campaign_id))
            if cmd.points_cost <= 0:
                raise InvalidRewardError("points_cost must be positive")
            if cmd.stock < 0:
                raise InvalidRewardError("stock cannot be negative")
            if not cmd.name.strip():
                raise InvalidRewardError("name is required")

            reward = Reward(
                id=uuid4(),
                campaign_id=campaign.id,
                name=cmd.name.strip(),
                points_cost=cmd.points_cost,
                stock=cmd.stock,
                is_active=True,
            )
            uow.rewards.add(reward)
            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.CREATE_REWARD,
                    now=uow.clock.now(),
                    detail={"reward_id": reward.id, "campaign_id": campaign.id},
                )
            )
            uow.commit()
        return reward


class UpdateReward:
    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: UpdateRewardCommand) -> Reward:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            reward = uow.rewards.get(cmd.reward_id)
            if reward is None:
                raise RewardUnavailable(f"reward {cmd.reward_id} does not exist")

            updated = replace(
                reward,
                name=cmd.name.strip() if cmd.name is not None else reward.name,
                points_cost=(
                    cmd.points_cost if cmd.points_cost is not None else reward.points_cost
                ),
                stock=cmd.stock if cmd.stock is not None else reward.stock,
                is_active=cmd.is_active if cmd.is_active is not None else reward.is_active,
            )
            if updated.points_cost <= 0:
                raise InvalidRewardError("points_cost must be positive")
            if updated.stock < 0:
                raise InvalidRewardError("stock cannot be negative")
            if not updated.name.strip():
                raise InvalidRewardError("name is required")

            uow.rewards.save(updated)
            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.UPDATE_REWARD,
                    now=uow.clock.now(),
                    detail={
                        "reward_id": reward.id,
                        # Retiring a reward is the supported alternative to deleting one,
                        # so it is worth seeing in the trail.
                        "retired": updated.is_active is False,
                    },
                )
            )
            uow.commit()
        return updated
