"""Withdraw consent (PDPA right to withdraw).

Withdrawal stops processing; it does not delete. From this moment health data cannot be
written, and admins cannot read this member's health data — but the member keeps access
to their own records, and the data itself ages out under its retention window, or goes
sooner if they make a separate erasure request.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.clock import Clock
from app.application.ports.consent_repository import ConsentRepository
from app.domain.consent import Consent, ConsentPurpose


@dataclass(frozen=True)
class WithdrawConsentCommand:
    member_id: UUID  # from the verified token, never from the request body
    purpose: ConsentPurpose = ConsentPurpose.HEALTH_DATA


class WithdrawConsent:
    def __init__(self, consents: ConsentRepository, clock: Clock) -> None:
        self._consents = consents
        self._clock = clock

    def execute(self, cmd: WithdrawConsentCommand) -> Consent | None:
        existing = self._consents.get_current(cmd.member_id, cmd.purpose)
        if existing is None:
            # Nothing to withdraw. Idempotent on purpose: a member pressing the button
            # twice has got what they asked for, and shouldn't see an error.
            return None

        withdrawn = existing.withdraw(self._clock.now())
        self._consents.save(withdrawn)
        return withdrawn
