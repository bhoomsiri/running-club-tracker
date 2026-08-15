"""What a member still has to do before the club will let them start.

Four things, and the reason each is required is different:

  - consent, because everything after it is sensitive personal data and the club has no
    lawful basis to hold any of it without one;
  - profile, because someone has to be reachable if a member collapses on a run;
  - screening, because the club should know before the first session whether a member
    ought to see a doctor first;
  - a baseline weight and height, because a before/after comparison with no "before" is
    not a comparison — and by the time anyone notices, the moment to take it has passed.

The superuser is exempt. Somebody has to be able to reach the admin screens on a fresh
deployment, and that person cannot be locked out by a gate whose own configuration they
are there to set up. Admins are NOT exempt: they run alongside everyone else.

This reports; it does not enforce. The gate is the frontend redirect, and every
individual write is guarded by its own rule regardless of what this says.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.consent_repository import ConsentRepository
from app.application.ports.health_repository import HealthRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.screening_repository import ScreeningRepository
from app.domain.consent import ConsentPurpose
from app.domain.entities import MemberRole
from app.domain.errors import MemberNotFound
from app.domain.health import HealthPhase

CONSENT = "consent"
PROFILE = "profile"
SCREENING = "screening"
BASELINE = "baseline"


@dataclass(frozen=True)
class OnboardingStatus:
    complete: bool
    missing: list[str]


class GetOnboardingStatus:
    def __init__(
        self,
        members: MemberRepository,
        consents: ConsentRepository,
        screenings: ScreeningRepository,
        health: HealthRepository,
        consent_version: str,
    ) -> None:
        self._members = members
        self._consents = consents
        self._screenings = screenings
        self._health = health
        self._consent_version = consent_version

    def execute(self, member_id: UUID) -> OnboardingStatus:
        member = self._members.get(member_id)
        if member is None:
            raise MemberNotFound(str(member_id))

        if member.role is MemberRole.SUPERUSER:
            return OnboardingStatus(complete=True, missing=[])

        missing = []

        consent = self._consents.get_current(member_id, ConsentPurpose.HEALTH_DATA)
        if consent is None or not consent.is_active(self._consent_version):
            missing.append(CONSENT)

        if not member.profile.is_complete:
            missing.append(PROFILE)

        if self._screenings.get_for_member(member_id) is None:
            missing.append(SCREENING)

        if not self._has_baseline(member_id):
            missing.append(BASELINE)

        # Reported in the order the wizard asks for them, so a client can send the
        # member straight to the first thing outstanding.
        return OnboardingStatus(complete=not missing, missing=missing)

    def _has_baseline(self, member_id: UUID) -> bool:
        """A 'before' record carrying both numbers BMI needs. One without the other is
        not a baseline — it produces no BMI, so there would be nothing to compare to."""
        return any(
            record.phase is HealthPhase.BEFORE
            and record.weight_kg is not None
            and record.height_cm is not None
            for record in self._health.list_by_member(member_id)
        )
