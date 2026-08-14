"""The 100 km challenge: every kilometre counts toward a fixed target.

config: {"target_km": 100}
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.domain.campaign import Campaign, CampaignProgress
from app.domain.entities import RunEntry

KM = Decimal("0.001")


class CumulativeDistancePolicy:
    required_config = ("target_km",)
    tracks_points = False  # distance only; nothing reaches the ledger

    def contribution(self, campaign: Campaign, run: RunEntry) -> Decimal:
        return run.distance_km

    def progress(self, campaign: Campaign, runs: Sequence[RunEntry]) -> CampaignProgress:
        target = campaign.required_decimal("target_km")
        total = sum(
            (self.contribution(campaign, r) for r in runs if campaign.contains(r.run_date)),
            start=Decimal("0"),
        ).quantize(KM)
        return CampaignProgress(
            campaign_id=campaign.id,
            value=total,
            unit="km",
            target=target,
            completed=total >= target,
        )
