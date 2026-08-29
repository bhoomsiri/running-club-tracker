"""Who gets a member row, when — and who is allowed to change a role."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.application.ports.token_verifier import VerifiedIdentity
from app.application.use_cases.ensure_member import (
    PLACEHOLDER_DISPLAY_NAME,
    EnsureMember,
)
from app.application.use_cases.sync_member_from_clerk import (
    ClerkUserEvent,
    SyncMemberFromClerk,
)
from app.domain.entities import Member, MemberRole
from app.domain.errors import MemberAlreadyExists
from tests.fakes.fake_uow import FixedClock
from tests.fakes.repositories import FakeMemberRepository

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
BOSS_CLERK_ID = "user_boss"


def existing(clerk_id: str, name: str, role: MemberRole = MemberRole.MEMBER) -> Member:
    return Member.create(clerk_user_id=clerk_id, display_name=name, now=NOW, role=role)


class TestJustInTimeProvisioning:
    def test_a_verified_newcomer_gets_a_member_row(self) -> None:
        members = FakeMemberRepository()

        member = EnsureMember(members, FixedClock(NOW)).execute(
            VerifiedIdentity(clerk_user_id="user_new", display_name="Somchai")
        )

        assert member.display_name == "Somchai"
        assert member.role is MemberRole.MEMBER
        assert members.get_by_clerk_id("user_new") is not None

    def test_a_nameless_token_gets_a_placeholder_not_a_blank(self) -> None:
        member = EnsureMember(FakeMemberRepository(), FixedClock(NOW)).execute(
            VerifiedIdentity(clerk_user_id="user_new")
        )

        assert member.display_name == PLACEHOLDER_DISPLAY_NAME

    def test_an_existing_member_is_returned_untouched(self) -> None:
        member = existing("user_1", "Somchai")
        members = FakeMemberRepository([member])

        result = EnsureMember(members, FixedClock(NOW)).execute(
            VerifiedIdentity(clerk_user_id="user_1", display_name="Something Else")
        )

        assert result.id == member.id
        assert result.display_name == "Somchai"  # never renamed by a login

    def test_jit_never_creates_an_admin_or_superuser(self) -> None:
        """A token cannot grant a role, whatever it claims."""
        member = EnsureMember(FakeMemberRepository(), FixedClock(NOW)).execute(
            VerifiedIdentity(clerk_user_id=BOSS_CLERK_ID, display_name="Boss")
        )

        assert member.role is MemberRole.MEMBER

    def test_losing_the_race_returns_the_winners_row(self) -> None:
        winner = existing("user_1", "Winner")

        class RacingRepository(FakeMemberRepository):
            def __init__(self) -> None:
                super().__init__()
                self._raced = False

            def get_by_clerk_id(self, clerk_user_id: str) -> Member | None:
                # Empty on the first look, occupied by the time we retry.
                if not self._raced:
                    self._raced = True
                    return None
                return winner

            def add(self, member: Member) -> None:
                raise MemberAlreadyExists(member.clerk_user_id)

        result = EnsureMember(RacingRepository(), FixedClock(NOW)).execute(
            VerifiedIdentity(clerk_user_id="user_1", display_name="Loser")
        )

        assert result.id == winner.id


class TestWebhookSync:
    def test_a_new_user_event_creates_the_member(self) -> None:
        members = FakeMemberRepository()

        member = SyncMemberFromClerk(members, FixedClock(NOW)).execute(
            ClerkUserEvent(clerk_user_id="user_1", display_name="Somchai")
        )

        assert member.display_name == "Somchai"

    def test_a_missing_name_falls_back_to_the_email_local_part(self) -> None:
        member = SyncMemberFromClerk(FakeMemberRepository(), FixedClock(NOW)).execute(
            ClerkUserEvent(clerk_user_id="user_1", display_name=None, email="somchai@mail.com")
        )

        assert member.display_name == "somchai"

    def test_no_name_and_no_email_still_never_leaves_a_blank(self) -> None:
        member = SyncMemberFromClerk(FakeMemberRepository(), FixedClock(NOW)).execute(
            ClerkUserEvent(clerk_user_id="user_1", display_name=None)
        )

        assert member.display_name == PLACEHOLDER_DISPLAY_NAME

    def test_a_later_event_never_overwrites_a_real_name(self) -> None:
        """The member owns their name — a Clerk profile edit must not rename them on
        the leaderboard."""
        members = FakeMemberRepository([existing("user_1", "ตั้งชื่อเอง")])

        member = SyncMemberFromClerk(members, FixedClock(NOW)).execute(
            ClerkUserEvent(clerk_user_id="user_1", display_name="Clerk Name", created=False)
        )

        assert member.display_name == "ตั้งชื่อเอง"

    def test_the_placeholder_from_jit_is_filled_in(self) -> None:
        """The one exception: a placeholder is not a name anybody chose."""
        members = FakeMemberRepository([existing("user_1", PLACEHOLDER_DISPLAY_NAME)])

        SyncMemberFromClerk(members, FixedClock(NOW)).execute(
            ClerkUserEvent(clerk_user_id="user_1", display_name="Somchai")
        )

        member = members.get_by_clerk_id("user_1")
        assert member is not None
        assert member.display_name == "Somchai"


class TestSuperuserBootstrap:
    def test_the_configured_clerk_id_is_promoted(self) -> None:
        members = FakeMemberRepository()

        member = SyncMemberFromClerk(members, FixedClock(NOW), BOSS_CLERK_ID).execute(
            ClerkUserEvent(clerk_user_id=BOSS_CLERK_ID, display_name="Boss")
        )

        assert member.role is MemberRole.SUPERUSER

    def test_nobody_else_is(self) -> None:
        members = FakeMemberRepository()

        member = SyncMemberFromClerk(members, FixedClock(NOW), BOSS_CLERK_ID).execute(
            ClerkUserEvent(clerk_user_id="user_someone", display_name="Someone")
        )

        assert member.role is MemberRole.MEMBER

    def test_the_seat_is_not_taken_from_an_existing_superuser(self) -> None:
        """uq_member_single_superuser allows exactly one. Rather than let the database
        reject the whole webhook, the promotion is skipped."""
        incumbent = existing("user_old_boss", "Old Boss", MemberRole.SUPERUSER)
        members = FakeMemberRepository([incumbent])

        member = SyncMemberFromClerk(members, FixedClock(NOW), BOSS_CLERK_ID).execute(
            ClerkUserEvent(clerk_user_id=BOSS_CLERK_ID, display_name="Boss")
        )

        assert member.role is MemberRole.MEMBER
        superuser = members.get_superuser()
        assert superuser is not None
        assert superuser.id == incumbent.id

    def test_promotion_is_idempotent(self) -> None:
        members = FakeMemberRepository()
        use_case = SyncMemberFromClerk(members, FixedClock(NOW), BOSS_CLERK_ID)
        event = ClerkUserEvent(clerk_user_id=BOSS_CLERK_ID, display_name="Boss")

        use_case.execute(event)
        member = use_case.execute(event)

        assert member.role is MemberRole.SUPERUSER
        assert len(members.list_all()) == 1

    def test_no_bootstrap_configured_means_no_promotions(self) -> None:
        members = FakeMemberRepository()

        member = SyncMemberFromClerk(members, FixedClock(NOW), None).execute(
            ClerkUserEvent(clerk_user_id=BOSS_CLERK_ID, display_name="Boss")
        )

        assert member.role is MemberRole.MEMBER


def test_roles_can_only_be_set_through_the_repository_not_a_command() -> None:
    """There is deliberately no 'set my role' path: ClerkUserEvent has no role field."""
    assert not hasattr(ClerkUserEvent(clerk_user_id="u", display_name="n"), "role")
    with pytest.raises(TypeError):
        ClerkUserEvent(clerk_user_id="u", display_name="n", role="superuser")  # type: ignore[call-arg]


class TestAvatarSync:
    """The picture is treated differently from the name, on purpose.

    A member owns their display name — the club may know them by a running nickname, so
    a later Clerk event must not rename them. Nobody owns their picture here, because the
    club offers no way to set one: Clerk is the only source, so a member who changes their
    Google photo expects the club to follow. Keeping the first one forever would leave an
    avatar nobody could update.
    """

    def event(self, **fields: object) -> ClerkUserEvent:
        base: dict[str, object] = {"clerk_user_id": "user_1", "display_name": "Somchai"}
        base.update(fields)
        return ClerkUserEvent(**base)  # type: ignore[arg-type]

    def test_a_picture_arrives_with_the_member(self) -> None:
        members = FakeMemberRepository()

        member = SyncMemberFromClerk(members, FixedClock(NOW)).execute(
            self.event(image_url="https://img.clerk.com/a", has_image=True)
        )

        assert member.image_url == "https://img.clerk.com/a"
        assert member.has_image is True

    def test_a_later_event_does_update_the_picture(self) -> None:
        """The opposite of the display-name rule, and the reason both are written down."""
        members = FakeMemberRepository()
        sync = SyncMemberFromClerk(members, FixedClock(NOW))
        sync.execute(self.event(image_url="https://img.clerk.com/old", has_image=True))

        member = sync.execute(self.event(image_url="https://img.clerk.com/new", has_image=True))

        assert member.image_url == "https://img.clerk.com/new"

    def test_a_later_event_still_does_not_rename_anybody(self) -> None:
        """Both rules at once, so neither can be broken while satisfying the other."""
        members = FakeMemberRepository()
        sync = SyncMemberFromClerk(members, FixedClock(NOW))
        sync.execute(self.event(display_name="Somchai", image_url="a", has_image=True))

        member = sync.execute(
            self.event(display_name="Somebody Else", image_url="b", has_image=True)
        )

        assert member.display_name == "Somchai"
        assert member.image_url == "b"

    def test_removing_the_photo_at_clerk_removes_it_here(self) -> None:
        """Otherwise a member who deletes their picture keeps showing it to the club."""
        members = FakeMemberRepository()
        sync = SyncMemberFromClerk(members, FixedClock(NOW))
        sync.execute(self.event(image_url="https://img.clerk.com/a", has_image=True))

        member = sync.execute(self.event(image_url=None, has_image=False))

        assert member.image_url is None
        assert member.has_image is False

    def test_a_generated_default_is_recorded_as_not_theirs(self) -> None:
        """Clerk sends an image_url for every account, including ones that never set a
        picture. The URL is kept; has_image is what stops it being shown as a choice."""
        members = FakeMemberRepository()

        member = SyncMemberFromClerk(members, FixedClock(NOW)).execute(
            self.event(image_url="https://img.clerk.com/generated", has_image=False)
        )

        assert member.has_image is False

    def test_the_promoted_superuser_keeps_their_picture(self) -> None:
        """The bootstrap rebuilds the member to change the role; it must not drop the
        fields it was not asked about."""
        members = FakeMemberRepository()

        member = SyncMemberFromClerk(members, FixedClock(NOW), "user_1").execute(
            self.event(image_url="https://img.clerk.com/a", has_image=True)
        )

        assert member.role is MemberRole.SUPERUSER
        assert member.image_url == "https://img.clerk.com/a"
