from __future__ import annotations

import hashlib
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import points_entry_to_orm
from app.domain.redemption import PointsEntry


def advisory_key(member_id: UUID, campaign_id: UUID) -> int:
    """Fold two UUIDs into the single bigint pg_advisory_xact_lock takes.

    blake2b, not Python's hash(): built-in string/bytes hashing is randomised per
    process, so two workers would compute different keys for the same account and
    would not block each other at all.
    """
    digest = hashlib.blake2b(member_id.bytes + campaign_id.bytes, digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


class SqlAlchemyPointsLedgerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def serialize_account(self, member_id: UUID, campaign_id: UUID) -> None:
        # pg_advisory_XACT_lock, not pg_advisory_lock: it is released automatically when
        # the transaction commits or rolls back, so a crashed request cannot strand a
        # member's account in a permanently locked state.
        self._session.execute(
            sa.text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": advisory_key(member_id, campaign_id)},
        )

    def balance(self, member_id: UUID, campaign_id: UUID) -> Decimal:
        total = self._session.execute(
            sa.select(sa.func.coalesce(sa.func.sum(models.PointsLedger.delta), 0)).where(
                models.PointsLedger.member_id == member_id,
                models.PointsLedger.campaign_id == campaign_id,
            )
        ).scalar_one()
        return Decimal(total)

    def balances_for_campaign(self, campaign_id: UUID) -> dict[UUID, Decimal]:
        rows = self._session.execute(
            sa.select(
                models.PointsLedger.member_id,
                sa.func.coalesce(sa.func.sum(models.PointsLedger.delta), 0),
            )
            .where(models.PointsLedger.campaign_id == campaign_id)
            .group_by(models.PointsLedger.member_id)
        ).all()
        return {member_id: Decimal(total) for member_id, total in rows}

    def credited_total(self, member_id: UUID, campaign_id: UUID) -> Decimal:
        total = self._session.execute(
            sa.select(sa.func.coalesce(sa.func.sum(models.PointsLedger.delta), 0)).where(
                models.PointsLedger.member_id == member_id,
                models.PointsLedger.campaign_id == campaign_id,
                models.PointsLedger.reason.in_(("run_earned", "reversal")),
                # Earning rows are the ones tied to a run. A cancelled redemption's
                # refund is also a 'reversal' but references the redemption, and it is
                # NOT something the member earned.
                models.PointsLedger.run_entry_id.is_not(None),
            )
        ).scalar_one()
        return Decimal(total)

    def has_entries_for_campaign(self, campaign_id: UUID) -> bool:
        return (
            self._session.execute(
                sa.select(sa.literal(1))
                .select_from(models.PointsLedger)
                .where(models.PointsLedger.campaign_id == campaign_id)
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    def add(self, entry: PointsEntry) -> None:
        self._session.add(points_entry_to_orm(entry))
        # Flushed immediately so the idempotency indexes (one credit per run, one charge
        # per redemption) reject a duplicate here rather than at commit time.
        self._session.flush()
