"""กิจกรรม 2: at least 10 km in a day, submitted by the next day, earns a point."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.campaign import Campaign, CampaignType
from app.domain.campaigns import DailyThresholdRewardPolicy, policy_for
from app.domain.entities import ReviewStatus, RunEntry, RunSource
from app.domain.errors import InvalidCampaignError

MEMBER = uuid4()
CAMPAIGN = Campaign.create(
    code="daily10", name="วันละ 10 กม.", type=CampaignType.DAILY_THRESHOLD_REWARD,
    starts_on=date(2026, 8, 15), ends_on=date(2026, 9, 30),
    config={"qualifying_km": 10, "points_per_qualifying_day": 1, "submit_within_days": 1},
)
POLICY = DailyThresholdRewardPolicy()


def run(km: str, ran_on: date, submitted_on: date | None = None) -> RunEntry:
    submitted = submitted_on or ran_on
    return RunEntry(
        id=uuid4(), member_id=MEMBER, distance_km=Decimal(km), duration_seconds=1800,
        run_date=ran_on, evidence_key="k", evidence_sha256="a" * 64,
        source=RunSource.APP_SCREENSHOT,
        review_status=ReviewStatus.OK,
        created_at=datetime.combine(submitted, datetime.min.time(), tzinfo=UTC),
    )


def points(*runs: RunEntry) -> Decimal:
    return POLICY.progress(CAMPAIGN, list(runs)).value


class TestQualifyingDays:
    def test_two_runs_in_one_day_add_up_to_qualify_it(self) -> None:
        """6 + 5 km on the same day is one qualifying day — the unit is the DAY."""
        assert points(run("6", date(2026, 8, 20)), run("5", date(2026, 8, 20))) == Decimal("1.00")

    def test_a_third_run_the_same_day_adds_nothing(self) -> None:
        day = date(2026, 8, 20)

        assert points(run("6", day), run("5", day), run("8", day)) == Decimal("1.00")

    def test_a_day_short_of_the_threshold_earns_nothing(self) -> None:
        day = date(2026, 8, 20)

        assert points(run("6", day), run("3.9", day)) == Decimal("0.00")

    def test_exactly_the_threshold_qualifies(self) -> None:
        assert points(run("10", date(2026, 8, 20))) == Decimal("1.00")

    def test_each_qualifying_day_earns_its_own_point(self) -> None:
        assert points(
            run("10", date(2026, 8, 20)),
            run("12", date(2026, 8, 21)),
            run("4", date(2026, 8, 22)),  # short
        ) == Decimal("2.00")

    def test_no_runs_is_zero(self) -> None:
        assert points() == Decimal("0.00")


class TestSubmissionDeadline:
    def test_submitting_the_next_day_still_counts(self) -> None:
        assert points(run("10", date(2026, 8, 20), submitted_on=date(2026, 8, 21))) == Decimal(
            "1.00"
        )

    def test_submitting_two_days_later_does_not(self) -> None:
        assert points(run("10", date(2026, 8, 20), submitted_on=date(2026, 8, 22))) == Decimal(
            "0.00"
        )

    def test_a_late_run_cannot_carry_its_day_over_the_line(self) -> None:
        """The day still has 6 km that counts; the late 5 km is simply not there."""
        day = date(2026, 8, 20)

        assert points(run("6", day), run("5", day, submitted_on=date(2026, 8, 25))) == Decimal(
            "0.00"
        )


class TestWindow:
    def test_a_run_before_the_campaign_starts_does_not_count(self) -> None:
        assert points(run("10", date(2026, 8, 14))) == Decimal("0.00")

    def test_a_run_after_it_ends_does_not_count(self) -> None:
        assert points(run("10", date(2026, 10, 1))) == Decimal("0.00")

    def test_the_first_and_last_day_do_count(self) -> None:
        assert points(run("10", date(2026, 8, 15)), run("10", date(2026, 9, 30))) == Decimal(
            "2.00"
        )


class TestPolicyShape:
    def test_it_is_registered_and_tracks_points(self) -> None:
        policy = policy_for(CampaignType.DAILY_THRESHOLD_REWARD)

        assert isinstance(policy, DailyThresholdRewardPolicy)
        assert policy.tracks_points is True

    def test_progress_reports_points_with_no_finish_line(self) -> None:
        progress = POLICY.progress(CAMPAIGN, [run("10", date(2026, 8, 20))])

        assert progress.unit == "points"
        assert progress.target is None
        assert progress.percent is None

    def test_missing_config_is_a_config_error(self) -> None:
        campaign = Campaign.create(
            code="broken", name="broken", type=CampaignType.DAILY_THRESHOLD_REWARD,
            starts_on=date(2026, 8, 15), ends_on=date(2026, 9, 30), config={},
        )

        with pytest.raises(InvalidCampaignError):
            POLICY.progress(campaign, [run("10", date(2026, 8, 20))])

    def test_a_custom_points_per_day_is_honoured(self) -> None:
        campaign = Campaign.create(
            code="daily10x3", name="x3", type=CampaignType.DAILY_THRESHOLD_REWARD,
            starts_on=date(2026, 8, 15), ends_on=date(2026, 9, 30),
            config={
                "qualifying_km": 10, "points_per_qualifying_day": 3, "submit_within_days": 1
            },
        )

        assert POLICY.progress(campaign, [run("10", date(2026, 8, 20))]).value == Decimal("3.00")
