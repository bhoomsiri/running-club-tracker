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
from app.domain.entities import Member, MemberProfile, MemberRole, Sex
from app.domain.errors import MemberNotFound, NotAuthorized
from app.domain.screening import QUESTION_KEYS, Screening
from tests.fakes.fake_sensitive_view_uow import DEFAULT_NOW, FakeSensitiveViewUnitOfWork
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


def uow_with(
    *members_in: Member,
    screenings: list[Screening] | None = None,
    audit: FakeAuditRepository | None = None,
) -> FakeSensitiveViewUnitOfWork:
    return FakeSensitiveViewUnitOfWork(
        members=FakeMemberRepository(list(members_in)),
        screenings=FakeScreeningRepository(screenings or []),
        audit=audit,
    )


class TestViewMemberScreening:
    def test_the_superuser_gets_the_answers_and_an_audit_row(self) -> None:
        boss, subject = member(MemberRole.SUPERUSER), member()
        uow = uow_with(boss, subject, screenings=[screening_for(subject.id, yes="diabetes")])

        view = ViewMemberScreening(uow).execute(
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

        ViewMemberScreening(uow).execute(
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

        view = ViewMemberScreening(uow).execute(
            ViewMemberScreeningCommand(actor_id=admin.id, subject_id=subject.id)
        )

        assert view.screening is not None
        entries = uow.audit.committed_entries()
        assert len(entries) == 1
        assert entries[0].actor_member_id == admin.id

    def test_an_ordinary_member_may_not(self) -> None:
        alice, subject = member(), member()

        with pytest.raises(NotAuthorized):
            ViewMemberScreening(uow_with(alice, subject)).execute(
                ViewMemberScreeningCommand(actor_id=alice.id, subject_id=subject.id)
            )

    def test_a_refused_read_writes_no_audit_row(self) -> None:
        """Otherwise the log fills with attempts that never saw anything, and the rows
        that did stop standing out."""
        alice, subject = member(), member()
        uow = uow_with(alice, subject)

        with pytest.raises(NotAuthorized):
            ViewMemberScreening(uow).execute(
                ViewMemberScreeningCommand(actor_id=alice.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []

    def test_an_unknown_subject_is_not_found(self) -> None:
        boss = member(MemberRole.SUPERUSER)

        with pytest.raises(MemberNotFound):
            ViewMemberScreening(uow_with(boss)).execute(
                ViewMemberScreeningCommand(actor_id=boss.id, subject_id=uuid4())
            )

    def test_a_member_who_has_not_been_screened_yields_nothing(self) -> None:
        """Not a row of assumed "no"s — the audit row says so too."""
        boss, subject = member(MemberRole.SUPERUSER), member()
        uow = uow_with(boss, subject)

        view = ViewMemberScreening(uow).execute(
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
            ViewMemberScreening(uow).execute(
                ViewMemberScreeningCommand(actor_id=boss.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []


class TestViewMemberContact:
    def test_the_superuser_gets_the_details_and_an_audit_row(self) -> None:
        boss = member(MemberRole.SUPERUSER)
        subject = member(with_profile=True)
        uow = uow_with(boss, subject)

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
        uow = uow_with(boss, subject)

        ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=boss.id, subject_id=subject.id)
        )

        detail = str(uow.audit.committed_entries()[0].detail)
        assert "0898765432" not in detail
        assert "0812345678" not in detail
        assert "สมหญิง" not in detail

    def test_an_admin_may_read_it_and_is_named_in_the_audit_row(self) -> None:
        admin, subject = member(MemberRole.ADMIN), member(with_profile=True)
        uow = uow_with(admin, subject)

        seen = ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=admin.id, subject_id=subject.id)
        )

        assert seen.profile.emergency_contact_phone == "0898765432"
        assert uow.audit.committed_entries()[0].actor_member_id == admin.id

    def test_a_refused_read_writes_no_audit_row(self) -> None:
        alice, subject = member(), member(with_profile=True)
        uow = uow_with(alice, subject)

        with pytest.raises(NotAuthorized):
            ViewMemberContact(uow).execute(
                ViewMemberContactCommand(actor_id=alice.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []

    def test_if_the_audit_cannot_be_written_nothing_is_returned(self) -> None:
        boss = member(MemberRole.SUPERUSER)
        subject = member(with_profile=True)
        uow = uow_with(boss, subject, audit=FakeAuditRepository(fail=True))

        with pytest.raises(RuntimeError):
            ViewMemberContact(uow).execute(
                ViewMemberContactCommand(actor_id=boss.id, subject_id=subject.id)
            )

        assert uow.audit.committed_entries() == []

    def test_the_row_is_stamped_with_the_units_clock(self) -> None:
        boss = member(MemberRole.SUPERUSER)
        subject = member(with_profile=True)
        uow = uow_with(boss, subject)

        ViewMemberContact(uow).execute(
            ViewMemberContactCommand(actor_id=boss.id, subject_id=subject.id)
        )

        assert uow.audit.committed_entries()[0].created_at == datetime(
            2026, 8, 20, 9, 0, tzinfo=UTC
        )
