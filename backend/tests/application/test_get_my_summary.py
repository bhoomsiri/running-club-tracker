"""GetMySummary reads one member's own data — and only that member's."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.get_my_summary import (
    CampaignSummary,
    GetMySummary,
    MemberSummary,
)
from app.domain.campaign import Campaign, CampaignType
from app.domain.entities import Member, MemberRole, ReviewStatus, RunEntry, RunSource
from app.domain.errors import MemberNotFound
from app.domain.health import HealthPhase, HealthRecord
from app.domain.redemption import PointsEntry, Redemption, RedemptionStatus, Reward
from tests.fakes.fake_uow import FakePointsLedgerRepository, FakeRedemptionRepository
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeHealthRepository,
    FakeMemberRepository,
    FakeRunRepository,
)

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
RETENTION = datetime(2028, 12, 31, tzinfo=UTC)
ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOB = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

# Two campaigns whose windows overlap in June.
DISTANCE = Campaign.create(
    id=UUID("11111111-1111-1111-1111-111111111111"),
    code="100km", name="100 km", type=CampaignType.CUMULATIVE_DISTANCE,
    starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31), config={"target_km": 100},
)
REWARDS = Campaign.create(
    id=UUID("22222222-2222-2222-2222-222222222222"),
    code="rewards", name="Run for rewards", type=CampaignType.REDEEM_REWARD,
    starts_on=date(2026, 6, 1), ends_on=date(2026, 8, 31), config={"points_per_km": 1},
)
ENDED = Campaign.create(
    id=UUID("33333333-3333-3333-3333-333333333333"),
    code="old", name="Last year", type=CampaignType.CUMULATIVE_DISTANCE,
    starts_on=date(2025, 1, 1), ends_on=date(2025, 12, 31), config={"target_km": 50},
    is_active=False,
)


def member(member_id: UUID = ALICE, name: str = "Alice") -> Member:
    return Member(
        id=member_id, clerk_user_id=f"clerk_{name}", display_name=name,
        role=MemberRole.MEMBER, created_at=NOW,
    )


def run(km: str, on: date, member_id: UUID = ALICE) -> RunEntry:
    return RunEntry.create(
        member_id=member_id, distance_km=Decimal(km), duration_seconds=1800, run_date=on,
        evidence_key="k", evidence_sha256="a" * 64, source=RunSource.APP_SCREENSHOT, now=NOW,
    )


def health(
    phase: HealthPhase, *, weight: str | None, height: str | None,
    member_id: UUID = ALICE, campaign_id: UUID = DISTANCE.id,
) -> HealthRecord:
    return HealthRecord(
        id=uuid4(), member_id=member_id, campaign_id=campaign_id, phase=phase,
        measured_on=date(2026, 6, 1),
        weight_kg=Decimal(weight) if weight else None,
        height_cm=Decimal(height) if height else None,
        resting_hr=None, systolic=None, diastolic=None,
        retention_until=RETENTION, created_at=NOW,
    )


def build(
    *, members: list[Member] | None = None, runs: list[RunEntry] | None = None,
    campaigns: list[Campaign] | None = None, ledger: list[PointsEntry] | None = None,
    redemptions: list[Redemption] | None = None, records: list[HealthRecord] | None = None,
) -> GetMySummary:
    return GetMySummary(
        members=FakeMemberRepository(members or [member()]),
        runs=FakeRunRepository(runs or []),
        campaigns=FakeCampaignRepository(campaigns or [DISTANCE, REWARDS]),
        ledger=FakePointsLedgerRepository(ledger or []),
        redemptions=FakeRedemptionRepository(redemptions or []),
        health=FakeHealthRepository(records or []),
    )


def campaign_named(summary: MemberSummary, code: str) -> CampaignSummary:
    return next(c for c in summary.campaigns if c.campaign.code == code)


def test_unknown_member_is_rejected() -> None:
    with pytest.raises(MemberNotFound):
        build().execute(uuid4())


def test_one_run_counts_in_every_campaign_whose_window_contains_it() -> None:
    """The overlap case: a June run belongs to both campaigns at once."""
    summary = build(runs=[run("10.000", date(2026, 6, 10))]).execute(ALICE)

    assert campaign_named(summary, "100km").progress.value == Decimal("10.000")
    assert campaign_named(summary, "rewards").progress.value == Decimal("10.00")
    assert summary.total_distance_km == Decimal("10.000")


def test_a_run_outside_a_window_counts_only_where_it_belongs() -> None:
    summary = build(
        runs=[run("10.000", date(2026, 6, 10)), run("5.000", date(2026, 3, 1))]
    ).execute(ALICE)

    assert campaign_named(summary, "100km").progress.value == Decimal("15.000")
    assert campaign_named(summary, "rewards").progress.value == Decimal("10.00")
    # Total distance is all-time, independent of any campaign window.
    assert summary.total_distance_km == Decimal("15.000")


def test_inactive_campaigns_are_not_listed() -> None:
    summary = build(campaigns=[DISTANCE, REWARDS, ENDED]).execute(ALICE)

    assert [c.campaign.code for c in summary.campaigns] == ["100km", "rewards"]


def test_earned_points_and_spendable_balance_are_different_numbers() -> None:
    """After redeeming, `earned` stays where it was and the balance drops. Showing
    earned as if it were the balance would let a member try to spend twice."""
    earned = PointsEntry.for_run(
        member_id=ALICE, campaign_id=REWARDS.id, points=Decimal("10"),
        run_entry_id=uuid4(), now=NOW,
    )
    reward = Reward(uuid4(), REWARDS.id, "Shirt", Decimal("4"), 1, True)
    redemption = Redemption.create(member_id=ALICE, reward=reward, now=NOW)
    spent = PointsEntry.for_redemption(redemption=redemption, now=NOW)

    summary = build(
        runs=[run("10.000", date(2026, 6, 10))],
        ledger=[earned, spent],
        redemptions=[redemption],
    ).execute(ALICE)

    rewards = campaign_named(summary, "rewards")
    assert rewards.progress.value == Decimal("10.00")  # earned, from the policy
    assert rewards.points_balance == Decimal("6.00")  # left to spend, from the ledger
    assert len(summary.redemptions) == 1


def test_distance_campaign_has_no_balance() -> None:
    """No `if campaign.type` anywhere: the policy declares whether points apply."""
    summary = build(runs=[run("10.000", date(2026, 6, 10))]).execute(ALICE)

    assert campaign_named(summary, "100km").points_balance is None
    assert campaign_named(summary, "rewards").points_balance is not None


class TestHealth:
    def test_bmi_is_derived_for_both_phases_with_a_delta(self) -> None:
        summary = build(
            records=[
                health(HealthPhase.BEFORE, weight="70.5", height="172.5"),
                health(HealthPhase.AFTER, weight="68.0", height=None),
            ]
        ).execute(ALICE)

        comparison = summary.health[0]
        assert comparison.bmi_before == Decimal("23.7")
        # The 'after' form doesn't re-ask for height — it reuses the 'before' height.
        assert comparison.bmi_after == Decimal("22.9")
        assert comparison.bmi_delta == Decimal("-0.8")

    def test_bmi_is_none_when_weight_is_missing(self) -> None:
        summary = build(
            records=[health(HealthPhase.BEFORE, weight=None, height="172.5")]
        ).execute(ALICE)

        assert summary.health[0].bmi_before is None
        assert summary.health[0].bmi_delta is None

    def test_bmi_is_none_when_height_is_missing_everywhere(self) -> None:
        summary = build(
            records=[health(HealthPhase.AFTER, weight="68.0", height=None)]
        ).execute(ALICE)

        assert summary.health[0].bmi_after is None

    def test_height_from_another_campaign_is_not_borrowed(self) -> None:
        summary = build(
            records=[
                health(HealthPhase.BEFORE, weight="70.5", height="172.5"),
                health(
                    HealthPhase.AFTER, weight="68.0", height=None, campaign_id=REWARDS.id
                ),
            ]
        ).execute(ALICE)

        rewards_health = next(h for h in summary.health if h.campaign_id == REWARDS.id)
        assert rewards_health.bmi_after is None

    def test_records_from_an_ended_campaign_are_still_visible_to_their_owner(self) -> None:
        summary = build(
            records=[
                health(HealthPhase.BEFORE, weight="70.5", height="172.5", campaign_id=ENDED.id)
            ]
        ).execute(ALICE)

        assert [h.campaign_id for h in summary.health] == [ENDED.id]


class TestIsolation:
    """IDOR: the summary is scoped to the member_id it was given, end to end."""

    def test_another_members_runs_and_health_are_invisible(self) -> None:
        uc = build(
            members=[member(ALICE, "Alice"), member(BOB, "Bob")],
            runs=[run("10.000", date(2026, 6, 10), ALICE), run("42.000", date(2026, 6, 11), BOB)],
            records=[
                health(HealthPhase.BEFORE, weight="70.5", height="172.5", member_id=ALICE),
                health(HealthPhase.BEFORE, weight="99.9", height="180.0", member_id=BOB),
            ],
        )

        summary = uc.execute(ALICE)

        assert summary.member.id == ALICE
        assert summary.total_distance_km == Decimal("10.000")
        assert summary.health[0].before is not None
        assert summary.health[0].before.weight_kg == Decimal("70.5")
        assert all(h.before is None or h.before.member_id == ALICE for h in summary.health)

    def test_another_members_points_are_not_in_my_balance(self) -> None:
        bobs_points = PointsEntry.for_run(
            member_id=BOB, campaign_id=REWARDS.id, points=Decimal("500"),
            run_entry_id=uuid4(), now=NOW,
        )
        uc = build(members=[member(ALICE), member(BOB, "Bob")], ledger=[bobs_points])

        summary = uc.execute(ALICE)

        assert campaign_named(summary, "rewards").points_balance == Decimal("0")

    def test_another_members_redemptions_are_not_listed(self) -> None:
        reward = Reward(uuid4(), REWARDS.id, "Shirt", Decimal("4"), 1, True)
        bobs = Redemption(
            id=uuid4(), member_id=BOB, reward_id=reward.id, campaign_id=REWARDS.id,
            points_spent=Decimal("4"), status=RedemptionStatus.PENDING, created_at=NOW,
        )
        uc = build(members=[member(ALICE), member(BOB, "Bob")], redemptions=[bobs])

        assert uc.execute(ALICE).redemptions == []


class TestActivityTotals:
    """Lifetime, over runs that still count. Every number here has to be one the member
    could arrive at themselves from their own runs — a total that quietly means something
    else is worse than no total."""

    def counted(
        self,
        km: str,
        seconds: int,
        calories_burned: int | None = None,
        steps: int | None = None,
    ) -> RunEntry:
        return RunEntry.create(
            member_id=ALICE, distance_km=Decimal(km), duration_seconds=seconds,
            run_date=date(2026, 6, 1), evidence_key="k", evidence_sha256="a" * 64,
            source=RunSource.APP_SCREENSHOT, now=NOW,
            calories_burned=calories_burned, steps=steps,
        )

    def test_no_runs_means_no_averages_rather_than_zeros(self) -> None:
        """0 min/km would be a claim about somebody who has simply not started."""
        totals = build().execute(ALICE).activity

        assert totals.run_count == 0
        assert totals.active_seconds == 0
        assert totals.avg_pace_min_per_km is None
        # 0 rather than None: `calories_from_runs` beside it already says the total is
        # made of nothing, so a second way of spelling absence would only invite a
        # frontend to handle one and forget the other.
        assert totals.total_calories == 0
        assert totals.calories_from_runs == 0
        assert totals.latest_run is None

    def test_average_pace_is_total_time_over_total_distance(self) -> None:
        """Not the mean of each run's pace. 1 km at 10:00 and 9 km at 5:00 average 5:30
        overall, where a mean of the two paces would say 7:30 — and the member's watch
        agrees with 5:30.
        """
        uc = build(runs=[self.counted("1", 600), self.counted("9", 2700)])

        totals = uc.execute(ALICE).activity

        assert totals.avg_pace_min_per_km == Decimal("5.500")
        assert totals.active_seconds == 3300

    def test_rejected_runs_are_left_out_of_every_total(self) -> None:
        """They count for nothing elsewhere; a calorie total that included them would
        contradict the distance sitting beside it."""
        rejected = replace(
            self.counted("5", 1800, calories_burned=300),
            review_status=ReviewStatus.REJECTED,
        )
        uc = build(runs=[self.counted("5", 1800, calories_burned=250), rejected])

        totals = uc.execute(ALICE).activity

        assert totals.run_count == 1
        assert totals.total_calories == 250

    def test_a_total_carries_how_many_runs_it_is_made_of(self) -> None:
        """Three of twelve runs having a calorie figure is the normal case, and a bare
        total would read as the total for all twelve (golden rule #4)."""
        uc = build(
            runs=[
                self.counted("5", 1800, calories_burned=250),
                self.counted("5", 1800),
                self.counted("5", 1800, calories_burned=300, steps=6000),
            ]
        )

        totals = uc.execute(ALICE).activity

        assert totals.run_count == 3
        assert totals.total_calories == 550
        assert totals.calories_from_runs == 2
        assert totals.total_steps == 6000
        assert totals.steps_from_runs == 1

    def test_a_count_nobody_recorded_is_absent_not_zero(self) -> None:
        uc = build(runs=[self.counted("5", 1800), self.counted("5", 1800)])

        totals = uc.execute(ALICE).activity

        assert totals.total_calories == 0
        assert totals.calories_from_runs == 0

    def test_the_latest_run_is_the_one_most_recently_run(self) -> None:
        """By the day it was run, not the day it was submitted — a member catching up on
        last week's runs should not see the oldest of them as their latest."""
        older = self.counted("5", 1800)
        newer = replace(self.counted("8", 2700, steps=9000), run_date=date(2026, 6, 10))
        uc = build(runs=[newer, older])

        latest = uc.execute(ALICE).activity.latest_run

        assert latest is not None
        assert latest.run_date == date(2026, 6, 10)
        assert latest.distance_km == Decimal("8.000")
        assert latest.steps == 9000
        assert latest.calories_burned is None
