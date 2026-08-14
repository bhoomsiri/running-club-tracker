from __future__ import annotations

from datetime import date
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import run_to_domain, run_to_orm
from app.domain.entities import ReviewStatus, RunEntry


class SqlAlchemyRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: RunEntry) -> None:
        self._session.add(run_to_orm(run))
        # See SqlAlchemyRedemptionRepository.add: insert order is explicit here, because
        # a ledger row crediting this run references it.
        self._session.flush()

    def get(self, run_id: UUID) -> RunEntry | None:
        row = self._session.get(models.RunEntry, run_id)
        return run_to_domain(row) if row else None

    def set_review_status(self, run_id: UUID, status: ReviewStatus) -> None:
        self._session.execute(
            sa.update(models.RunEntry)
            .where(models.RunEntry.id == run_id)
            .values(review_status=status.value)
        )
        self._session.flush()

    def count_in_window(self, start: date, end: date) -> int:
        return int(
            self._session.execute(
                sa.select(sa.func.count())
                .select_from(models.RunEntry)
                .where(models.RunEntry.run_date.between(start, end))
            ).scalar_one()
        )

    def has_flagged(self, member_id: UUID) -> bool:
        return (
            self._session.execute(
                sa.select(sa.literal(1))
                .select_from(models.RunEntry)
                .where(
                    models.RunEntry.member_id == member_id,
                    models.RunEntry.review_status == ReviewStatus.FLAGGED.value,
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def find_by_evidence_hash(self, digest: str) -> list[RunEntry]:
        rows = self._session.execute(
            sa.select(models.RunEntry).where(models.RunEntry.evidence_sha256 == digest)
        ).scalars()
        return [run_to_domain(r) for r in rows]

    def list_by_member(self, member_id: UUID) -> list[RunEntry]:
        rows = self._session.execute(
            sa.select(models.RunEntry)
            .where(models.RunEntry.member_id == member_id)
            .order_by(models.RunEntry.run_date.desc())
        ).scalars()
        return [run_to_domain(r) for r in rows]
