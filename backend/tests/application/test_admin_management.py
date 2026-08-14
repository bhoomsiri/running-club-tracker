"""Superuser management: campaigns, rewards, and the fulfilment gate."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.manage_campaigns import (
    CreateCampaign,
    CreateCampaignCommand,
    UpdateCampaign,
    UpdateCampaignCommand,
)
from app.application.use_cases.manage_redemptions import (
    CancelRedemption,
    FulfillRedemption,
    RedemptionCommand,
)
from app.application.use_cases.manage_rewards import (
    CreateReward,
    CreateRewardCommand,
    UpdateReward,
    UpdateRewardCommand,
)
from app.domain.audit import AuditAction
from app.domain.campaign import Campaign, CampaignType
from app.domain.entities import (
    Member,
    MemberRole,
    ReviewStatus,
    RunEntry,
    RunSource,
)
from app.domain.errors import (
    InsufficientPoints,
    InvalidCampaignError,
    InvalidRewardError,
    NotAuthorized,
    RedemptionNotPending,
    UnresolvedRuns,
)
from app.domain.redemption import PointsEntry, Redemption, RedemptionStatus, Reward
from tests.fakes.fake_uow import (
    FakeAdminUnitOfWork,
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
BOSS = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
ADMIN = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
ALICE = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

CAMPAIGN = Campaign.create(
    code="daily-10km-2026", name="วันละ 10 กม.", type=CampaignType.DAILY_THRESHOLD_REWARD,
    starts_on=date(2026, 8, 15), ends_on=date(2026, 9, 30),
    config={"qualifying_km": 10, "points_per_qualifying_day": 1, "submit_within_days": 1},
)


def people() -> FakeMemberRepository:
    return FakeMemberRepository(
        [
            Member(id=BOSS, clerk_user_id="c_boss", display_name="Boss",
                   role=MemberRole.SUPERUSER, created_at=NOW),
            Member(id=ADMIN, clerk_user_id="c_admin", display_name="Admin",
                   role=MemberRole.ADMIN, created_at=NOW),
            Member(id=ALICE, clerk_user_id="c_alice", display_name="Alice",
                   role=MemberRole.MEMBER, created_at=NOW),
        ]
    )


class Harness:
    def __init__(
        self,
        *,
        campaigns: list[Campaign] | None = None,
        rewards: list[Reward] | None = None,
        redemptions: list[Redemption] | None = None,
        ledger: list[PointsEntry] | None = None,
        runs: list[RunEntry] | None = None,
    ) -> None:
        self.members = people()
        self.campaigns = FakeCampaignRepository(campaigns if campaigns is not None else [CAMPAIGN])
        self.rewards = FakeRewardRepository(rewards or [])
        self.redemptions = FakeRedemptionRepository(redemptions or [])
        self.ledger = FakePointsLedgerRepository(ledger or [])
        self.runs = FakeRunRepository(runs or [])
        self.audit = FakeAuditRepository()

    def uow(self) -> FakeAdminUnitOfWork:
        return FakeAdminUnitOfWork(
            members=self.members, campaigns=self.campaigns, rewards=self.rewards,
            redemptions=self.redemptions, ledger=self.ledger, runs=self.runs,
            audit=self.audit, clock=FixedClock(NOW),
        )

    def actions(self) -> list[AuditAction]:
        return [e.action for e in self.audit.committed_entries()]


def a_run(status: ReviewStatus = ReviewStatus.OK) -> RunEntry:
    return RunEntry(
        id=uuid4(), member_id=ALICE, distance_km=Decimal("11"), duration_seconds=1800,
        run_date=date(2026, 8, 20), evidence_key="k", evidence_sha256="a" * 64,
        source=RunSource.APP_SCREENSHOT, review_status=status, created_at=NOW,
    )


def a_reward(stock: int = 3, cost: str = "5") -> Reward:
    return Reward(
        id=uuid4(), campaign_id=CAMPAIGN.id, name="เสื้อวิ่ง",
        points_cost=Decimal(cost), stock=stock, is_active=True,
    )


def a_redemption(reward: Reward, status: RedemptionStatus = RedemptionStatus.PENDING) -> Redemption:
    return Redemption(
        id=uuid4(), member_id=ALICE, reward_id=reward.id, campaign_id=CAMPAIGN.id,
        points_spent=reward.points_cost, status=status, created_at=NOW,
    )


def earned(points: str) -> PointsEntry:
    return PointsEntry.for_run(
        member_id=ALICE, campaign_id=CAMPAIGN.id, points=Decimal(points),
        run_entry_id=uuid4(), now=NOW,
    )


def spent(redemption: Redemption) -> PointsEntry:
    return PointsEntry.for_redemption(redemption=redemption, now=NOW)


class TestCampaignCrud:
    def test_the_superuser_can_create_one_and_it_is_audited(self) -> None:
        harness = Harness(campaigns=[])

        campaign = CreateCampaign(harness.uow()).execute(
            CreateCampaignCommand(
                actor_id=BOSS, code="new-2027", name="ปีหน้า",
                type=CampaignType.CUMULATIVE_DISTANCE,
                starts_on=date(2027, 1, 1), ends_on=date(2027, 3, 31),
                config={"target_km": 50},
            )
        )

        assert campaign.code == "new-2027"
        assert harness.actions() == [AuditAction.CREATE_CAMPAIGN]

    def test_an_admin_cannot(self) -> None:
        harness = Harness(campaigns=[])

        with pytest.raises(NotAuthorized):
            CreateCampaign(harness.uow()).execute(
                CreateCampaignCommand(
                    actor_id=ADMIN, code="x", name="x",
                    type=CampaignType.CUMULATIVE_DISTANCE,
                    starts_on=date(2027, 1, 1), ends_on=date(2027, 3, 31),
                    config={"target_km": 50},
                )
            )

        assert harness.campaigns.list_all() == []
        assert harness.audit.committed_entries() == []

    def test_a_member_cannot(self) -> None:
        harness = Harness(campaigns=[])

        with pytest.raises(NotAuthorized):
            CreateCampaign(harness.uow()).execute(
                CreateCampaignCommand(
                    actor_id=ALICE, code="x", name="x",
                    type=CampaignType.CUMULATIVE_DISTANCE,
                    starts_on=date(2027, 1, 1), ends_on=date(2027, 3, 31),
                    config={"target_km": 50},
                )
            )

    def test_config_missing_what_the_policy_needs_is_refused(self) -> None:
        """The policy declares its required keys, so a broken campaign is refused at the
        door rather than failing later when someone opens their dashboard."""
        harness = Harness(campaigns=[])

        with pytest.raises(InvalidCampaignError):
            CreateCampaign(harness.uow()).execute(
                CreateCampaignCommand(
                    actor_id=BOSS, code="broken", name="broken",
                    type=CampaignType.DAILY_THRESHOLD_REWARD,
                    starts_on=date(2027, 1, 1), ends_on=date(2027, 3, 31),
                    config={"qualifying_km": 10},  # missing two keys
                )
            )

    def test_a_duplicate_code_is_refused(self) -> None:
        harness = Harness()

        with pytest.raises(InvalidCampaignError, match="already used"):
            CreateCampaign(harness.uow()).execute(
                CreateCampaignCommand(
                    actor_id=BOSS, code=CAMPAIGN.code, name="dup",
                    type=CampaignType.CUMULATIVE_DISTANCE,
                    starts_on=date(2027, 1, 1), ends_on=date(2027, 3, 31),
                    config={"target_km": 10},
                )
            )

    def test_renaming_is_allowed_and_audited(self) -> None:
        harness = Harness()

        updated = UpdateCampaign(harness.uow()).execute(
            UpdateCampaignCommand(actor_id=BOSS, campaign_id=CAMPAIGN.id, name="ชื่อใหม่")
        )

        assert updated.name == "ชื่อใหม่"
        assert harness.actions() == [AuditAction.UPDATE_CAMPAIGN]

    def test_closing_a_campaign_is_allowed(self) -> None:
        harness = Harness()

        updated = UpdateCampaign(harness.uow()).execute(
            UpdateCampaignCommand(actor_id=BOSS, campaign_id=CAMPAIGN.id, is_active=False)
        )

        assert updated.is_active is False

    def test_moving_the_dates_after_points_were_awarded_is_refused(self) -> None:
        """Narrowing the window later is how a member loses points they were told they
        had."""
        harness = Harness(ledger=[earned("2")])

        with pytest.raises(InvalidCampaignError, match="points have already"):
            UpdateCampaign(harness.uow()).execute(
                UpdateCampaignCommand(
                    actor_id=BOSS, campaign_id=CAMPAIGN.id, ends_on=date(2026, 9, 1)
                )
            )

    def test_moving_the_dates_after_runs_were_submitted_is_refused(self) -> None:
        harness = Harness(runs=[a_run()])

        with pytest.raises(InvalidCampaignError, match="runs have already"):
            UpdateCampaign(harness.uow()).execute(
                UpdateCampaignCommand(
                    actor_id=BOSS, campaign_id=CAMPAIGN.id, starts_on=date(2026, 8, 25)
                )
            )

    def test_an_inverted_window_is_refused(self) -> None:
        harness = Harness()

        with pytest.raises(InvalidCampaignError):
            UpdateCampaign(harness.uow()).execute(
                UpdateCampaignCommand(
                    actor_id=BOSS, campaign_id=CAMPAIGN.id,
                    starts_on=date(2026, 9, 30), ends_on=date(2026, 8, 15),
                )
            )

    def test_there_is_no_way_to_change_the_type(self) -> None:
        """Type decides which policy reads the runs; changing it would reinterpret
        history. The command simply has no field for it."""
        assert not hasattr(
            UpdateCampaignCommand(actor_id=BOSS, campaign_id=CAMPAIGN.id), "type"
        )


class TestRewardCrud:
    def test_creating_a_reward_is_audited(self) -> None:
        harness = Harness()

        reward = CreateReward(harness.uow()).execute(
            CreateRewardCommand(
                actor_id=BOSS, campaign_id=CAMPAIGN.id, name="ขวดน้ำ",
                points_cost=Decimal("5"), stock=10,
            )
        )

        assert reward.name == "ขวดน้ำ"
        assert harness.actions() == [AuditAction.CREATE_REWARD]

    def test_an_admin_cannot_create_one(self) -> None:
        harness = Harness()

        with pytest.raises(NotAuthorized):
            CreateReward(harness.uow()).execute(
                CreateRewardCommand(
                    actor_id=ADMIN, campaign_id=CAMPAIGN.id, name="x",
                    points_cost=Decimal("5"), stock=1,
                )
            )

    def test_a_free_reward_is_refused(self) -> None:
        harness = Harness()

        with pytest.raises(InvalidRewardError):
            CreateReward(harness.uow()).execute(
                CreateRewardCommand(
                    actor_id=BOSS, campaign_id=CAMPAIGN.id, name="x",
                    points_cost=Decimal("0"), stock=1,
                )
            )

    def test_restocking_is_allowed(self) -> None:
        reward = a_reward(stock=0)
        harness = Harness(rewards=[reward])

        updated = UpdateReward(harness.uow()).execute(
            UpdateRewardCommand(actor_id=BOSS, reward_id=reward.id, stock=12)
        )

        assert updated.stock == 12

    def test_retiring_a_reward_keeps_it_but_takes_it_off_the_catalogue(self) -> None:
        reward = a_reward()
        harness = Harness(rewards=[reward], redemptions=[a_redemption(reward)])

        UpdateReward(harness.uow()).execute(
            UpdateRewardCommand(actor_id=BOSS, reward_id=reward.id, is_active=False)
        )

        # Gone from what members can redeem...
        assert harness.rewards.list_active_for_campaign(CAMPAIGN.id) == []
        # ...but the reward row and the redemption pointing at it both survive.
        assert harness.rewards.get(reward.id) is not None
        assert len(harness.redemptions.list_by_member(ALICE)) == 1
        assert harness.actions() == [AuditAction.UPDATE_REWARD]


class TestFulfilmentGate:
    def test_a_clean_redemption_is_fulfilled_and_audited(self) -> None:
        reward = a_reward(cost="5")
        redemption = a_redemption(reward)
        harness = Harness(
            rewards=[reward],
            redemptions=[redemption],
            ledger=[earned("10"), spent(redemption)],
            runs=[a_run()],
        )

        result = FulfillRedemption(harness.uow()).execute(
            RedemptionCommand(actor_id=BOSS, redemption_id=redemption.id)
        )

        assert result.status is RedemptionStatus.FULFILLED
        assert harness.actions() == [AuditAction.FULFILL_REDEMPTION]

    def test_a_negative_balance_blocks_it(self) -> None:
        """A rejected run pulled the balance under after the redemption was made."""
        reward = a_reward(cost="5")
        redemption = a_redemption(reward)
        harness = Harness(
            rewards=[reward], redemptions=[redemption],
            ledger=[earned("2"), spent(redemption)],  # 2 - 5 = -3
            runs=[a_run()],
        )

        with pytest.raises(InsufficientPoints):
            FulfillRedemption(harness.uow()).execute(
                RedemptionCommand(actor_id=BOSS, redemption_id=redemption.id)
            )

        # It stays pending: no separate "hold" mechanism is needed.
        assert harness.redemptions.get(redemption.id).status is RedemptionStatus.PENDING  # type: ignore[union-attr]
        assert harness.audit.committed_entries() == []

    def test_a_run_still_awaiting_review_blocks_it(self) -> None:
        reward = a_reward(cost="5")
        redemption = a_redemption(reward)
        harness = Harness(
            rewards=[reward], redemptions=[redemption],
            ledger=[earned("10"), spent(redemption)],
            runs=[a_run(ReviewStatus.FLAGGED)],
        )

        with pytest.raises(UnresolvedRuns):
            FulfillRedemption(harness.uow()).execute(
                RedemptionCommand(actor_id=BOSS, redemption_id=redemption.id)
            )

    def test_fulfilling_twice_is_refused(self) -> None:
        reward = a_reward()
        redemption = a_redemption(reward, RedemptionStatus.FULFILLED)
        harness = Harness(rewards=[reward], redemptions=[redemption], ledger=[earned("10")])

        with pytest.raises(RedemptionNotPending):
            FulfillRedemption(harness.uow()).execute(
                RedemptionCommand(actor_id=BOSS, redemption_id=redemption.id)
            )

    def test_an_admin_cannot_fulfil(self) -> None:
        reward = a_reward()
        redemption = a_redemption(reward)
        harness = Harness(rewards=[reward], redemptions=[redemption], ledger=[earned("10")])

        with pytest.raises(NotAuthorized):
            FulfillRedemption(harness.uow()).execute(
                RedemptionCommand(actor_id=ADMIN, redemption_id=redemption.id)
            )

    def test_the_account_lock_is_taken_before_the_balance_is_read(self) -> None:
        reward = a_reward()
        redemption = a_redemption(reward)
        harness = Harness(
            rewards=[reward], redemptions=[redemption],
            ledger=[earned("10"), spent(redemption)], runs=[a_run()],
        )

        FulfillRedemption(harness.uow()).execute(
            RedemptionCommand(actor_id=BOSS, redemption_id=redemption.id)
        )

        assert harness.ledger.serialized == [(ALICE, CAMPAIGN.id)]


class TestCancellation:
    def test_cancelling_refunds_the_points_and_restocks_the_item(self) -> None:
        reward = a_reward(stock=2, cost="5")
        redemption = a_redemption(reward)
        harness = Harness(
            rewards=[reward], redemptions=[redemption], ledger=[earned("10"), spent(redemption)]
        )
        assert harness.ledger.balance(ALICE, CAMPAIGN.id) == Decimal("5.00")

        result = CancelRedemption(harness.uow()).execute(
            RedemptionCommand(actor_id=BOSS, redemption_id=redemption.id)
        )

        assert result.status is RedemptionStatus.CANCELLED
        assert harness.ledger.balance(ALICE, CAMPAIGN.id) == Decimal("10.00")  # refunded
        assert harness.rewards.get(reward.id).stock == 3  # type: ignore[union-attr]
        assert harness.actions() == [AuditAction.CANCEL_REDEMPTION]

    def test_the_refund_is_not_mistaken_for_something_earned(self) -> None:
        """`credited_total` drives reconciliation; a refund must not inflate it, or the
        next run would be reconciled back down by the refunded amount."""
        reward = a_reward(cost="5")
        redemption = a_redemption(reward)
        harness = Harness(
            rewards=[reward], redemptions=[redemption], ledger=[earned("10"), spent(redemption)]
        )

        CancelRedemption(harness.uow()).execute(
            RedemptionCommand(actor_id=BOSS, redemption_id=redemption.id)
        )

        assert harness.ledger.credited_total(ALICE, CAMPAIGN.id) == Decimal("10.00")

    def test_cancelling_a_fulfilled_redemption_is_refused(self) -> None:
        reward = a_reward()
        redemption = a_redemption(reward, RedemptionStatus.FULFILLED)
        harness = Harness(rewards=[reward], redemptions=[redemption])

        with pytest.raises(RedemptionNotPending):
            CancelRedemption(harness.uow()).execute(
                RedemptionCommand(actor_id=BOSS, redemption_id=redemption.id)
            )

    def test_a_member_cannot_cancel_their_own_redemption(self) -> None:
        reward = a_reward()
        redemption = a_redemption(reward)
        harness = Harness(rewards=[reward], redemptions=[redemption])

        with pytest.raises(NotAuthorized):
            CancelRedemption(harness.uow()).execute(
                RedemptionCommand(actor_id=ALICE, redemption_id=redemption.id)
            )

        assert harness.ledger.all_entries() == []
