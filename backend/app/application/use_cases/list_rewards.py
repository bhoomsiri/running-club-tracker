"""The reward catalogue a member sees, with their balance beside it.

The balance travels with the rewards deliberately: "what can I afford?" is the only
question this screen exists to answer, and computing it on the client from two separate
calls invites showing a stale balance next to a fresh price.

Which campaigns appear is decided by the policy (`tracks_points`), not by an `if` on
campaign type — a future format that pays points shows up here for free.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.reward_repository import RewardRepository
from app.domain.campaign import Campaign
from app.domain.campaigns import policy_for
from app.domain.redemption import Reward


@dataclass(frozen=True)
class CampaignRewards:
    campaign: Campaign
    points_balance: Decimal
    rewards: list[Reward]


class ListRewards:
    def __init__(
        self,
        campaigns: CampaignRepository,
        rewards: RewardRepository,
        ledger: PointsLedgerRepository,
    ) -> None:
        self._campaigns = campaigns
        self._rewards = rewards
        self._ledger = ledger

    def execute(self, member_id: UUID) -> list[CampaignRewards]:
        catalogue = []
        for campaign in self._campaigns.list_active():
            if not policy_for(campaign.type).tracks_points:
                continue
            catalogue.append(
                CampaignRewards(
                    campaign=campaign,
                    # SUM(delta), the spendable balance — not the total ever earned.
                    points_balance=self._ledger.balance(member_id, campaign.id),
                    rewards=self._rewards.list_active_for_campaign(campaign.id),
                )
            )
        return catalogue
