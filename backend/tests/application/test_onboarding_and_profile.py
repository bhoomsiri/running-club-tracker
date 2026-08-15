"""The onboarding gate, and the profile it asks for.

The gate decides whether a member may use the app at all, so what it counts as done —
and who it exempts — matters more than most rules here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.use_cases.get_onboarding_status import (
    BASELINE,
    CONSENT,
    PROFILE,
    SCREENING,
    GetOnboardingStatus,
)
from app.application.use_cases.update_my_profile import (
    UpdateMyProfile,
    UpdateMyProfileCommand,
)
from app.domain.consent import Consent, ConsentPurpose
from app.domain.entities import Member, MemberRole, Sex
from app.domain.errors import InvalidMemberError
from app.domain.health import HealthPhase, HealthRecord
from app.domain.screening import QUESTION_KEYS, Screening
from tests.fakes.fake_health_uow import ImmediateConsentRepository
from tests.fakes.fake_uow import FixedClock
from tests.fakes.repositories import (
    FakeHealthRepository,
    FakeMemberRepository,
    FakeScreeningRepository,
)

NOW = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)
CAMPAIGN = UUID("11111111-1111-1111-1111-111111111111")
VERSION = "v2"

PROFILE_FIELDS = {
    "full_name_th": "สมชาย ใจดี",
    "birth_year": 1990,
    "sex": Sex.MALE,
    "phone": "081-234-5678",
    "emergency_contact_name": "สมหญิง ใจดี",
    "emergency_contact_phone": "0898765432",
}


def member(role: MemberRole = MemberRole.MEMBER) -> Member:
    return Member.create(
        clerk_user_id=f"user_{role.value}", display_name="Somchai", now=NOW, role=role
    )


def consent(version: str = VERSION) -> Consent:
    return Consent.grant(
        member_id=UUID(int=0), purpose=ConsentPurpose.HEALTH_DATA, version=version, now=NOW
    )


def screening(member_id: UUID) -> Screening:
    return Screening.create(
        member_id=member_id,
        answers=dict.fromkeys(QUESTION_KEYS, False),
        risk_acknowledged=True,
        screened_on=date(2026, 8, 16),
        now=NOW,
    )


def baseline(member_id: UUID, *, weight: Decimal | None, height: Decimal | None) -> HealthRecord:
    return HealthRecord.create(
        member_id=member_id,
        campaign_id=CAMPAIGN,
        phase=HealthPhase.BEFORE,
        measured_on=date(2026, 8, 16),
        campaign_ends_on=date(2026, 9, 30),
        retention_days=730,
        now=NOW,
        weight_kg=weight,
        height_cm=height,
    )


def build_status(
    subject: Member,
    *,
    consented: bool = False,
    screened: bool = False,
    baseline_record: HealthRecord | None = None,
) -> GetOnboardingStatus:
    granted = [
        Consent.grant(
            member_id=subject.id,
            purpose=ConsentPurpose.HEALTH_DATA,
            version=VERSION,
            now=NOW,
        )
    ]
    return GetOnboardingStatus(
        members=FakeMemberRepository([subject]),
        consents=ImmediateConsentRepository(granted if consented else []),
        screenings=FakeScreeningRepository([screening(subject.id)] if screened else []),
        health=FakeHealthRepository([baseline_record] if baseline_record else []),
        consent_version=VERSION,
    )


class TestOnboardingStatus:
    def test_a_brand_new_member_is_missing_everything(self) -> None:
        subject = member()

        status = build_status(subject).execute(subject.id)

        assert status.complete is False
        assert status.missing == [CONSENT, PROFILE, SCREENING, BASELINE]

    def test_the_steps_come_back_in_the_order_the_wizard_asks_them(self) -> None:
        """So a client can send the member straight to the first thing outstanding."""
        subject = member()

        missing = build_status(subject).execute(subject.id).missing

        assert missing.index(CONSENT) < missing.index(PROFILE) < missing.index(SCREENING)

    def test_everything_done_is_complete(self) -> None:
        subject = member().with_profile(_complete_profile())

        status = build_status(
            subject,
            consented=True,
            screened=True,
            baseline_record=baseline(
                subject.id, weight=Decimal("62"), height=Decimal("170")
            ),
        ).execute(subject.id)

        assert status.complete is True
        assert status.missing == []

    def test_a_half_filled_profile_does_not_count(self) -> None:
        """An emergency contact with no phone number is not an emergency contact."""
        subject = member().with_profile(_complete_profile(emergency_contact_phone=None))

        assert PROFILE in build_status(subject).execute(subject.id).missing

    def test_a_baseline_without_height_does_not_count(self) -> None:
        """Weight alone yields no BMI, so there would be nothing to compare against —
        and by the time anyone notices, the moment to measure has passed."""
        subject = member().with_profile(_complete_profile())

        status = build_status(
            subject,
            consented=True,
            screened=True,
            baseline_record=baseline(subject.id, weight=Decimal("62"), height=None),
        ).execute(subject.id)

        assert BASELINE in status.missing

    def test_consent_to_superseded_wording_does_not_count(self) -> None:
        subject = member()
        use_case = GetOnboardingStatus(
            members=FakeMemberRepository([subject]),
            consents=ImmediateConsentRepository(
                [
                    Consent.grant(
                        member_id=subject.id,
                        purpose=ConsentPurpose.HEALTH_DATA,
                        version="v1-old",
                        now=NOW,
                    )
                ]
            ),
            screenings=FakeScreeningRepository(),
            health=FakeHealthRepository(),
            consent_version=VERSION,
        )

        assert CONSENT in use_case.execute(subject.id).missing

    def test_the_superuser_is_exempt(self) -> None:
        """Somebody has to be able to reach the admin screens on a fresh deployment, and
        that person cannot be locked out by a gate they are there to configure."""
        boss = member(MemberRole.SUPERUSER)

        status = build_status(boss).execute(boss.id)

        assert status.complete is True
        assert status.missing == []

    def test_an_admin_is_not_exempt(self) -> None:
        """Admins run alongside everyone else — the exemption is a bootstrap, not a
        privilege."""
        admin = member(MemberRole.ADMIN)

        assert build_status(admin).execute(admin.id).complete is False


class TestUpdateMyProfile:
    def build(self, subject: Member) -> tuple[UpdateMyProfile, FakeMemberRepository]:
        members = FakeMemberRepository([subject])
        return UpdateMyProfile(members, FixedClock(NOW)), members

    def test_it_stores_the_profile(self) -> None:
        subject = member()
        use_case, members = self.build(subject)

        updated = use_case.execute(UpdateMyProfileCommand(member_id=subject.id, **PROFILE_FIELDS))  # type: ignore[arg-type]

        assert updated.profile.is_complete
        stored = members.get(subject.id)
        assert stored is not None
        assert stored.profile.full_name_th == "สมชาย ใจดี"

    def test_a_phone_number_is_stored_as_digits(self) -> None:
        """So the same number typed three ways is one number, and an emergency contact
        that cannot be dialled never looks like one that can."""
        subject = member()
        use_case, _ = self.build(subject)

        updated = use_case.execute(UpdateMyProfileCommand(member_id=subject.id, **PROFILE_FIELDS))  # type: ignore[arg-type]

        assert updated.profile.phone == "0812345678"

    def test_a_malformed_phone_is_refused(self) -> None:
        subject = member()
        use_case, _ = self.build(subject)

        with pytest.raises(InvalidMemberError, match="phone"):
            use_case.execute(
                UpdateMyProfileCommand(
                    member_id=subject.id, **{**PROFILE_FIELDS, "phone": "12345"}  # type: ignore[arg-type]
                )
            )

    def test_this_years_birth_year_is_refused(self) -> None:
        """Catches the current year typed where a birth year was meant."""
        subject = member()
        use_case, _ = self.build(subject)

        with pytest.raises(InvalidMemberError, match="birth_year"):
            use_case.execute(
                UpdateMyProfileCommand(
                    member_id=subject.id, **{**PROFILE_FIELDS, "birth_year": 2026}  # type: ignore[arg-type]
                )
            )

    def test_updating_a_profile_never_touches_the_role(self) -> None:
        """There is no field for it on the command, and this pins that: the profile
        endpoint must not become a way to promote yourself."""
        subject = member(MemberRole.ADMIN)
        use_case, members = self.build(subject)

        use_case.execute(UpdateMyProfileCommand(member_id=subject.id, **PROFILE_FIELDS))  # type: ignore[arg-type]

        stored = members.get(subject.id)
        assert stored is not None
        assert stored.role is MemberRole.ADMIN

    def test_the_thai_name_becomes_the_name_shown(self) -> None:
        subject = member()
        use_case, _ = self.build(subject)

        assert subject.preferred_name == "Somchai"
        updated = use_case.execute(UpdateMyProfileCommand(member_id=subject.id, **PROFILE_FIELDS))  # type: ignore[arg-type]
        assert updated.preferred_name == "สมชาย ใจดี"


def _complete_profile(**overrides: object):  # type: ignore[no-untyped-def]
    from app.domain.entities import MemberProfile

    fields = {
        "full_name_th": "สมชาย ใจดี",
        "birth_year": 1990,
        "sex": Sex.MALE,
        "phone": "0812345678",
        "emergency_contact_name": "สมหญิง ใจดี",
        "emergency_contact_phone": "0898765432",
    }
    fields.update(overrides)
    return MemberProfile(**fields)  # type: ignore[arg-type]
