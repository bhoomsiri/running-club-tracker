from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import consent_to_domain, consent_to_orm
from app.domain.consent import Consent, ConsentPurpose


class SqlAlchemyConsentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_current(self, member_id: UUID, purpose: ConsentPurpose) -> Consent | None:
        row = self._session.execute(
            sa.select(models.Consent).where(
                models.Consent.member_id == member_id,
                models.Consent.purpose == purpose.value,
                models.Consent.withdrawn_at.is_(None),
            )
        ).scalar_one_or_none()
        # uq_consent_member_purpose_active guarantees at most one row here.
        return consent_to_domain(row) if row else None

    def add(self, consent: Consent) -> None:
        self._session.add(consent_to_orm(consent))
        self._session.flush()

    def save(self, consent: Consent) -> None:
        self._session.execute(
            sa.update(models.Consent)
            .where(models.Consent.id == consent.id)
            .values(withdrawn_at=consent.withdrawn_at)
        )
        self._session.flush()
