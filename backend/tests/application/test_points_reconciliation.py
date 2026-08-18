"""Earning as reconciliation, across both this year's activities.

The cases that matter are the ones per-run crediting could not express: a day carried
over the line by several runs together, and a rejection that costs a whole day even
though the rejected run never held a ledger row of its own.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.review_run import ReviewRun, ReviewRunCommand
from app.application.use_cases.submit_run import SubmitRun, SubmitRunCommand
from app.domain.audit import AuditAction
from app.domain.campaign import Campaign, CampaignType
from app.domain.entities import Member, MemberRole, ReviewStatus, RunEntry, RunSource
from app.domain.errors import NotAuthorized, RunNotFound
from app.domain.redemption import LedgerReason
from tests.fakes.fake_health_uow import FakeAuditRepository
from tests.fakes.fake_uow import (
    FakePointsLedgerRepository,
    FakeRunReviewUnitOfWork,
    FakeRunSubmissionUnitOfWork,
    FixedClock,
)
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeMemberRepository,
    FakeRunRepository,
)

ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
BOSS = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")   # superuser: mutations are theirs
ADMIN = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")  # admin: may view, may not decide

# This year's two activities, running side by side over the same window.
HUNDRED_KM = Campaign.create(
    code="100km", name="สะสม 100 กม.", type=CampaignType.CUMULATIVE_DISTANCE,
    starts_on=date(2026, 8, 15), ends_on=date(2026, 9, 30), config={"target_km": 100},
)
DAILY_10 = Campaign.create(
    code="daily10", name="วันละ 10 กม.", type=CampaignType.DAILY_THRESHOLD_REWARD,
    starts_on=date(2026, 8, 15), ends_on=date(2026, 9, 30),
    config={"qualifying_km": 10, "points_per_qualifying_day": 1, "submit_within_days": 1},
)


def at(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=20)


def key_for(member_id: UUID, seed: str) -> str:
    return f"runs/{member_id}/{hashlib.sha256(seed.encode()).hexdigest()}.jpeg"


class Harness:
    """A member, their runs, and the two campaigns — sharing one ledger across the
    submit and review use cases, like the real database does."""

    def __init__(self, campaigns: list[Campaign] | None = None) -> None:
        self.runs = FakeRunRepository()
        self.campaigns = FakeCampaignRepository(campaigns or [HUNDRED_KM, DAILY_10])
        self.ledger = FakePointsLedgerRepository()
        self.audit = FakeAuditRepository()
        self.members = FakeMemberRepository(
            [
                Member(id=ALICE, clerk_user_id="c_alice", display_name="Alice",
                       role=MemberRole.MEMBER, created_at=at(date(2026, 8, 15))),
                Member(id=BOSS, clerk_user_id="c_boss", display_name="Boss",
                       role=MemberRole.SUPERUSER, created_at=at(date(2026, 8, 15))),
                Member(id=ADMIN, clerk_user_id="c_admin", display_name="Admin",
                       role=MemberRole.ADMIN, created_at=at(date(2026, 8, 15))),
            ]
        )

    def submit(self, km: str, ran_on: date, submitted_on: date | None = None) -> RunEntry:
        clock = FixedClock(at(submitted_on or ran_on))
        uow = FakeRunSubmissionUnitOfWork(
            runs=self.runs, campaigns=self.campaigns, ledger=self.ledger, clock=clock
        )
        return SubmitRun(uow).execute(
            SubmitRunCommand(
                member_id=ALICE, distance_km=Decimal(km), duration_seconds=1800,
                run_date=ran_on, image_key=key_for(ALICE, f"{km}-{ran_on}-{submitted_on}"),
                source=RunSource.APP_SCREENSHOT,
            )
        )

    def review(
        self, run_id: UUID, decision: ReviewStatus, actor_id: UUID = BOSS
    ) -> RunEntry:
        uow = FakeRunReviewUnitOfWork(
            members=self.members, runs=self.runs, campaigns=self.campaigns,
            ledger=self.ledger, audit=self.audit, clock=FixedClock(at(date(2026, 9, 1))),
        )
        return ReviewRun(uow).execute(
            ReviewRunCommand(actor_id=actor_id, run_id=run_id, decision=decision)
        )

    def close(self, campaign: Campaign) -> None:
        """What a superuser does when the activity is over."""
        self.campaigns.save(replace(campaign, is_active=False))

    def points(self, campaign: Campaign = DAILY_10) -> Decimal:
        return self.ledger.balance(ALICE, campaign.id)


class TestDailyThresholdEarning:
    def test_six_plus_five_in_one_day_earns_one_point(self) -> None:
        harness = Harness()

        harness.submit("6", date(2026, 8, 20))
        assert harness.points() == Decimal("0.00")  # 6 km alone doesn't qualify the day

        harness.submit("5", date(2026, 8, 20))
        assert harness.points() == Decimal("1.00")  # 11 km together does

    def test_a_third_run_the_same_day_adds_nothing(self) -> None:
        harness = Harness()
        harness.submit("6", date(2026, 8, 20))
        harness.submit("5", date(2026, 8, 20))

        harness.submit("8", date(2026, 8, 20))

        assert harness.points() == Decimal("1.00")

    def test_reconciling_with_nothing_to_change_writes_no_row(self) -> None:
        harness = Harness()
        harness.submit("6", date(2026, 8, 20))  # day not yet qualifying

        assert harness.ledger.all_entries() == []

    def test_a_late_submission_earns_nothing(self) -> None:
        harness = Harness()

        harness.submit("12", date(2026, 8, 20), submitted_on=date(2026, 8, 22))

        assert harness.points() == Decimal("0.00")

    def test_one_run_serves_both_activities_at_once(self) -> None:
        """12 km on one day: +12 km toward the 100 km challenge, +1 qualifying day."""
        harness = Harness()

        harness.submit("12", date(2026, 8, 20))

        assert harness.points(DAILY_10) == Decimal("1.00")
        # The distance campaign has no ledger — its progress is derived from the runs.
        assert harness.points(HUNDRED_KM) == Decimal("0")
        from app.domain.campaigns import policy_for

        progress = policy_for(HUNDRED_KM.type).progress(
            HUNDRED_KM, harness.runs.list_by_member(ALICE)
        )
        assert progress.value == Decimal("12.000")


class TestRejectionReconciles:
    def test_rejecting_a_run_that_carried_its_day_removes_the_point(self) -> None:
        """The case per-run reversal could not do: the rejected run never held a ledger
        row, yet it is the reason the day qualified."""
        harness = Harness()
        first = harness.submit("6", date(2026, 8, 20))
        harness.submit("5", date(2026, 8, 20))
        assert harness.points() == Decimal("1.00")

        harness.review(first.id, ReviewStatus.REJECTED)

        assert harness.points() == Decimal("0.00")
        reversal = harness.ledger.all_entries()[-1]
        assert reversal.reason is LedgerReason.REVERSAL
        assert reversal.delta == Decimal("-1.00")

    def test_rejecting_a_run_that_did_not_change_the_outcome_costs_nothing(self) -> None:
        harness = Harness()
        harness.submit("11", date(2026, 8, 20))
        spare = harness.submit("3", date(2026, 8, 20))
        assert harness.points() == Decimal("1.00")

        harness.review(spare.id, ReviewStatus.REJECTED)

        assert harness.points() == Decimal("1.00")

    def test_flagging_a_run_leaves_the_points_alone(self) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))

        harness.review(run.id, ReviewStatus.FLAGGED)

        assert harness.points() == Decimal("1.00")

    def test_every_decision_is_audited(self) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))

        harness.review(run.id, ReviewStatus.REJECTED)

        entry = harness.audit.committed_entries()[-1]
        assert entry.action is AuditAction.REVIEW_RUN
        assert entry.actor_member_id == BOSS
        assert entry.subject_member_id == ALICE
        assert entry.detail == {"run_id": str(run.id), "decision": "rejected"}

    def test_an_admin_can_review(self) -> None:
        """Deciding runs is the work the club has helpers for. The points move exactly as
        they do for the superuser — same reconciliation, same route."""
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))

        harness.review(run.id, ReviewStatus.REJECTED, actor_id=ADMIN)

        assert harness.points() == Decimal("0.00")

    def test_an_admins_decision_is_audited_under_their_own_name(self) -> None:
        """Three people can decide runs now, so "who rejected this?" has to have an
        answer that is not just "an admin"."""
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))

        harness.review(run.id, ReviewStatus.REJECTED, actor_id=ADMIN)

        entry = harness.audit.committed_entries()[-1]
        assert entry.action is AuditAction.REVIEW_RUN
        assert entry.actor_member_id == ADMIN

    def test_an_ordinary_member_cannot_review(self) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))

        with pytest.raises(NotAuthorized):
            harness.review(run.id, ReviewStatus.REJECTED, actor_id=ALICE)

        assert harness.points() == Decimal("1.00")
        assert harness.audit.committed_entries() == []

    def test_reviewing_a_run_that_does_not_exist_is_refused(self) -> None:
        harness = Harness()

        with pytest.raises(RunNotFound):
            harness.review(uuid4(), ReviewStatus.REJECTED)

    def test_the_account_lock_is_taken_before_any_reconciliation(self) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))
        harness.ledger.serialized.clear()

        harness.review(run.id, ReviewStatus.REJECTED)

        assert (ALICE, DAILY_10.id) in harness.ledger.serialized


class TestLinearCampaignsAreUnchanged:
    """Reconciliation has to produce exactly what per-run crediting produced, or the
    redeem tests written against the old behaviour would be a lie."""

    REDEEM = Campaign.create(
        code="rewards", name="Run for rewards", type=CampaignType.REDEEM_REWARD,
        starts_on=date(2026, 8, 15), ends_on=date(2026, 9, 30),
        config={"points_per_km": 2},
    )

    def test_points_accrue_per_kilometre_as_before(self) -> None:
        harness = Harness(campaigns=[self.REDEEM])

        harness.submit("5.25", date(2026, 8, 20))

        assert harness.points(self.REDEEM) == Decimal("10.50")

    def test_a_second_run_adds_to_it(self) -> None:
        harness = Harness(campaigns=[self.REDEEM])
        harness.submit("5.25", date(2026, 8, 20))

        harness.submit("4.75", date(2026, 8, 21))

        assert harness.points(self.REDEEM) == Decimal("20.00")

    def test_rejecting_one_run_takes_back_exactly_its_points(self) -> None:
        harness = Harness(campaigns=[self.REDEEM])
        first = harness.submit("5.25", date(2026, 8, 20))
        harness.submit("4.75", date(2026, 8, 21))

        harness.review(first.id, ReviewStatus.REJECTED)

        assert harness.points(self.REDEEM) == Decimal("9.50")


class TestClosedCampaignsStillReconcile:
    """`is_active` says whether a campaign accepts new work — not whether its points are
    final. A run rejected after the activity closed must still cost its points."""

    def test_rejecting_after_the_campaign_is_closed_still_takes_the_points_back(
        self,
    ) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))
        assert harness.points() == Decimal("1.00")

        harness.close(DAILY_10)
        harness.review(run.id, ReviewStatus.REJECTED)

        assert harness.points() == Decimal("0.00")

    def test_approving_after_the_campaign_is_closed_still_credits(self) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))
        harness.review(run.id, ReviewStatus.REJECTED)
        assert harness.points() == Decimal("0.00")

        harness.close(DAILY_10)
        harness.review(run.id, ReviewStatus.OK)

        assert harness.points() == Decimal("1.00")

    def test_a_closed_unrelated_campaign_reconciles_to_nothing(self) -> None:
        """Iterating every campaign is safe: ones the run has nothing to do with have a
        target and a credited total of zero, so no row is written."""
        last_year = Campaign.create(
            code="old", name="Last year", type=CampaignType.DAILY_THRESHOLD_REWARD,
            starts_on=date(2025, 8, 15), ends_on=date(2025, 9, 30),
            config={
                "qualifying_km": 10, "points_per_qualifying_day": 1, "submit_within_days": 1
            },
            is_active=False,
        )
        harness = Harness(campaigns=[HUNDRED_KM, DAILY_10, last_year])
        run = harness.submit("11", date(2026, 8, 20))

        harness.review(run.id, ReviewStatus.REJECTED)

        assert harness.points(last_year) == Decimal("0")
        assert [e.campaign_id for e in harness.ledger.all_entries()] == [
            DAILY_10.id,
            DAILY_10.id,
        ]


class TestReReview:
    """A decision can be changed. Reconciliation has to survive that."""

    def test_reject_then_approve_credits_the_points_again(self) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))

        harness.review(run.id, ReviewStatus.REJECTED)
        assert harness.points() == Decimal("0.00")

        harness.review(run.id, ReviewStatus.OK)

        assert harness.points() == Decimal("1.00")

    def test_flipping_repeatedly_always_lands_on_the_right_balance(self) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))

        for decision, expected in [
            (ReviewStatus.REJECTED, "0.00"),
            (ReviewStatus.OK, "1.00"),
            (ReviewStatus.REJECTED, "0.00"),
            (ReviewStatus.FLAGGED, "1.00"),
        ]:
            harness.review(run.id, decision)
            assert harness.points() == Decimal(expected)

    def test_reviewing_to_the_same_decision_writes_nothing_new(self) -> None:
        harness = Harness()
        run = harness.submit("11", date(2026, 8, 20))
        before = len(harness.ledger.all_entries())

        harness.review(run.id, ReviewStatus.OK)

        assert len(harness.ledger.all_entries()) == before
