"""Club news: who may write it, and who may read what.

The thing worth testing here is the asymmetry. Anyone at all may read a published
notice — that is the point of it — while a draft must reach nobody but the person who
wrote it, and nobody but the superuser may write one at all.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.application.use_cases.list_announcements import (
    ListAllAnnouncements,
    ListPublishedAnnouncements,
)
from app.application.use_cases.manage_announcements import (
    CreateAnnouncement,
    CreateAnnouncementCommand,
    UpdateAnnouncement,
    UpdateAnnouncementCommand,
)
from app.domain.announcement import Announcement
from app.domain.audit import AuditAction
from app.domain.entities import Member, MemberRole
from app.domain.errors import (
    AnnouncementNotFound,
    InvalidAnnouncementError,
    NotAuthorized,
)
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

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def a_member(role: MemberRole) -> Member:
    return Member.create(
        clerk_user_id=f"user_{role.value}", display_name=role.value, now=NOW, role=role
    )


BOSS = a_member(MemberRole.SUPERUSER)
ADMIN = a_member(MemberRole.ADMIN)
RUNNER = a_member(MemberRole.MEMBER)


def a_notice(
    title: str = "ซ้อมวิ่งเช้าวันเสาร์",
    *,
    published: bool = True,
    age_days: int = 0,
) -> Announcement:
    return Announcement(
        id=uuid4(),
        title=title,
        body="เจอกันหน้าตึกอำนวยการ 05:30 น.",
        is_published=published,
        created_at=NOW - timedelta(days=age_days),
        updated_at=NOW - timedelta(days=age_days),
    )


class Harness:
    def __init__(self, announcements: list[Announcement] | None = None) -> None:
        self.members = FakeMemberRepository([BOSS, ADMIN, RUNNER])
        self.announcements = FakeAnnouncementRepository(announcements or [])
        self.audit = FakeAuditRepository()

    def uow(self) -> FakeAdminUnitOfWork:
        return FakeAdminUnitOfWork(
            members=self.members,
            campaigns=FakeCampaignRepository(),
            rewards=FakeRewardRepository(),
            redemptions=FakeRedemptionRepository(),
            runs=FakeRunRepository(),
            ledger=FakePointsLedgerRepository(),
            audit=self.audit,
            announcements=self.announcements,
            clock=FixedClock(NOW),
        )

    def actions(self) -> list[AuditAction]:
        # Committed only: an audit row that never landed is not a record of anything.
        return [entry.action for entry in self.audit.committed_entries()]


class TestWhatThePublicSees:
    def test_only_published_notices(self) -> None:
        """No token reaches this list, so a draft appearing in it is a leak rather than
        a display bug."""
        harness = Harness([a_notice("เผยแพร่"), a_notice("ยังไม่เสร็จ", published=False)])

        listed = ListPublishedAnnouncements(harness.announcements).execute()

        assert [a.title for a in listed] == ["เผยแพร่"]

    def test_newest_first(self) -> None:
        harness = Harness(
            [a_notice("เก่า", age_days=7), a_notice("ใหม่"), a_notice("กลาง", age_days=2)]
        )

        listed = ListPublishedAnnouncements(harness.announcements).execute()

        assert [a.title for a in listed] == ["ใหม่", "กลาง", "เก่า"]

    def test_the_limit_takes_the_newest(self) -> None:
        """The landing page asks for a handful — it must get the recent ones, not
        whichever the database happened to return first."""
        harness = Harness([a_notice("เก่า", age_days=7), a_notice("ใหม่")])

        listed = ListPublishedAnnouncements(harness.announcements).execute(1)

        assert [a.title for a in listed] == ["ใหม่"]

    def test_hiding_takes_a_notice_back_off_the_list(self) -> None:
        notice = a_notice()
        harness = Harness([notice])

        UpdateAnnouncement(harness.uow()).execute(
            UpdateAnnouncementCommand(
                actor_id=BOSS.id, announcement_id=notice.id, is_published=False
            )
        )

        assert ListPublishedAnnouncements(harness.announcements).execute() == []
        # Hidden, not deleted: whoever wrote it can still find it.
        assert harness.announcements.get(notice.id) is not None


class TestWriting:
    def test_the_superuser_can_post_one(self) -> None:
        harness = Harness()

        created = CreateAnnouncement(harness.uow()).execute(
            CreateAnnouncementCommand(
                actor_id=BOSS.id, title="เปิดรับสมัคร", body="สมัครได้ที่หน้าเว็บ",
                is_published=True,
            )
        )

        assert created.is_published is True
        assert harness.actions() == [AuditAction.CREATE_ANNOUNCEMENT]

    def test_it_is_a_draft_unless_asked_otherwise(self) -> None:
        """Saving must not be the same act as publishing — nothing would ever get
        proofread."""
        harness = Harness()

        created = CreateAnnouncement(harness.uow()).execute(
            CreateAnnouncementCommand(actor_id=BOSS.id, title="ร่าง", body="ยังไม่เสร็จ")
        )

        assert created.is_published is False
        assert ListPublishedAnnouncements(harness.announcements).execute() == []

    @pytest.mark.parametrize("actor", [ADMIN, RUNNER])
    def test_nobody_else_can_post(self, actor: Member) -> None:
        harness = Harness()

        with pytest.raises(NotAuthorized):
            CreateAnnouncement(harness.uow()).execute(
                CreateAnnouncementCommand(actor_id=actor.id, title="x", body="y")
            )

        assert harness.announcements.list_all() == []
        assert harness.actions() == []

    @pytest.mark.parametrize("actor", [ADMIN, RUNNER])
    def test_nobody_else_can_edit(self, actor: Member) -> None:
        notice = a_notice()
        harness = Harness([notice])

        with pytest.raises(NotAuthorized):
            UpdateAnnouncement(harness.uow()).execute(
                UpdateAnnouncementCommand(
                    actor_id=actor.id, announcement_id=notice.id, title="แก้"
                )
            )

        assert harness.announcements.get(notice.id) == notice

    def test_an_empty_body_is_refused(self) -> None:
        harness = Harness()

        with pytest.raises(InvalidAnnouncementError, match="body"):
            CreateAnnouncement(harness.uow()).execute(
                CreateAnnouncementCommand(actor_id=BOSS.id, title="หัวข้อ", body="   ")
            )

    def test_editing_one_field_leaves_the_rest_alone(self) -> None:
        notice = a_notice()
        harness = Harness([notice])

        updated = UpdateAnnouncement(harness.uow()).execute(
            UpdateAnnouncementCommand(
                actor_id=BOSS.id, announcement_id=notice.id, title="ซ้อมวิ่งเช้าวันอาทิตย์"
            )
        )

        assert updated.title == "ซ้อมวิ่งเช้าวันอาทิตย์"
        assert updated.body == notice.body
        assert updated.is_published is True
        assert harness.actions() == [AuditAction.UPDATE_ANNOUNCEMENT]

    def test_editing_something_that_does_not_exist(self) -> None:
        harness = Harness()

        with pytest.raises(AnnouncementNotFound):
            UpdateAnnouncement(harness.uow()).execute(
                UpdateAnnouncementCommand(actor_id=BOSS.id, announcement_id=uuid4())
            )


class TestTheAdminList:
    def test_it_shows_drafts_too(self) -> None:
        """A draft that vanished from the only screen that could bring it back would be
        a draft nobody can publish."""
        harness = Harness([a_notice("เผยแพร่"), a_notice("ร่าง", published=False)])

        listed = ListAllAnnouncements(harness.members, harness.announcements).execute(BOSS.id)

        assert {a.title for a in listed} == {"เผยแพร่", "ร่าง"}

    @pytest.mark.parametrize("actor", [ADMIN, RUNNER])
    def test_nobody_else_may_see_the_drafts(self, actor: Member) -> None:
        harness = Harness([a_notice("ร่าง", published=False)])

        with pytest.raises(NotAuthorized):
            ListAllAnnouncements(harness.members, harness.announcements).execute(actor.id)
