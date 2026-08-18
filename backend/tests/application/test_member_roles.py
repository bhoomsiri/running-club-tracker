"""Handing out the admin role, and taking it back.

This is the endpoint that widens who may read everyone else's data, so the tests come in
pairs: one that proves the capability works, and one that proves it stops where it is
supposed to. The refusals matter more than the successes here — a broken promotion is a
complaint, a promotion that should have been refused is a data breach.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.set_member_role import SetMemberRole, SetMemberRoleCommand
from app.domain.audit import AuditAction
from app.domain.entities import Member, MemberRole
from app.domain.errors import MemberNotFound, NotAuthorized
from tests.fakes.fake_uow import (
    FakeAdminUnitOfWork,
    FakeAnnouncementRepository,
    FakeAuditRepository,
    FakePointsLedgerRepository,
    FakeRedemptionRepository,
    FakeRewardRepository,
    FixedClock,
)
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeMemberRepository,
    FakeRunRepository,
)

NOW = datetime(2026, 8, 18, 9, 0, tzinfo=UTC)


def member(role: MemberRole = MemberRole.MEMBER) -> Member:
    return Member.create(
        clerk_user_id=f"user_{uuid4().hex[:6]}",
        display_name="Somebody",
        now=NOW,
        role=role,
    )


class Harness:
    def __init__(self, *members_in: Member) -> None:
        self.members = FakeMemberRepository(list(members_in))
        self.audit = FakeAuditRepository()
        self.uow = FakeAdminUnitOfWork(
            members=self.members,
            campaigns=FakeCampaignRepository(),
            rewards=FakeRewardRepository(),
            redemptions=FakeRedemptionRepository(),
            ledger=FakePointsLedgerRepository(),
            runs=FakeRunRepository(),
            announcements=FakeAnnouncementRepository(),
            audit=self.audit,
            clock=FixedClock(NOW),
        )

    def set_role(self, actor: Member, subject_id: UUID, role: MemberRole) -> Member:
        return SetMemberRole(self.uow).execute(
            SetMemberRoleCommand(actor_id=actor.id, subject_id=subject_id, role=role)
        )

    def stored_role(self, member_id: UUID) -> MemberRole:
        stored = self.members.get(member_id)
        assert stored is not None
        return stored.role


class TestWhoMayHandOutTheRole:
    def test_the_superuser_can_promote_a_member(self) -> None:
        boss, alice = member(MemberRole.SUPERUSER), member()
        harness = Harness(boss, alice)

        updated = harness.set_role(boss, alice.id, MemberRole.ADMIN)

        assert updated.role is MemberRole.ADMIN
        assert harness.stored_role(alice.id) is MemberRole.ADMIN

    def test_the_superuser_can_demote_an_admin(self) -> None:
        boss, helper = member(MemberRole.SUPERUSER), member(MemberRole.ADMIN)
        harness = Harness(boss, helper)

        harness.set_role(boss, helper.id, MemberRole.MEMBER)

        assert harness.stored_role(helper.id) is MemberRole.MEMBER

    def test_an_admin_cannot_promote_anybody(self) -> None:
        """The whole point of the role being the superuser's to give: an admin who could
        appoint another admin could appoint a hundred, and nobody would have decided it."""
        helper, alice = member(MemberRole.ADMIN), member()
        harness = Harness(helper, alice)

        with pytest.raises(NotAuthorized):
            harness.set_role(helper, alice.id, MemberRole.ADMIN)

        assert harness.stored_role(alice.id) is MemberRole.MEMBER

    def test_an_admin_cannot_demote_another_admin(self) -> None:
        """Otherwise an admin about to have their run rejected can remove the person
        reviewing it."""
        helper, other = member(MemberRole.ADMIN), member(MemberRole.ADMIN)
        harness = Harness(helper, other)

        with pytest.raises(NotAuthorized):
            harness.set_role(helper, other.id, MemberRole.MEMBER)

        assert harness.stored_role(other.id) is MemberRole.ADMIN

    def test_an_ordinary_member_cannot_promote_themselves(self) -> None:
        alice = member()
        harness = Harness(alice)

        with pytest.raises(NotAuthorized):
            harness.set_role(alice, alice.id, MemberRole.ADMIN)

        assert harness.stored_role(alice.id) is MemberRole.MEMBER


class TestWhatTheRoleMayBeSetTo:
    def test_it_cannot_create_a_second_superuser(self) -> None:
        """The database permits exactly one superuser row. A path that could write a
        second one would either hit that index at the worst possible moment or — worse —
        find a way around it."""
        boss, alice = member(MemberRole.SUPERUSER), member()
        harness = Harness(boss, alice)

        with pytest.raises(NotAuthorized):
            harness.set_role(boss, alice.id, MemberRole.SUPERUSER)

        assert harness.stored_role(alice.id) is MemberRole.MEMBER

    def test_the_superusers_own_role_cannot_be_changed(self) -> None:
        """Including by themselves. Somebody has to be left who can fix things, and a
        mis-tap on the wrong row is exactly how that person disappears."""
        boss = member(MemberRole.SUPERUSER)
        harness = Harness(boss)

        with pytest.raises(NotAuthorized):
            harness.set_role(boss, boss.id, MemberRole.MEMBER)

        assert harness.stored_role(boss.id) is MemberRole.SUPERUSER

    def test_an_unknown_member_is_not_found(self) -> None:
        boss = member(MemberRole.SUPERUSER)
        harness = Harness(boss)

        with pytest.raises(MemberNotFound):
            harness.set_role(boss, uuid4(), MemberRole.ADMIN)

    def test_setting_the_role_somebody_already_has_is_a_no_op(self) -> None:
        """Idempotent: a double tap on a slow connection is not an error to explain."""
        boss, helper = member(MemberRole.SUPERUSER), member(MemberRole.ADMIN)
        harness = Harness(boss, helper)

        updated = harness.set_role(boss, helper.id, MemberRole.ADMIN)

        assert updated.role is MemberRole.ADMIN
        assert harness.stored_role(helper.id) is MemberRole.ADMIN


class TestTheAuditTrail:
    def test_a_promotion_is_recorded_with_both_roles(self) -> None:
        boss, alice = member(MemberRole.SUPERUSER), member()
        harness = Harness(boss, alice)

        harness.set_role(boss, alice.id, MemberRole.ADMIN)

        entries = harness.audit.committed_entries()
        assert len(entries) == 1
        assert entries[0].action is AuditAction.CHANGE_ROLE
        assert entries[0].actor_member_id == boss.id
        assert entries[0].subject_member_id == alice.id
        assert entries[0].detail == {"from_role": "member", "to_role": "admin"}

    def test_a_demotion_is_recorded_the_same_way(self) -> None:
        boss, helper = member(MemberRole.SUPERUSER), member(MemberRole.ADMIN)
        harness = Harness(boss, helper)

        harness.set_role(boss, helper.id, MemberRole.MEMBER)

        assert harness.audit.committed_entries()[0].detail == {
            "from_role": "admin",
            "to_role": "member",
        }

    def test_even_the_no_op_is_recorded(self) -> None:
        """Somebody pressed the button; the log answers "who did what and when", and a
        call that changed nothing is still a call that was made."""
        boss, helper = member(MemberRole.SUPERUSER), member(MemberRole.ADMIN)
        harness = Harness(boss, helper)

        harness.set_role(boss, helper.id, MemberRole.ADMIN)

        assert harness.audit.committed_entries()[0].detail == {
            "from_role": "admin",
            "to_role": "admin",
        }

    def test_a_refused_change_records_nothing(self) -> None:
        helper, alice = member(MemberRole.ADMIN), member()
        harness = Harness(helper, alice)

        with pytest.raises(NotAuthorized):
            harness.set_role(helper, alice.id, MemberRole.ADMIN)

        assert harness.audit.committed_entries() == []

    def test_the_role_and_its_audit_row_commit_together(self) -> None:
        """If the trail cannot be written the promotion does not happen — an access
        widened without a record of who widened it is the one outcome to avoid.

        Asserted through the unit of work rather than the stored role: this fake applies
        a member write immediately, while the real one issues it inside the session and
        discards it on rollback. The HTTP test against a real database is what proves the
        row itself is unchanged.
        """
        boss, alice = member(MemberRole.SUPERUSER), member()
        harness = Harness(boss, alice)
        harness.uow.audit = FakeAuditRepository(fail=True)

        with pytest.raises(RuntimeError):
            harness.set_role(boss, alice.id, MemberRole.ADMIN)

        assert harness.uow.committed is False
