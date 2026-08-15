"""A member recording their own pre-exercise screening — behind the consent gate.

The gate is here rather than at the router for the same reason it is in
`save_health_record`: these answers are sensitive personal data under PDPA, the club
needs a lawful basis to hold them, and that basis must not depend on which caller
happens to reach the use case.

Answering again replaces the previous record. What the club needs to know is what is
true now, and keeping every past draft of someone's cardiac history would be a liability
rather than an asset.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.application.ports.clock import Clock
from app.application.ports.consent_repository import ConsentRepository
from app.application.ports.screening_repository import ScreeningRepository
from app.domain.consent import ConsentPurpose
from app.domain.errors import ConsentRequired
from app.domain.screening import Screening


@dataclass(frozen=True)
class SaveMyScreeningCommand:
    member_id: UUID  # from the verified token, never from the request body
    answers: dict[str, bool]
    risk_acknowledged: bool
    screened_on: date


class SaveMyScreening:
    def __init__(
        self,
        consents: ConsentRepository,
        screenings: ScreeningRepository,
        clock: Clock,
        consent_version: str,
    ) -> None:
        self._consents = consents
        self._screenings = screenings
        self._clock = clock
        self._consent_version = consent_version

    def execute(self, cmd: SaveMyScreeningCommand) -> Screening:
        consent = self._consents.get_current(cmd.member_id, ConsentPurpose.HEALTH_DATA)
        if consent is None or not consent.is_active(self._consent_version):
            raise ConsentRequired("active consent for health_data is required")

        screening = Screening.create(
            member_id=cmd.member_id,
            answers=cmd.answers,
            risk_acknowledged=cmd.risk_acknowledged,
            screened_on=cmd.screened_on,
            now=self._clock.now(),
            # Keeps the row's id and created_at when this is a revision.
            existing=self._screenings.get_for_member(cmd.member_id),
        )
        return self._screenings.upsert(screening)
