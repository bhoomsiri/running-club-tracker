"""Run at least N km in a day, earn a point for that day.

config: {"qualifying_km": 10, "points_per_qualifying_day": 1, "submit_within_days": 1}

Two things make this format different from the linear ones, and they are why earning
had to become a reconciliation rather than a per-run credit:

  - the unit that earns is a **day**, not a run. Three runs of 4 km each qualify the day
    together; none of them qualifies it alone, so no single run can carry the points.
  - a run submitted too late doesn't count, so the same run can be worth a point or
    nothing depending on when it arrived.

Filtering out rejected runs is the caller's job. This policy never sees `review_status`:
it is handed the runs that count and adds them up.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from app.domain.campaign import Campaign, CampaignProgress
from app.domain.entities import RunEntry

POINTS = Decimal("0.01")


class DailyThresholdRewardPolicy:
    required_config = (
        "qualifying_km",
        "points_per_qualifying_day",
        "submit_within_days",
    )
    tracks_points = True

    def contribution(self, campaign: Campaign, run: RunEntry) -> Decimal:
        """What this run adds to ITS DAY's total — not points.

        A run's point value cannot be known in isolation here (the day it belongs to
        might be carried over the line by another run), so points come only from
        `progress()`.
        """
        return run.distance_km

    def progress(self, campaign: Campaign, runs: Sequence[RunEntry]) -> CampaignProgress:
        qualifying_km = campaign.required_decimal("qualifying_km")
        points_per_day = campaign.required_decimal("points_per_qualifying_day")
        submit_within_days = int(campaign.required_decimal("submit_within_days"))

        totals: dict[date, Decimal] = defaultdict(Decimal)
        for run in runs:
            if not campaign.contains(run.run_date):
                continue
            if run.created_at.date() > run.run_date + timedelta(days=submit_within_days):
                # Submitted too late: the run happened, but it earns nothing.
                continue
            totals[run.run_date] += run.distance_km

        qualifying_days = sum(1 for total in totals.values() if total >= qualifying_km)

        return CampaignProgress(
            campaign_id=campaign.id,
            value=(points_per_day * qualifying_days).quantize(POINTS),
            unit="points",
            target=None,  # earning has no finish line
            completed=False,
        )
