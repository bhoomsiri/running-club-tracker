"""The policy registry — the ONE place campaign type is mapped to behaviour.

Adding next year's activity format:
  1. add a value to CampaignType in domain/campaign.py
  2. add a policy file here implementing contribution() + progress()
  3. add one line to _REGISTRY

Nothing else in the codebase changes. If you find yourself writing
`if campaign.type == ...` anywhere else, that branch belongs here instead.
"""

from app.domain.campaign import CampaignPolicy, CampaignType
from app.domain.campaigns.cumulative_distance import CumulativeDistancePolicy
from app.domain.campaigns.daily_threshold_reward import DailyThresholdRewardPolicy
from app.domain.campaigns.redeem_reward import RedeemRewardPolicy
from app.domain.errors import UnknownCampaignType

_REGISTRY: dict[CampaignType, CampaignPolicy] = {
    CampaignType.CUMULATIVE_DISTANCE: CumulativeDistancePolicy(),
    CampaignType.REDEEM_REWARD: RedeemRewardPolicy(),
    CampaignType.DAILY_THRESHOLD_REWARD: DailyThresholdRewardPolicy(),
    # next year: CampaignType.STREAK: StreakPolicy(),
}


def policy_for(campaign_type: CampaignType) -> CampaignPolicy:
    try:
        return _REGISTRY[campaign_type]
    except KeyError as e:
        raise UnknownCampaignType(str(campaign_type)) from e


__all__ = [
    "CumulativeDistancePolicy",
    "DailyThresholdRewardPolicy",
    "RedeemRewardPolicy",
    "policy_for",
]
