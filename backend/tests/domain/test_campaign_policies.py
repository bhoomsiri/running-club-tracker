"""Policies are pure functions — test them directly, no fakes needed."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.campaign import Campaign, CampaignType
from app.domain.campaigns import CumulativeDistancePolicy, RedeemRewardPolicy, policy_for
from app.domain.entities import RunEntry, RunSource
from app.domain.errors import InvalidCampaignError, UnknownCampaignType

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
MEMBER = uuid4()


def make_campaign(type: CampaignType, **config: object) -> Campaign:
    return Campaign.create(
        code=f"c-{type}",
        name="test",
        type=type,
        starts_on=date(2026, 1, 1),
        ends_on=date(2026, 12, 31),
        config=config,
    )


def run(km: str, on: date = date(2026, 6, 1)) -> RunEntry:
    return RunEntry.create(
        member_id=MEMBER,
        distance_km=Decimal(km),
        duration_seconds=1800,
        run_date=on,
        evidence_key="k",
        evidence_sha256="a" * 64,
        source=RunSource.APP_SCREENSHOT,
        now=NOW,
    )


class TestRegistry:
    def test_each_type_resolves_to_its_policy(self) -> None:
        assert isinstance(policy_for(CampaignType.CUMULATIVE_DISTANCE), CumulativeDistancePolicy)
        assert isinstance(policy_for(CampaignType.REDEEM_REWARD), RedeemRewardPolicy)

    def test_every_campaign_type_has_a_policy(self) -> None:
        # Adding a CampaignType without registering a policy fails here, not in prod.
        for campaign_type in CampaignType:
            assert policy_for(campaign_type) is not None

    def test_unregistered_type_raises(self) -> None:
        with pytest.raises(UnknownCampaignType):
            policy_for("streak")  # type: ignore[arg-type]


class TestCumulativeDistance:
    def test_progress_sums_distance_in_the_window(self) -> None:
        campaign = make_campaign(CampaignType.CUMULATIVE_DISTANCE, target_km=100)
        runs = [run("5.250"), run("10.500"), run("4.250")]

        progress = CumulativeDistancePolicy().progress(campaign, runs)

        assert progress.value == Decimal("20.000")
        assert progress.unit == "km"
        assert progress.target == Decimal("100")
        assert progress.completed is False
        assert progress.percent == Decimal("20.0")

    def test_runs_outside_the_window_are_ignored(self) -> None:
        campaign = make_campaign(CampaignType.CUMULATIVE_DISTANCE, target_km=100)
        runs = [run("5.000"), run("42.000", on=date(2025, 12, 31))]

        assert CumulativeDistancePolicy().progress(campaign, runs).value == Decimal("5.000")

    def test_reaching_the_target_completes_it(self) -> None:
        campaign = make_campaign(CampaignType.CUMULATIVE_DISTANCE, target_km=10)

        progress = CumulativeDistancePolicy().progress(campaign, [run("10.000")])

        assert progress.completed is True
        assert progress.percent == Decimal("100.0")

    def test_percent_is_capped_at_100(self) -> None:
        campaign = make_campaign(CampaignType.CUMULATIVE_DISTANCE, target_km=10)

        progress = CumulativeDistancePolicy().progress(campaign, [run("25")])
        assert progress.percent == Decimal("100.0")

    def test_no_runs_is_zero_not_an_error(self) -> None:
        campaign = make_campaign(CampaignType.CUMULATIVE_DISTANCE, target_km=100)

        assert CumulativeDistancePolicy().progress(campaign, []).value == Decimal("0.000")

    def test_missing_target_km_is_a_config_error(self) -> None:
        campaign = make_campaign(CampaignType.CUMULATIVE_DISTANCE)

        with pytest.raises(InvalidCampaignError):
            CumulativeDistancePolicy().progress(campaign, [run("5")])


class TestRedeemReward:
    def test_points_are_earned_per_km(self) -> None:
        campaign = make_campaign(CampaignType.REDEEM_REWARD, points_per_km=2)

        assert RedeemRewardPolicy().contribution(campaign, run("5.500")) == Decimal("11.00")

    def test_partial_points_round_down_never_up(self) -> None:
        campaign = make_campaign(CampaignType.REDEEM_REWARD, points_per_km="0.5")

        # 5.255 km * 0.5 = 2.6275 -> 2.62, not 2.63: never credit an unearned point.
        assert RedeemRewardPolicy().contribution(campaign, run("5.255")) == Decimal("2.62")

    def test_float_config_does_not_leak_binary_error(self) -> None:
        campaign = make_campaign(CampaignType.REDEEM_REWARD, points_per_km=0.1)

        # 10 * 0.1 is exactly 1.00 here; with float maths it would be 1.0000000000000002.
        assert RedeemRewardPolicy().contribution(campaign, run("10")) == Decimal("1.00")

    def test_progress_totals_earned_points_with_no_target(self) -> None:
        campaign = make_campaign(CampaignType.REDEEM_REWARD, points_per_km=1)

        progress = RedeemRewardPolicy().progress(campaign, [run("5.250"), run("4.750")])

        assert progress.value == Decimal("10.00")
        assert progress.unit == "points"
        assert progress.target is None
        assert progress.percent is None

    def test_zero_or_negative_rate_is_a_config_error(self) -> None:
        campaign = make_campaign(CampaignType.REDEEM_REWARD, points_per_km=0)

        with pytest.raises(InvalidCampaignError):
            RedeemRewardPolicy().contribution(campaign, run("5"))
