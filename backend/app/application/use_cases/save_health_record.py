"""Write a member's own before/after health record — behind the consent gate.

The gate is here, in the use case, not in the router: it is a legal obligation, so it
must hold for every caller, including any future admin or import path. The frontend
gates the form too, but that is convenience, not the control.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.clock import Clock
from app.application.ports.consent_repository import ConsentRepository
from app.application.ports.health_repository import HealthRepository
from app.domain.consent import ConsentPurpose
from app.domain.errors import ConsentRequired, InvalidCampaignError
from app.domain.health import HealthPhase, HealthRecord, check_measurement_order


@dataclass(frozen=True)
class SaveHealthRecordCommand:
    member_id: UUID  # from the verified token, never from the request body
    campaign_id: UUID
    phase: HealthPhase
    measured_on: date
    # Every measurement is optional: an unknown value stays None and is never invented.
    weight_kg: Decimal | None = None
    height_cm: Decimal | None = None
    resting_hr: int | None = None
    systolic: int | None = None
    diastolic: int | None = None


class SaveHealthRecord:
    def __init__(
        self,
        consents: ConsentRepository,
        campaigns: CampaignRepository,
        health: HealthRepository,
        clock: Clock,
        consent_version: str,
        retention_days: int,
    ) -> None:
        self._consents = consents
        self._campaigns = campaigns
        self._health = health
        self._clock = clock
        self._consent_version = consent_version
        self._retention_days = retention_days

    def execute(self, cmd: SaveHealthRecordCommand) -> HealthRecord:
        consent = self._consents.get_current(cmd.member_id, ConsentPurpose.HEALTH_DATA)
        # A withdrawn consent, or one given for superseded wording, both count as no
        # consent — the member is asked again before anything is stored.
        if consent is None or not consent.is_active(self._consent_version):
            raise ConsentRequired("active consent for health_data is required")

        campaign = self._campaigns.get(cmd.campaign_id)
        if campaign is None:
            raise InvalidCampaignError(f"campaign {cmd.campaign_id} does not exist")

        record = HealthRecord.create(
            member_id=cmd.member_id,
            campaign_id=campaign.id,
            phase=cmd.phase,
            measured_on=cmd.measured_on,
            campaign_ends_on=campaign.ends_on,
            retention_days=self._retention_days,
            now=self._clock.now(),
            weight_kg=cmd.weight_kg,
            height_cm=cmd.height_cm,
            resting_hr=cmd.resting_hr,
            systolic=cmd.systolic,
            diastolic=cmd.diastolic,
        )
        # The pair has to make sense, and only this layer can see both rows.
        check_measurement_order(record, self._counterpart(record))
        return self._health.upsert(record)

    def _counterpart(self, record: HealthRecord) -> HealthRecord | None:
        """The member's other phase for the same campaign, if they have recorded one."""
        other = (
            HealthPhase.BEFORE if record.phase is HealthPhase.AFTER else HealthPhase.AFTER
        )
        return next(
            (
                existing
                for existing in self._health.list_by_member(record.member_id)
                if existing.campaign_id == record.campaign_id and existing.phase is other
            ),
            None,
        )
