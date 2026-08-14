"""PDPA consent.

Consent is the legal basis for processing health data, so "do we have it?" is asked in
two different places for two different reasons:

  - before WRITING a health record (the member must have agreed), and
  - before an ADMIN reads someone's health data (their basis for processing it).

The owner reading their own data is a different right entirely (access to one's own
personal data), so it is not gated on consent — withdrawing consent stops the club from
using your data, it does not lock you out of it.

Withdrawal does not delete anything. Erasure is a separate, explicit request; withdrawn
data stops being processed and then ages out under its own retention window.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.errors import InvalidConsentError


class ConsentPurpose(StrEnum):
    HEALTH_DATA = "health_data"


@dataclass(frozen=True)
class Consent:
    id: UUID
    member_id: UUID
    purpose: ConsentPurpose
    # Which wording was agreed to — needed to prove WHAT was consented to, and to
    # invalidate agreements to superseded wording.
    version: str
    granted_at: datetime
    withdrawn_at: datetime | None

    @classmethod
    def grant(
        cls, *, member_id: UUID, purpose: ConsentPurpose, version: str, now: datetime
    ) -> Consent:
        if not version.strip():
            raise InvalidConsentError("consent version is required")
        return cls(
            id=uuid4(),
            member_id=member_id,
            purpose=purpose,
            version=version,
            granted_at=now,
            withdrawn_at=None,
        )

    def is_active(self, current_version: str) -> bool:
        """Active means: not withdrawn AND agreed to the wording currently in force.

        An agreement to superseded wording is not consent to the current terms, so it
        counts as absent — the member is asked again.
        """
        return self.withdrawn_at is None and self.version == current_version

    def withdraw(self, now: datetime) -> Consent:
        if self.withdrawn_at is not None:
            raise InvalidConsentError("consent is already withdrawn")
        if now < self.granted_at:
            raise InvalidConsentError("cannot withdraw before the consent was granted")
        return replace(self, withdrawn_at=now)
