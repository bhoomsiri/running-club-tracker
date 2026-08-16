from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import announcement_to_domain, announcement_to_orm
from app.domain.announcement import Announcement


class SqlAlchemyAnnouncementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_published(self, limit: int | None = None) -> list[Announcement]:
        # The WHERE is the security control, not a display filter: this list is served
        # without a token.
        query = (
            sa.select(models.Announcement)
            .where(models.Announcement.is_published.is_(True))
            .order_by(models.Announcement.created_at.desc())
        )
        if limit is not None:
            query = query.limit(limit)
        return [announcement_to_domain(row) for row in self._session.execute(query).scalars()]

    def list_all(self) -> list[Announcement]:
        rows = self._session.execute(
            sa.select(models.Announcement).order_by(models.Announcement.created_at.desc())
        ).scalars()
        return [announcement_to_domain(row) for row in rows]

    def get(self, announcement_id: UUID) -> Announcement | None:
        row = self._session.get(models.Announcement, announcement_id)
        return announcement_to_domain(row) if row else None

    def add(self, announcement: Announcement) -> None:
        self._session.add(announcement_to_orm(announcement))
        self._session.flush()

    def save(self, announcement: Announcement) -> None:
        self._session.execute(
            sa.update(models.Announcement)
            .where(models.Announcement.id == announcement.id)
            .values(
                title=announcement.title,
                body=announcement.body,
                is_published=announcement.is_published,
                updated_at=announcement.updated_at,
            )
        )
        self._session.flush()
