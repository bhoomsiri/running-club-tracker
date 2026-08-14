from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import redemption_to_domain, redemption_to_orm
from app.domain.redemption import Redemption, RedemptionStatus


class SqlAlchemyRedemptionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, redemption: Redemption) -> None:
        self._session.add(redemption_to_orm(redemption))
        # Flush now, don't wait for commit. These models declare no relationship(), so
        # SQLAlchemy has no dependency graph to order the INSERTs by — and the ledger
        # row written straight after this one carries an FK to it. Flushing also makes
        # a constraint violation surface here, inside the use case's transaction.
        self._session.flush()

    def get(self, redemption_id: UUID) -> Redemption | None:
        row = self._session.get(models.Redemption, redemption_id)
        return redemption_to_domain(row) if row else None

    def list_pending(self) -> list[Redemption]:
        rows = self._session.execute(
            sa.select(models.Redemption)
            .where(models.Redemption.status == RedemptionStatus.PENDING.value)
            .order_by(models.Redemption.created_at)
        ).scalars()
        return [redemption_to_domain(r) for r in rows]

    def set_status(self, redemption_id: UUID, status: RedemptionStatus) -> None:
        self._session.execute(
            sa.update(models.Redemption)
            .where(models.Redemption.id == redemption_id)
            .values(status=status.value)
        )
        self._session.flush()

    def exists_for_reward(self, reward_id: UUID) -> bool:
        return (
            self._session.execute(
                sa.select(sa.literal(1))
                .select_from(models.Redemption)
                .where(models.Redemption.reward_id == reward_id)
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def list_by_member(self, member_id: UUID) -> list[Redemption]:
        rows = self._session.execute(
            sa.select(models.Redemption)
            .where(models.Redemption.member_id == member_id)
            .order_by(models.Redemption.created_at.desc())
        ).scalars()
        return [redemption_to_domain(r) for r in rows]
