"""The club standing: the order, the ties, and what it must not carry.

Everyone in the club sees this list, which makes it the widest audience any response in
the app has. So as well as the ordering there is a test here that the row shape has not
quietly grown a field.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.get_leaderboard import GetLeaderboard, LeaderboardEntry
from app.domain.campaign import Campaign, CampaignType
from app.domain.entities import (
    Member,
    MemberProfile,
    MemberRole,
    ReviewStatus,
    RunEntry,
    RunSource,
)
from app.domain.errors import MemberNotFound
from app.domain.redemption import LedgerReason, PointsEntry
from tests.fakes.fake_uow import FakePointsLedgerRepository
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeMemberRepository,
    FakeRunRepository,
)

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)

DISTANCE_CAMPAIGN = Campaign(
    id=uuid4(),
    code="hundred-km-2026",
    name="สะสมระยะ 100 กิโลเมตร",
    type=CampaignType.CUMULATIVE_DISTANCE,
    starts_on=date(2026, 1, 1),
    ends_on=date(2026, 12, 31),
    config={"target_km": 100},
    is_active=True,
)

POINTS_CAMPAIGN = Campaign(
    id=uuid4(),
    code="daily-10km-2026",
    name="วันละ 10 กิโลเมตร สะสมแลกของรางวัล",
    type=CampaignType.DAILY_THRESHOLD_REWARD,
    starts_on=date(2026, 1, 1),
    ends_on=date(2026, 12, 31),
    config={"threshold_km": "10", "points_per_day": "1", "submit_within_days": 1},
    is_active=True,
)


def a_member(name: str) -> Member:
    return Member.create(
        clerk_user_id=f"user_{name}", display_name=name, now=NOW, role=MemberRole.MEMBER
    )


def a_run(
    member_id: UUID, km: str, *, rejected: bool = False, day: int = 1
) -> RunEntry:
    return RunEntry(
        id=uuid4(),
        member_id=member_id,
        distance_km=Decimal(km),
        duration_seconds=1800,
        run_date=date(2026, 6, day),
        evidence_key=f"runs/{member_id}/{'a' * 64}.jpeg",
        evidence_sha256="a" * 64,
        source=RunSource.APP_SCREENSHOT,
        review_status=ReviewStatus.REJECTED if rejected else ReviewStatus.OK,
        created_at=NOW,
    )


def points(member_id: UUID, delta: str) -> PointsEntry:
    return PointsEntry(
        id=uuid4(),
        member_id=member_id,
        campaign_id=POINTS_CAMPAIGN.id,
        delta=Decimal(delta),
        reason=LedgerReason.RUN_EARNED,
        run_entry_id=uuid4(),
        redemption_id=None,
        created_at=NOW,
    )


def build(
    members: list[Member],
    runs: list[RunEntry] | None = None,
    ledger: list[PointsEntry] | None = None,
    campaigns: list[Campaign] | None = None,
) -> GetLeaderboard:
    return GetLeaderboard(
        FakeMemberRepository(members),
        FakeRunRepository(runs or []),
        FakeCampaignRepository(
            campaigns if campaigns is not None else [DISTANCE_CAMPAIGN, POINTS_CAMPAIGN]
        ),
        FakePointsLedgerRepository(ledger or []),
    )


class TestTheOrder:
    def test_furthest_first(self) -> None:
        near, far, middle = a_member("near"), a_member("far"), a_member("middle")
        board = build(
            [near, far, middle],
            [a_run(near.id, "5"), a_run(far.id, "40"), a_run(middle.id, "12.5")],
        ).execute(near.id)

        assert [e.name for e in board.entries] == ["far", "middle", "near"]
        assert [e.rank for e in board.entries] == [1, 2, 3]

    def test_a_tie_shares_a_place_and_the_next_one_skips(self) -> None:
        """Standard competition ranking. Breaking a real tie by name would invent a
        difference that is not there, and whoever was put second would be right to
        complain."""
        first, tied_a, tied_b, last = (
            a_member("first"),
            a_member("anong"),
            a_member("bee"),
            a_member("last"),
        )
        board = build(
            [first, tied_a, tied_b, last],
            [
                a_run(first.id, "50"),
                a_run(tied_a.id, "40"),
                a_run(tied_b.id, "40"),
                a_run(last.id, "10"),
            ],
        ).execute(first.id)

        assert [(e.name, e.rank) for e in board.entries] == [
            ("first", 1),
            ("anong", 2),
            ("bee", 2),
            ("last", 4),
        ]

    def test_a_rejected_run_counts_for_nothing(self) -> None:
        """The same rule as every other screen — otherwise the leaderboard would rank
        someone above a member who actually ran further."""
        alice, bob = a_member("alice"), a_member("bob")
        board = build(
            [alice, bob],
            [
                a_run(alice.id, "30"),
                a_run(alice.id, "100", rejected=True),
                a_run(bob.id, "50"),
            ],
        ).execute(alice.id)

        assert [e.name for e in board.entries] == ["bob", "alice"]
        alice_row = next(e for e in board.entries if e.name == "alice")
        assert alice_row.total_distance_km == Decimal("30.000")
        assert alice_row.run_count == 1

    def test_a_member_who_has_never_run_is_still_listed(self) -> None:
        runner, watcher = a_member("runner"), a_member("watcher")

        board = build([runner, watcher], [a_run(runner.id, "5")]).execute(watcher.id)

        assert [e.name for e in board.entries] == ["runner", "watcher"]
        assert board.entries[1].total_distance_km == Decimal("0.000")


class TestTheCallersOwnLine:
    def test_it_comes_back_even_from_the_bottom(self) -> None:
        """Someone in last place opening a top-ten and not finding themselves has
        learned nothing."""
        members = [a_member(f"m{i:02d}") for i in range(12)]
        runs = [a_run(m.id, str((12 - i) * 5)) for i, m in enumerate(members)]
        me = members[-1]

        board = build(members, runs).execute(me.id)

        assert board.me.member_id == me.id
        assert board.me.rank == 12
        assert board.total_members == 12

    def test_the_number_of_members_is_the_whole_club(self) -> None:
        members = [a_member("a"), a_member("b"), a_member("c")]

        board = build(members).execute(members[0].id)

        assert board.total_members == 3

    def test_an_unknown_caller_is_refused(self) -> None:
        with pytest.raises(MemberNotFound):
            build([a_member("a")]).execute(uuid4())


class TestPoints:
    def test_the_balance_comes_from_the_campaign_that_awards_them(self) -> None:
        alice, bob = a_member("alice"), a_member("bob")

        board = build(
            [alice, bob],
            [a_run(alice.id, "10"), a_run(bob.id, "20")],
            [points(alice.id, "3"), points(bob.id, "1")],
        ).execute(alice.id)

        by_name = {e.name: e for e in board.entries}
        assert by_name["alice"].points == Decimal("3")
        assert by_name["bob"].points == Decimal("1")
        assert board.points_campaign_name == POINTS_CAMPAIGN.name

    def test_with_no_points_campaign_there_is_no_points_column(self) -> None:
        """Rather than a column of zeroes that means nothing."""
        alice = a_member("alice")

        board = build(
            [alice], [a_run(alice.id, "10")], campaigns=[DISTANCE_CAMPAIGN]
        ).execute(alice.id)

        assert board.points_campaign_name is None
        assert board.entries[0].points is None


class TestWhatItCarries:
    def test_a_row_holds_a_name_a_distance_and_two_counts_and_nothing_else(self) -> None:
        """Every member sees every row, so this list has the widest audience of anything
        the API returns. If a field is added here, it is added for the whole club."""
        assert set(LeaderboardEntry.__dataclass_fields__) == {
            "rank",
            "member_id",
            "name",
            "total_distance_km",
            "points",
            "run_count",
        }

    def test_the_name_is_the_one_the_club_uses(self) -> None:
        alice = a_member("alice")
        named = alice.with_profile(MemberProfile(full_name_th="สมชาย ใจดี"))

        board = build([named]).execute(named.id)

        assert board.entries[0].name == "สมชาย ใจดี"
