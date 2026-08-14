"""Superuser edits to the club's activities.

Two rules that exist to protect history rather than to protect the database:

  - **A campaign's type is never changed once anything depends on it.** Type decides
    which policy reads the runs, so switching it would silently re-interpret months of
    submissions — the same runs suddenly meaning different points. If the format is
    genuinely different, it is a different campaign.
  - **Config is validated against the policy's declared requirements** at write time.
    A campaign missing `target_km` is not a broken screen later; it is refused now.

Every change is audited: accountability for a mutation doesn't depend on how sensitive
the data was to read.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from typing import Any
from uuid import UUID

from app.application.ports.admin_unit_of_work import AdminUnitOfWork
from app.domain.audit import AuditAction, AuditEntry
from app.domain.campaign import Campaign, CampaignType, validate_config_for
from app.domain.entities import Member
from app.domain.errors import (
    CampaignNotFound,
    InvalidCampaignError,
    MemberNotFound,
    NotAuthorized,
)


@dataclass(frozen=True)
class CreateCampaignCommand:
    actor_id: UUID
    code: str
    name: str
    type: CampaignType
    starts_on: date
    ends_on: date
    config: dict[str, Any]


@dataclass(frozen=True)
class UpdateCampaignCommand:
    actor_id: UUID
    campaign_id: UUID
    # Only what may change. `type` and `code` are deliberately absent.
    name: str | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    config: dict[str, Any] | None = None
    is_active: bool | None = None


def _require_superuser(uow: AdminUnitOfWork, actor_id: UUID) -> Member:
    actor = uow.members.get(actor_id)
    if actor is None:
        raise MemberNotFound(str(actor_id))
    if not actor.role.may_edit_records:
        raise NotAuthorized("superuser only")
    return actor


class CreateCampaign:
    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: CreateCampaignCommand) -> Campaign:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            if uow.campaigns.get_by_code(cmd.code) is not None:
                raise InvalidCampaignError(f"campaign code {cmd.code!r} is already used")

            campaign = Campaign.create(
                code=cmd.code,
                name=cmd.name,
                type=cmd.type,
                starts_on=cmd.starts_on,
                ends_on=cmd.ends_on,
                config=cmd.config,
            )
            # The policy says which keys it needs; a bad config is refused here.
            validate_config_for(campaign)

            uow.campaigns.add(campaign)
            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.CREATE_CAMPAIGN,
                    now=uow.clock.now(),
                    detail={"campaign_id": campaign.id, "code": campaign.code},
                )
            )
            uow.commit()
        return campaign


class UpdateCampaign:
    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: UpdateCampaignCommand) -> Campaign:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            campaign = uow.campaigns.get(cmd.campaign_id)
            if campaign is None:
                raise CampaignNotFound(str(cmd.campaign_id))

            updated = replace(
                campaign,
                name=cmd.name if cmd.name is not None else campaign.name,
                starts_on=cmd.starts_on or campaign.starts_on,
                ends_on=cmd.ends_on or campaign.ends_on,
                config=cmd.config if cmd.config is not None else campaign.config,
                is_active=cmd.is_active if cmd.is_active is not None else campaign.is_active,
            )
            if updated.ends_on < updated.starts_on:
                raise InvalidCampaignError("ends_on cannot be before starts_on")
            validate_config_for(updated)

            # Narrowing the window after people have run is how a member loses points
            # they were told they had, so it is refused once the campaign has history.
            if (updated.starts_on, updated.ends_on) != (campaign.starts_on, campaign.ends_on):
                self._refuse_if_it_has_history(uow, campaign, "dates")

            uow.campaigns.save(updated)
            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.UPDATE_CAMPAIGN,
                    now=uow.clock.now(),
                    detail={"campaign_id": campaign.id, "code": campaign.code},
                )
            )
            uow.commit()
        return updated

    def _refuse_if_it_has_history(
        self, uow: AdminUnitOfWork, campaign: Campaign, what: str
    ) -> None:
        if uow.ledger.has_entries_for_campaign(campaign.id):
            raise InvalidCampaignError(
                f"cannot change {what}: points have already been awarded in this campaign"
            )
        if uow.runs.count_in_window(campaign.starts_on, campaign.ends_on) > 0:
            raise InvalidCampaignError(
                f"cannot change {what}: runs have already been submitted in this window"
            )
