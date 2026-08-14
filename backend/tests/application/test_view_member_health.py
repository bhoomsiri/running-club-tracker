"""Admin access to someone else's health data: role-gated, consent-gated, always audited."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.view_member_health import (
    ViewMemberHealth,
    ViewMemberHealthCommand,
)
from app.domain.audit import AuditAction
from app.domain.consent import Consent, ConsentPurpose
from app.domain.entities import Member, MemberRole
from app.domain.errors import ConsentRequired, MemberNotFound, NotAuthorized
from app.domain.health import HealthPhase, HealthRecord
from tests.fakes.fake_health_uow import (
    FakeAuditRepository,
    FakeConsentRepository,
    FakeHealthUnitOfWork,
)
from tests.fakes.fake_uow import FixedClock
from tests.fakes.repositories import FakeHealthRepository, FakeMemberRepository

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
RETENTION = datetime(2028, 12, 31, tzinfo=UTC)
VERSION = "v2"
ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
ADMIN = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
BOSS = UUID("55555555-5555-5555-5555-555555555555")
CAMPAIGN = UUID("11111111-1111-1111-1111-111111111111")


def member(member_id: UUID, role: MemberRole) -> Member:
    return Member(
        id=member_id, clerk_user_id=f"clerk_{member_id}", display_name=str(role),
        role=role, created_at=NOW,
    )


def record() -> HealthRecord:
    return HealthRecord(
        id=uuid4(), member_id=ALICE, campaign_id=CAMPAIGN, phase=HealthPhase.BEFORE,
        measured_on=date(2026, 6, 1), weight_kg=Decimal("70.5"), height_cm=Decimal("172.5"),
        resting_hr=None, systolic=None, diastolic=None,
        retention_until=RETENTION, created_at=NOW,
    )


def build(
    *,
    actor_role: MemberRole = MemberRole.ADMIN,
    consent_version: str | None = VERSION,
    withdrawn: bool = False,
    records: list[HealthRecord] | None = None,
    audit_fails: bool = False,
) -> tuple[ViewMemberHealth, FakeHealthUnitOfWork]:
    consents = []
    if consent_version is not None:
        granted = Consent.grant(
            member_id=ALICE, purpose=ConsentPurpose.HEALTH_DATA,
            version=consent_version, now=NOW,
        )
        consents.append(granted.withdraw(NOW) if withdrawn else granted)

    uow = FakeHealthUnitOfWork(
        members=FakeMemberRepository(
            [member(ALICE, MemberRole.MEMBER), member(ADMIN, actor_role)]
        ),
        consents=FakeConsentRepository(consents),
        health=FakeHealthRepository(records if records is not None else [record()]),
        audit=FakeAuditRepository(fail=audit_fails),
        clock=FixedClock(NOW),
    )
    return ViewMemberHealth(uow, VERSION), uow


class TestRoleGate:
    def test_an_ordinary_member_cannot_view_someone_elses_health(self) -> None:
        use_case, uow = build(actor_role=MemberRole.MEMBER)

        with pytest.raises(NotAuthorized):
            use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

        # A refused attempt reads nothing, so there is nothing to account for.
        assert uow.audit.committed_entries() == []

    def test_an_admin_may(self) -> None:
        use_case, _ = build(actor_role=MemberRole.ADMIN)

        view = use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

        assert view.subject.id == ALICE

    def test_the_superuser_may(self) -> None:
        use_case, _ = build(actor_role=MemberRole.SUPERUSER)

        view = use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

        assert view.health[0].bmi_before == Decimal("23.7")

    def test_unknown_actor_or_subject_is_rejected(self) -> None:
        use_case, _ = build()

        with pytest.raises(MemberNotFound):
            use_case.execute(ViewMemberHealthCommand(actor_id=uuid4(), subject_id=ALICE))
        with pytest.raises(MemberNotFound):
            use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=uuid4()))


class TestConsentGate:
    def test_withdrawn_consent_closes_admin_access(self) -> None:
        """Consent is the club's basis for processing this data. Withdrawn means the
        admin cannot look, even though the data still exists and its owner can."""
        use_case, uow = build(withdrawn=True)

        with pytest.raises(ConsentRequired):
            use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

        assert uow.audit.committed_entries() == []

    def test_consent_to_superseded_wording_closes_admin_access(self) -> None:
        use_case, _ = build(consent_version="v1")

        with pytest.raises(ConsentRequired):
            use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

    def test_no_consent_at_all_closes_admin_access(self) -> None:
        use_case, _ = build(consent_version=None)

        with pytest.raises(ConsentRequired):
            use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))


class TestAudit:
    def test_a_successful_view_writes_exactly_one_committed_entry(self) -> None:
        use_case, uow = build()

        use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

        entries = uow.audit.committed_entries()
        assert len(entries) == 1
        assert entries[0].action is AuditAction.VIEW_HEALTH
        assert entries[0].actor_member_id == ADMIN
        assert entries[0].subject_member_id == ALICE
        assert uow.committed

    def test_the_entry_carries_context_but_never_measurements(self) -> None:
        use_case, uow = build()

        use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

        detail = uow.audit.committed_entries()[0].detail
        assert detail == {"campaign_count": 1}
        assert not {"weight_kg", "height_cm", "bmi"} & set(detail)

    def test_a_failed_audit_write_returns_no_data_at_all(self) -> None:
        """An access that cannot be accounted for must not happen."""
        use_case, uow = build(audit_fails=True)

        with pytest.raises(RuntimeError):
            use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

        assert uow.audit.committed_entries() == []
        assert not uow.committed
        assert uow.rolled_back

    def test_each_viewed_member_is_one_entry(self) -> None:
        use_case, uow = build()

        use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))
        use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

        assert len(uow.audit.committed_entries()) == 2


def test_a_member_with_no_records_is_an_empty_view_not_an_error() -> None:
    use_case, uow = build(records=[])

    view = use_case.execute(ViewMemberHealthCommand(actor_id=ADMIN, subject_id=ALICE))

    assert view.health == []
    # Still an access to that member's (empty) health data, so still accounted for.
    assert len(uow.audit.committed_entries()) == 1
