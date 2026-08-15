from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import screening_to_domain, screening_to_orm
from app.domain.screening import Screening


class SqlAlchemyScreeningRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_for_member(self, member_id: UUID) -> Screening | None:
        row = self._session.execute(
            sa.select(models.Screening).where(models.Screening.member_id == member_id)
        ).scalar_one_or_none()
        # member_id is unique, so there is at most one row here.
        return screening_to_domain(row) if row else None

    def upsert(self, screening: Screening) -> Screening:
        existing = self._session.execute(
            sa.select(models.Screening).where(
                models.Screening.member_id == screening.member_id
            )
        ).scalar_one_or_none()

        if existing is None:
            self._session.add(screening_to_orm(screening))
            self._session.flush()
            return screening

        # Updated in place rather than deleted and re-inserted, so the row's identity
        # and created_at survive a member answering again.
        existing.version = screening.version
        existing.answers = dict(screening.answers)
        existing.risk_acknowledged = screening.risk_acknowledged
        existing.screened_on = screening.screened_on
        existing.updated_at = screening.updated_at
        self._session.flush()
        return screening_to_domain(existing)
