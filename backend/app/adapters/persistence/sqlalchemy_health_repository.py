from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import health_to_domain, health_to_orm
from app.domain.health import HealthRecord


class SqlAlchemyHealthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, record: HealthRecord) -> HealthRecord:
        existing = self._session.execute(
            sa.select(models.HealthRecord).where(
                models.HealthRecord.member_id == record.member_id,
                models.HealthRecord.campaign_id == record.campaign_id,
                models.HealthRecord.phase == record.phase.value,
            )
        ).scalar_one_or_none()

        if existing is None:
            self._session.add(health_to_orm(record))
            self._session.flush()
            return record

        # Update in place, keeping the original row's id: correcting a measurement is
        # the same record, not a new one (uq_health_record_member_campaign_phase would
        # reject a second row anyway).
        existing.measured_on = record.measured_on
        existing.weight_kg = record.weight_kg
        existing.height_cm = record.height_cm
        existing.resting_hr = record.resting_hr
        existing.systolic = record.systolic
        existing.diastolic = record.diastolic
        existing.retention_until = record.retention_until
        existing.updated_at = record.created_at
        self._session.flush()
        return health_to_domain(existing)

    def list_by_member(self, member_id: UUID) -> list[HealthRecord]:
        rows = self._session.execute(
            sa.select(models.HealthRecord)
            .where(models.HealthRecord.member_id == member_id)
            .order_by(models.HealthRecord.measured_on)
        ).scalars()
        return [health_to_domain(r) for r in rows]
