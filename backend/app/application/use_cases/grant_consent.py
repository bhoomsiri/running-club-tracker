"""Record that a member agreed to the current consent wording.

Re-granting is normal, not an error: when the wording is superseded every member is
asked again. The old agreement is withdrawn rather than overwritten, so the record of
what was agreed to, and until when, survives.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.clock import Clock
from app.application.ports.consent_repository import ConsentRepository
from app.domain.consent import Consent, ConsentPurpose


@dataclass(frozen=True)
class GrantConsentCommand:
    member_id: UUID  # from the verified token, never from the request body
    purpose: ConsentPurpose = ConsentPurpose.HEALTH_DATA


class GrantConsent:
    def __init__(self, consents: ConsentRepository, clock: Clock, consent_version: str) -> None:
        self._consents = consents
        self._clock = clock
        self._version = consent_version

    def execute(self, cmd: GrantConsentCommand) -> Consent:
        now = self._clock.now()
        existing = self._consents.get_current(cmd.member_id, cmd.purpose)

        if existing is not None:
            if existing.is_active(self._version):
                return existing  # already agreed to the wording in force
            # An agreement to superseded wording: close it before opening the new one,
            # or the "one active consent per purpose" index would reject the insert.
            self._consents.save(existing.withdraw(now))

        granted = Consent.grant(
            member_id=cmd.member_id, purpose=cmd.purpose, version=self._version, now=now
        )
        self._consents.add(granted)
        return granted
