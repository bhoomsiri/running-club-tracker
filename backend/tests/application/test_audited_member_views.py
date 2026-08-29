"""Audited reads of a member's sensitive details.

The rule these enforce is the same one `view_member_health` enforces: an access that
cannot be accounted for must not happen. So the audit row is committed BEFORE the data
is returned, and if that write fails the caller gets nothing.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.view_member_contact import (
    ViewMemberContact,
    ViewMemberContactCommand,
)
from app.application.use_cases.view_member_screening import (
    ViewMemberScreening,
    ViewMemberScreeningCommand,
)
from app.domain.audit import AuditAction
from app.domain.consent import Consent, ConsentPurpose
from app.domain.entities import Member, MemberProfile, MemberRole, Sex
from app.domain.errors import ConsentRequired, MemberNotFound, NotAuthorized
from app.domain.screening import QUESTION_KEYS, Screening
from tests.fakes.fake_audited_view_uows import (
    DEFAULT_NOW,
    FakeContactViewUnitOfWork,
    FakeScreeningViewUnitOfWork,
)
from tests.fakes.fake_health_uow import FakeConsentRepository
from tests.fakes.fake_uow import FakeAuditRepository
from tests.fakes.repositories import FakeMemberRepository, FakeScreeningRepository

NOW = DEFAULT_NOW


def member(role: MemberRole = MemberRole.MEMBER, *, with_profile: bool = False) -> Member:
    built = Member.create(
        clerk_user_id=f"user_{uuid4().hex[:6]}",
        display_name="Somebody",
        now=NOW,
        role=role,
    )
    if not with_profile:
        return built
    return built.with_profile(
        MemberProfile(
            full_name_th="สมชาย ใจดี",
            birth_date=date(1990, 5, 20),
            sex=Sex.MALE,
            phone="0812345678",
            emergency_contact_name="สมหญิง ใจดี",
            emergency_contact_phone="0898765432",
        )
    )


def screening_for(member_id: UUID, *, yes: str | None = None) -> Screening:
    answers = dict.fromkeys(QUESTION_KEYS, False)
    if yes:
        answers[yes] = True
    return Screening.create(
        member_id=member_id,
        answers=answers,
        risk_acknowledged=True,
        screened_on=date(2026, 8, 1),
        now=NOW,
    )


CONSENT_VERSION = "v2"


def consent_for(member_id: UUID, withdrawn: bool = False) -> Consent:
    return Consent(
        id=uuid4(), member_id=member_id, purpose=ConsentPurpose.HEALTH_DATA,
        version=CONSENT_VERSION, granted_at=NOW,
        withdrawn_at=NOW if withdrawn else None,
    )


def uow_with(
    *members_in: Member,
    screenings: list[Screening] | None = None,
    audit: FakeAuditRepository | None = None,
    consents: list[Consent] | None = None,
) -> FakeScreeningViewUnitOfWork:
    """Consent defaults to granted for every member passed in: these tests are about the
    audit trail and the role gate, and spelling it out in each would bury that. The
    consent gate has its own class."""
    return FakeScreeningViewUnitOfWork(
        members=FakeMemberRepository(list(members_in)),
        screenings=FakeScreeningRepository(screenings or []),
        audit=audit,
        consents=FakeConsentRepository(
            consents
            if consents is not None
            else [consent_for(member.id) for member in members_in]
        ),
    )


def contact_uow_with(
    *members_in: Member, audit: FakeAuditRepository | None = None
) -> FakeContactViewUnitOfWork:
    return FakeContactViewUnitOfWork(
        members=FakeMemberRepository(list(members_in)), audit=audit
    )


class TestViewMemberScreening:
    def test_the_superuser_gets_the_answers_and_an_audit_row(self) -> None:
        boss, subject = member(MemberRole.SUPERUSER), member()
        uow = uow_with(boss, subject, screenings=[screening_for(subject.id, yes="diabetes")])

        view = ViewMemberScreening(uow, CONSENT_VERSION).execute(
            ViewMemberScreeningCommand(actor_id=boss.id, subject_id=subject.id)
        )

        assert view.screening is not None
        assert view.screening.needs_medical_advice is True
        entries = uow.audit.committed_entries()
        assert len(entries) == 1
        assert entries[0].action is AuditAction.VIEW_SCREENING
        assert entries[0].actor_member_id == boss.id
        assert entries[0].subject_member_id == subject.id

    def test_the_audit_row_records_no_answers(self) -> None:
        """A log that quotes someone's cardiac history is a second copy of it, in a
        place that is kept longer and read by more people."""
        boss, subject = member(MemberRole.SUPERUSER), member()
        uow = uow_with(
            boss, subject, screenings=[screening_for(subject.id, yes="heart_condition")]
        )

        ViewMemberScreening(uow, CONSENT_VERSION).execute(
            ViewMemberScreeningCommand(actor_id=boss.id, subject_id=subject.id)
        )

        detail = uow.audit.committed_entries()[0].detail
        assert detail == {"has_screening": True, "yes_count": 1}
        assert "heart_condition" not in str(detail)

    def test_an_admin_may_read_it_and_is_named_in_the_audit_row(self) -> None:
        """Admins read screening on the same terms as health data: allowed, and recorded
        under their own name. The trail is the price of the access, not a formality —
        three people can open this now, and the log has to say which one did."""
        admin, subject = member(MemberRole.ADMIN), member()
        uow = uow_with(admin, subject, screenings=[screening_for(subject.id)])

        view = ViewMemberScreening(uow, CONSENT_VERSION).execute(
            ViewMemberScreeningCommand(actor_id=admin.id, subject_id=subject.id)
        )

        assert view.screening is not None
        entries = uow.audit.committed_entries()
        assert len(entries) == 1
        assert entries[0].actor_member_id == admin.id

    def test_an_ordinary_member_may_not(self) -> None:
        alice, subject = member(), member()

        with pytest.raises(NotAuthorized):
            ViewMemberScreening(uow_with(alice, subject), CONSENT_VERSION).execute(
                ViewMemberScreeningCommand(actor_id=alice.id, subject_id=subject.id)
            )

    def test_a_refused_read_writes_no_audit_row(self) -> None:
        """Otherwise the log fills with attempts that never saw anything, and the rows
        that did stop standing out."""
        alice, subject = member(), member()
        uow = uow_with(alice, subject)

        with pytest.raises(NotAuthorized):
            ViewMemberScreening(uow, CONSENT_VERSION).execute(
                ViewMemberScreeningCommand(actor_id=alice.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []

    def test_an_unknown_subject_is_not_found(self) -> None:
        boss = member(MemberRole.SUPERUSER)

        with pytest.raises(MemberNotFound):
            ViewMemberScreening(uow_with(boss), CONSENT_VERSION).execute(
                ViewMemberScreeningCommand(actor_id=boss.id, subject_id=uuid4())
            )

    def test_a_member_who_has_not_been_screened_yields_nothing(self) -> None:
        """Not a row of assumed "no"s — the audit row says so too."""
        boss, subject = member(MemberRole.SUPERUSER), member()
        uow = uow_with(boss, subject)

        view = ViewMemberScreening(uow, CONSENT_VERSION).execute(
            ViewMemberScreeningCommand(actor_id=boss.id, subject_id=subject.id)
        )

        assert view.screening is None
        assert uow.audit.committed_entries()[0].detail["has_screening"] is False

    def test_if_the_audit_cannot_be_written_nothing_is_returned(self) -> None:
        """The whole reason this is a unit of work: the read and its record stand or
        fall together."""
        boss, subject = member(MemberRole.SUPERUSER), member()
        uow = uow_with(
            boss,
            subject,
            screenings=[screening_for(subject.id)],
            audit=FakeAuditRepository(fail=True),
        )

        with pytest.raises(RuntimeError):
            ViewMemberScreening(uow, CONSENT_VERSION).execute(
                ViewMemberScreeningCommand(actor_id=boss.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []


class TestViewMemberContact:
    def test_the_superuser_gets_the_details_and_an_audit_row(self) -> None:
        boss = member(MemberRole.SUPERUSER)
        subject = member(with_profile=True)
        uow = contact_uow_with(boss, subject)

        seen = ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=boss.id, subject_id=subject.id)
        )

        assert seen.profile.emergency_contact_phone == "0898765432"
        entries = uow.audit.committed_entries()
        assert len(entries) == 1
        assert entries[0].action is AuditAction.VIEW_CONTACT
        assert entries[0].subject_member_id == subject.id

    def test_the_audit_row_records_no_contact_details(self) -> None:
        boss = member(MemberRole.SUPERUSER)
        subject = member(with_profile=True)
        uow = contact_uow_with(boss, subject)

        ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=boss.id, subject_id=subject.id)
        )

        detail = str(uow.audit.committed_entries()[0].detail)
        assert "0898765432" not in detail
        assert "0812345678" not in detail
        assert "สมหญิง" not in detail

    def test_an_admin_may_read_it_and_is_named_in_the_audit_row(self) -> None:
        admin, subject = member(MemberRole.ADMIN), member(with_profile=True)
        uow = contact_uow_with(admin, subject)

        seen = ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=admin.id, subject_id=subject.id)
        )

        assert seen.profile.emergency_contact_phone == "0898765432"
        assert uow.audit.committed_entries()[0].actor_member_id == admin.id

    def test_a_refused_read_writes_no_audit_row(self) -> None:
        alice, subject = member(), member(with_profile=True)
        uow = contact_uow_with(alice, subject)

        with pytest.raises(NotAuthorized):
            ViewMemberContact(uow).execute(
                ViewMemberContactCommand(actor_id=alice.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []

    def test_if_the_audit_cannot_be_written_nothing_is_returned(self) -> None:
        boss = member(MemberRole.SUPERUSER)
        subject = member(with_profile=True)
        uow = contact_uow_with(boss, subject, audit=FakeAuditRepository(fail=True))

        with pytest.raises(RuntimeError):
            ViewMemberContact(uow).execute(
                ViewMemberContactCommand(actor_id=boss.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []

    def test_the_row_is_stamped_with_the_units_clock(self) -> None:
        boss = member(MemberRole.SUPERUSER)
        subject = member(with_profile=True)
        uow = contact_uow_with(boss, subject)

        ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=boss.id, subject_id=subject.id)
        )

        assert uow.audit.committed_entries()[0].created_at == datetime(
            2026, 8, 20, 9, 0, tzinfo=UTC
        )


class TestScreeningRidesOnConsent:
    """A screening is a cardiac and medication history — health data under มาตรา 26 in
    the same way a weight is, so the same basis governs reading it.

    Until this existed a member could withdraw, be refused at /admin/members/{id}/health,
    and have their screening answers read on the next endpoint along.
    """

    def test_active_consent_lets_an_admin_read_it(self) -> None:
        admin, subject = member(MemberRole.ADMIN), member()
        uow = uow_with(admin, subject, screenings=[screening_for(subject.id)])

        view = ViewMemberScreening(uow, CONSENT_VERSION).execute(
            ViewMemberScreeningCommand(actor_id=admin.id, subject_id=subject.id)
        )

        assert view.screening is not None

    def test_withdrawn_consent_closes_it(self) -> None:
        admin, subject = member(MemberRole.ADMIN), member()
        uow = uow_with(
            admin,
            subject,
            screenings=[screening_for(subject.id)],
            consents=[consent_for(admin.id), consent_for(subject.id, withdrawn=True)],
        )

        with pytest.raises(ConsentRequired):
            ViewMemberScreening(uow, CONSENT_VERSION).execute(
                ViewMemberScreeningCommand(actor_id=admin.id, subject_id=subject.id)
            )

    def test_no_consent_at_all_closes_it(self) -> None:
        admin, subject = member(MemberRole.ADMIN), member()
        uow = uow_with(admin, subject, screenings=[screening_for(subject.id)], consents=[])

        with pytest.raises(ConsentRequired):
            ViewMemberScreening(uow, CONSENT_VERSION).execute(
                ViewMemberScreeningCommand(actor_id=admin.id, subject_id=subject.id)
            )

    def test_consent_to_an_older_wording_closes_it(self) -> None:
        """Agreeing to v1 is not agreeing to v2 — the same rule the health read applies."""
        admin, subject = member(MemberRole.ADMIN), member()
        stale = Consent(
            id=uuid4(), member_id=subject.id, purpose=ConsentPurpose.HEALTH_DATA,
            version="v1", granted_at=NOW, withdrawn_at=None,
        )
        uow = uow_with(
            admin, subject, screenings=[screening_for(subject.id)],
            consents=[consent_for(admin.id), stale],
        )

        with pytest.raises(ConsentRequired):
            ViewMemberScreening(uow, CONSENT_VERSION).execute(
                ViewMemberScreeningCommand(actor_id=admin.id, subject_id=subject.id)
            )

    def test_a_refusal_writes_no_audit_row(self) -> None:
        """Refused before the row is written, exactly as the health read refuses: an
        access that did not happen must not appear in the log as though it did."""
        admin, subject = member(MemberRole.ADMIN), member()
        uow = uow_with(
            admin,
            subject,
            screenings=[screening_for(subject.id)],
            consents=[consent_for(admin.id), consent_for(subject.id, withdrawn=True)],
        )

        with pytest.raises(ConsentRequired):
            ViewMemberScreening(uow, CONSENT_VERSION).execute(
                ViewMemberScreeningCommand(actor_id=admin.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []

    def test_the_subjects_consent_is_what_counts_not_the_admins(self) -> None:
        """An admin who has withdrawn their own consent may still do their job; a subject
        who has withdrawn theirs is closed to everyone."""
        admin, subject = member(MemberRole.ADMIN), member()
        uow = uow_with(
            admin,
            subject,
            screenings=[screening_for(subject.id)],
            consents=[consent_for(admin.id, withdrawn=True), consent_for(subject.id)],
        )

        view = ViewMemberScreening(uow, CONSENT_VERSION).execute(
            ViewMemberScreeningCommand(actor_id=admin.id, subject_id=subject.id)
        )

        assert view.screening is not None


class TestContactDoesNotRideOnConsent:
    """The emergency contact rests on the club's interest in the safety of the people
    running for it (มาตรา 24), not on the health-data consent. Withdrawing that consent
    stops the club holding measurements; it must not make somebody unreachable at the
    moment their phone number was collected for.

    Structural as well as asserted: ContactViewUnitOfWork carries no consent repository,
    so this use case has nothing to gate on even if someone later tried.
    """

    def test_an_admin_reads_it_whatever_the_consent_record_says(self) -> None:
        admin = member(MemberRole.ADMIN)
        subject = member(with_profile=True)
        uow = contact_uow_with(admin, subject)

        seen = ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=admin.id, subject_id=subject.id)
        )

        assert seen.profile.emergency_contact_phone == "0898765432"

    def test_it_is_still_audited(self) -> None:
        """Ungated is not unwatched — the club can still show when it looked."""
        admin = member(MemberRole.ADMIN)
        subject = member(with_profile=True)
        uow = contact_uow_with(admin, subject)

        ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=admin.id, subject_id=subject.id)
        )

        entries = uow.audit.committed_entries()
        assert [e.action for e in entries] == [AuditAction.VIEW_CONTACT]
        assert entries[0].subject_member_id == subject.id
