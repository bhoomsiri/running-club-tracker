"""Run to earn points, spend points on rewards.

config: {"points_per_km": 1}

This policy says only how many points a run EARNS. What a member currently holds is
SUM(delta) over the ledger, which includes what they have already spent — so a balance
is never computed from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_DOWN, Decimal

from app.domain.campaign import Campaign, CampaignProgress
from app.domain.entities import RunEntry

POINTS = Decimal("0.01")


class RedeemRewardPolicy:
    required_config = ("points_per_km",)
    tracks_points = True

    def contribution(self, campaign: Campaign, run: RunEntry) -> Decimal:
        rate = campaign.required_decimal("points_per_km")
        # Round DOWN: never credit a point that wasn't fully earned.
        return (run.distance_km * rate).quantize(POINTS, rounding=ROUND_DOWN)

    def progress(self, campaign: Campaign, runs: Sequence[RunEntry]) -> CampaignProgress:
        earned = sum(
            (self.contribution(campaign, r) for r in runs if campaign.contains(r.run_date)),
            start=Decimal("0"),
        )
        return CampaignProgress(
            campaign_id=campaign.id,
            value=earned,
            unit="points",
            target=None,  # earning has no finish line
            completed=False,
        )
