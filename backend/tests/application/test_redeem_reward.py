"""The must-cover use case: redeeming can never double-spend or go negative."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.redeem_reward import RedeemReward, RedeemRewardCommand
from app.domain.errors import InsufficientPoints, OutOfStock, RewardUnavailable
from app.domain.redemption import LedgerReason, PointsEntry, Reward
from tests.fakes.fake_uow import (
    FakePointsLedgerRepository,
    FakeRewardRepository,
    FakeUnitOfWork,
    FixedClock,
)

NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
MEMBER = UUID("11111111-1111-1111-1111-111111111111")
CAMPAIGN = UUID("22222222-2222-2222-2222-222222222222")


def make_reward(*, cost: str = "50", stock: int = 1, is_active: bool = True) -> Reward:
    return Reward(
        id=uuid4(),
        campaign_id=CAMPAIGN,
        name="Club shirt",
        points_cost=Decimal(cost),
        stock=stock,
        is_active=is_active,
    )


def earned(points: str) -> PointsEntry:
    return PointsEntry.for_run(
        member_id=MEMBER,
        campaign_id=CAMPAIGN,
        points=Decimal(points),
        run_entry_id=uuid4(),
        now=NOW,
    )


def build(reward: Reward, *entries: PointsEntry) -> tuple[RedeemReward, FakeUnitOfWork]:
    uow = FakeUnitOfWork(
        rewards=FakeRewardRepository([reward]),
        ledger=FakePointsLedgerRepository(list(entries)),
        clock=FixedClock(NOW),
    )
    return RedeemReward(uow), uow


def test_redeem_writes_a_negative_ledger_row_and_decrements_stock() -> None:
    reward = make_reward(cost="50", stock=2)
    uc, uow = build(reward, earned("60"))

    redemption = uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))

    assert redemption.points_spent == Decimal("50.00")
    assert uow.committed
    assert uow.ledger.balance(MEMBER, CAMPAIGN) == Decimal("10.00")
    assert uow.rewards.get(reward.id).stock == 1  # type: ignore[union-attr]
    spend = [e for e in uow.ledger.all_entries() if e.reason is LedgerReason.REDEEMED]
    assert len(spend) == 1
    assert spend[0].delta == Decimal("-50.00")
    assert spend[0].redemption_id == redemption.id


def test_reward_row_is_locked_before_anything_is_read_or_written() -> None:
    reward = make_reward()
    uc, uow = build(reward, earned("60"))

    uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))

    assert uow.rewards.locked == [reward.id]


def test_balance_below_cost_is_rejected_and_nothing_is_written() -> None:
    reward = make_reward(cost="50")
    uc, uow = build(reward, earned("49.99"))

    with pytest.raises(InsufficientPoints):
        uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))

    assert not uow.committed
    assert uow.rolled_back
    assert uow.ledger.balance(MEMBER, CAMPAIGN) == Decimal("49.99")
    assert uow.rewards.get(reward.id).stock == 1  # type: ignore[union-attr]
    assert uow.redemptions.list_by_member(MEMBER) == []


def test_second_redeem_cannot_spend_points_already_spent() -> None:
    """The double-spend case: enough points for ONE reward, redeemed twice in a row."""
    reward = make_reward(cost="50", stock=5)
    uc, uow = build(reward, earned("60"))

    uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))

    with pytest.raises(InsufficientPoints):
        uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))

    # Balance never goes negative, and only the first redemption survived.
    assert uow.ledger.balance(MEMBER, CAMPAIGN) == Decimal("10.00")
    assert uow.ledger.balance(MEMBER, CAMPAIGN) >= 0
    assert len(uow.redemptions.list_by_member(MEMBER)) == 1
    assert uow.rewards.get(reward.id).stock == 4  # type: ignore[union-attr]


def test_last_item_cannot_be_oversold() -> None:
    reward = make_reward(cost="10", stock=1)
    uc, uow = build(reward, earned("100"))

    uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))
    assert uow.rewards.get(reward.id).stock == 0  # type: ignore[union-attr]

    with pytest.raises(OutOfStock):
        uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))

    assert len(uow.redemptions.list_by_member(MEMBER)) == 1
    assert uow.ledger.balance(MEMBER, CAMPAIGN) == Decimal("90.00")


def test_inactive_reward_is_rejected() -> None:
    reward = make_reward(is_active=False)
    uc, _ = build(reward, earned("100"))

    with pytest.raises(RewardUnavailable):
        uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))


def test_unknown_reward_is_rejected() -> None:
    uc, _ = build(make_reward(), earned("100"))

    with pytest.raises(RewardUnavailable):
        uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=uuid4()))


def test_another_members_points_are_not_spendable() -> None:
    """Balance is scoped to the caller's member_id — one member cannot spend another's."""
    reward = make_reward(cost="50")
    other_member = uuid4()
    uc, uow = build(reward, earned("100"))

    with pytest.raises(InsufficientPoints):
        uc.execute(RedeemRewardCommand(member_id=other_member, reward_id=reward.id))

    assert uow.ledger.balance(MEMBER, CAMPAIGN) == Decimal("100.00")


def test_points_from_a_different_campaign_do_not_count() -> None:
    reward = make_reward(cost="50")
    elsewhere = PointsEntry.for_run(
        member_id=MEMBER, campaign_id=uuid4(), points=Decimal("100"),
        run_entry_id=uuid4(), now=NOW,
    )
    uc, _ = build(reward, elsewhere)

    with pytest.raises(InsufficientPoints):
        uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))


def test_exact_balance_is_enough() -> None:
    reward = make_reward(cost="50")
    uc, uow = build(reward, earned("50"))

    uc.execute(RedeemRewardCommand(member_id=MEMBER, reward_id=reward.id))

    assert uow.ledger.balance(MEMBER, CAMPAIGN) == Decimal("0.00")
