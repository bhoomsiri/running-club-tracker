from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import campaign_to_domain, campaign_to_orm
from app.domain.campaign import Campaign


class SqlAlchemyCampaignRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, campaign_id: UUID) -> Campaign | None:
        row = self._session.get(models.Campaign, campaign_id)
        return campaign_to_domain(row) if row else None

    def get_by_code(self, code: str) -> Campaign | None:
        row = self._session.execute(
            sa.select(models.Campaign).where(models.Campaign.code == code)
        ).scalar_one_or_none()
        return campaign_to_domain(row) if row else None

    def list_all(self) -> list[Campaign]:
        rows = self._session.execute(
            sa.select(models.Campaign).order_by(models.Campaign.starts_on)
        ).scalars()
        return [campaign_to_domain(r) for r in rows]

    def add(self, campaign: Campaign) -> None:
        self._session.add(campaign_to_orm(campaign))
        self._session.flush()

    def save(self, campaign: Campaign) -> None:
        self._session.execute(
            sa.update(models.Campaign)
            .where(models.Campaign.id == campaign.id)
            .values(
                name=campaign.name,
                starts_on=campaign.starts_on,
                ends_on=campaign.ends_on,
                config=dict(campaign.config),
                is_active=campaign.is_active,
            )
        )
        self._session.flush()

    def list_active(self) -> list[Campaign]:
        rows = self._session.execute(
            sa.select(models.Campaign)
            .where(models.Campaign.is_active.is_(True))
            .order_by(models.Campaign.starts_on)
        ).scalars()
        return [campaign_to_domain(r) for r in rows]
