"""What the superuser is managing: every campaign, and every reward in one of them.

Separate from the member-facing `list_rewards` because the two ask different questions.
A member asks "what can I get?" and sees the active catalogue with their balance beside
it. Whoever manages the catalogue asks "what is in it?" and has to see the retired
entries too — rewards are never deleted, only withdrawn, and a withdrawn one that
vanished from this screen would look deleted.
"""

from __future__ import annotations

from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.reward_repository import RewardRepository
from app.domain.campaign import Campaign
from app.domain.entities import MemberRole
from app.domain.errors import MemberNotFound, NotAuthorized
from app.domain.redemption import Reward


def _require_superuser(members: MemberRepository, actor_id: UUID) -> None:
    actor = members.get(actor_id)
    if actor is None:
        raise MemberNotFound(str(actor_id))
    if actor.role is not MemberRole.SUPERUSER:
        raise NotAuthorized("superuser only")


class ListAdminCampaigns:
    def __init__(self, members: MemberRepository, campaigns: CampaignRepository) -> None:
        self._members = members
        self._campaigns = campaigns

    def execute(self, actor_id: UUID) -> list[Campaign]:
        _require_superuser(self._members, actor_id)
        # Closed campaigns included: last year's is still something to look at, and a
        # correction to a finished activity still has to be possible.
        return self._campaigns.list_all()


class ListAdminRewards:
    def __init__(self, members: MemberRepository, rewards: RewardRepository) -> None:
        self._members = members
        self._rewards = rewards

    def execute(self, actor_id: UUID, campaign_id: UUID) -> list[Reward]:
        _require_superuser(self._members, actor_id)
        return self._rewards.list_for_campaign(campaign_id)
