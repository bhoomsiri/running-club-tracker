"""Spending points on rewards — one of the club's two activities this year.

The endpoint is deliberately thin. Everything that makes redeeming safe (the reward row
lock, the per-account advisory lock, the balance check and the two writes in one
transaction) lives in the use case and its UnitOfWork, so it cannot be bypassed by
adding another caller later.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_member_id, get_list_rewards_uc, get_redeem_reward_uc
from app.api.schemas import CampaignRewardsResponse, RedemptionResponse
from app.application.use_cases.list_rewards import ListRewards
from app.application.use_cases.redeem_reward import RedeemReward, RedeemRewardCommand

router = APIRouter(prefix="/rewards", tags=["rewards"])


@router.get("", response_model=list[CampaignRewardsResponse])
def list_rewards(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[ListRewards, Depends(get_list_rewards_uc)],
) -> list[CampaignRewardsResponse]:
    # The catalogue always comes with the caller's own balance beside it.
    return [CampaignRewardsResponse.from_catalogue(c) for c in use_case.execute(member_id)]


@router.post(
    "/{reward_id}/redeem",
    response_model=RedemptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def redeem_reward(
    reward_id: UUID,
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[RedeemReward, Depends(get_redeem_reward_uc)],
) -> RedemptionResponse:
    # Points are spent from the caller's own balance: member_id comes from the token,
    # so there is no way to redeem against somebody else's points.
    # InsufficientPoints / OutOfStock / RewardUnavailable all map to 409 in api/errors.py.
    redemption = use_case.execute(
        RedeemRewardCommand(member_id=member_id, reward_id=reward_id)
    )
    return RedemptionResponse.from_entity(redemption)
