from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import reward_to_domain, reward_to_orm
from app.domain.redemption import Reward


class SqlAlchemyRewardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, reward_id: UUID) -> Reward | None:
        row = self._session.get(models.Reward, reward_id)
        return reward_to_domain(row) if row else None

    def get_for_update(self, reward_id: UUID) -> Reward | None:
        """SELECT ... FOR UPDATE: holds the reward row until the transaction ends, so
        two members redeeming the same reward cannot both see the last item."""
        row = self._session.execute(
            sa.select(models.Reward).where(models.Reward.id == reward_id).with_for_update()
        ).scalar_one_or_none()
        return reward_to_domain(row) if row else None

    def list_for_campaign(self, campaign_id: UUID) -> list[Reward]:
        rows = self._session.execute(
            sa.select(models.Reward)
            .where(models.Reward.campaign_id == campaign_id)
            .order_by(models.Reward.points_cost)
        ).scalars()
        return [reward_to_domain(r) for r in rows]

    def list_active_for_campaign(self, campaign_id: UUID) -> list[Reward]:
        rows = self._session.execute(
            sa.select(models.Reward)
            .where(
                models.Reward.campaign_id == campaign_id,
                models.Reward.is_active.is_(True),
            )
            .order_by(models.Reward.points_cost)
        ).scalars()
        return [reward_to_domain(r) for r in rows]

    def add(self, reward: Reward) -> None:
        self._session.add(reward_to_orm(reward))
        self._session.flush()

    def save(self, reward: Reward) -> None:
        self._session.execute(
            sa.update(models.Reward)
            .where(models.Reward.id == reward.id)
            .values(
                name=reward.name,
                points_cost=reward.points_cost,
                stock=reward.stock,
                is_active=reward.is_active,
            )
        )
        self._session.flush()

    def increment_stock(self, reward_id: UUID) -> None:
        self._session.execute(
            sa.update(models.Reward)
            .where(models.Reward.id == reward_id)
            .values(stock=models.Reward.stock + 1)
        )
        self._session.flush()

    def decrement_stock(self, reward_id: UUID) -> None:
        # Guarded by ck_reward_stock_non_negative as a last resort: if this ever runs
        # without the row lock, the database refuses rather than overselling.
        self._session.execute(
            sa.update(models.Reward)
            .where(models.Reward.id == reward_id)
            .values(stock=models.Reward.stock - 1)
        )
