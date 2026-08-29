"""Everything a member sees about themselves, in one read.

Two things this must get right:

  - It is scoped to ONE member_id, which the router takes from the verified token
    (golden rule #2). Nothing here accepts a target id from a request body, so there is
    no way to read someone else's data through this use case.
  - It never branches on `campaign.type`. Each campaign's numbers come from
    `policy_for(campaign.type)`, and whether a balance is relevant is something the
    policy declares (`tracks_points`), not something this file decides.

Health data is included because this is the owner reading their own record — that is
not an admin access, so it is not audited. An admin reading someone else's data is a
different use case, and that one must write an audit_log row.

It IS consent-gated, though, and that gate lives here rather than in the screen that
happens to show it. Consent is the club's basis for processing health data at all, and
handing it back to the member is processing: a member who has withdrawn, or never
granted, gets an empty list. Until this was added the gate existed only in the frontend
(`health/consent-gate.tsx`), which meant the API answered with the measurements whatever
the consent record said, and any new screen that read this endpoint would have shown them
without anyone noticing the gate had been left behind. The records are not deleted —
withdrawal stops processing, it does not erase — so granting again brings them back.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.consent_repository import ConsentRepository
from app.application.ports.health_repository import HealthRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.run_repository import RunRepository
from app.application.services.points_reconciliation import valid_runs_of
from app.domain.campaign import Campaign, CampaignProgress
from app.domain.campaigns import policy_for
from app.domain.consent import ConsentPurpose
from app.domain.entities import Member, RunEntry
from app.domain.errors import MemberNotFound
from app.domain.health import HealthComparison
from app.domain.pace import pace_min_per_km
from app.domain.redemption import Redemption

KM = Decimal("0.001")


@dataclass(frozen=True)
class CampaignSummary:
    campaign: Campaign
    progress: CampaignProgress
    # What the member has EARNED is progress.value. What they can still SPEND is this
    # balance — SUM(delta) over the ledger, which already accounts for redemptions.
    # They are different numbers and both are shown; never substitute one for the other.
    points_balance: Decimal | None


@dataclass(frozen=True)
class LatestRun:
    run_date: date
    distance_km: Decimal
    pace_min_per_km: Decimal
    calories_burned: int | None
    steps: int | None


@dataclass(frozen=True)
class ActivityTotals:
    """What the member has actually done, over every run of theirs that still counts.

    Deliberately NOT scoped to a campaign window, unlike `CampaignSummary`. A campaign
    asks "how far this season"; these answer "how much running have I done", which is a
    different question and stops being true the day a campaign ends. `total_distance_km`
    beside it has always been lifetime, so scoping these differently would put two
    numbers with two meanings on one screen.

    The counts are the reason `total_calories` can be trusted. Most screenshots carry no
    calorie figure, so a bare total over the three runs that happened to have one reads
    as the total for all twelve. `calories_from_runs` is what lets a screen say "from 3
    of 12" instead of implying completeness the data does not have (golden rule #4).
    """

    run_count: int
    active_seconds: int
    # None when there are no runs at all — there is no average of nothing, and 0 would
    # be a claim about a member who has simply not started.
    avg_pace_min_per_km: Decimal | None
    total_calories: int
    calories_from_runs: int
    total_steps: int
    steps_from_runs: int
    latest_run: LatestRun | None


@dataclass(frozen=True)
class MemberSummary:
    member: Member
    total_distance_km: Decimal
    campaigns: list[CampaignSummary]
    redemptions: list[Redemption]
    health: list[HealthComparison]
    activity: ActivityTotals


class GetMySummary:
    def __init__(
        self,
        members: MemberRepository,
        runs: RunRepository,
        campaigns: CampaignRepository,
        ledger: PointsLedgerRepository,
        redemptions: RedemptionRepository,
        health: HealthRepository,
        consents: ConsentRepository,
        consent_version: str,
    ) -> None:
        self._members = members
        self._runs = runs
        self._campaigns = campaigns
        self._ledger = ledger
        self._redemptions = redemptions
        self._health = health
        self._consents = consents
        self._consent_version = consent_version

    def execute(self, member_id: UUID) -> MemberSummary:
        member = self._members.get(member_id)
        if member is None:
            raise MemberNotFound(str(member_id))

        # Rejected runs count for nothing: not toward a campaign, not toward the
        # member's total. Progress that still included them would contradict the
        # reversal the ledger already made.
        runs = valid_runs_of(self._runs.list_by_member(member_id))
        total_distance = sum((r.distance_km for r in runs), start=Decimal("0")).quantize(KM)

        campaigns = []
        for campaign in self._campaigns.list_active():
            policy = policy_for(campaign.type)
            campaigns.append(
                CampaignSummary(
                    campaign=campaign,
                    # One run can sit inside two overlapping campaigns and counts in
                    # both — each policy filters the same list by its own window.
                    progress=policy.progress(campaign, runs),
                    points_balance=(
                        self._ledger.balance(member_id, campaign.id)
                        if policy.tracks_points
                        else None
                    ),
                )
            )

        return MemberSummary(
            member=member,
            total_distance_km=total_distance,
            campaigns=campaigns,
            redemptions=self._redemptions.list_by_member(member_id),
            health=self._health_for(member_id),
            activity=_activity_totals(runs, total_distance),
        )

    def _health_for(self, member_id: UUID) -> list[HealthComparison]:
        consent = self._consents.get_current(member_id, ConsentPurpose.HEALTH_DATA)
        if consent is None or not consent.is_active(self._consent_version):
            # Nothing is deleted and nothing is said about why here — the consent screen
            # is where a member sees the state of their own consent and can grant again.
            return []

        records = self._health.list_by_member(member_id)
        # Includes campaigns that have already ended: the member keeps access to their
        # own history (PDPA right of access), not just to what is running now.
        return [
            HealthComparison.build(campaign_id, records)
            for campaign_id in dict.fromkeys(r.campaign_id for r in records)
        ]


def _activity_totals(runs: list[RunEntry], total_distance: Decimal) -> ActivityTotals:
    if not runs:
        return ActivityTotals(
            run_count=0,
            active_seconds=0,
            avg_pace_min_per_km=None,
            total_calories=0,
            calories_from_runs=0,
            total_steps=0,
            steps_from_runs=0,
            latest_run=None,
        )

    active_seconds = sum(run.duration_seconds for run in runs)
    with_calories = [run.calories_burned for run in runs if run.calories_burned is not None]
    with_steps = [run.steps for run in runs if run.steps is not None]
    # The run the member did most recently, by the day they ran rather than the day they
    # got round to submitting it — `created_at` breaks the tie for two runs on one day.
    latest = max(runs, key=lambda run: (run.run_date, run.created_at))

    return ActivityTotals(
        run_count=len(runs),
        active_seconds=active_seconds,
        # Total time over total distance, not the mean of each run's pace. Those are
        # different numbers, and this is the one that means "how fast do I run": a mean
        # of paces lets a 1 km jog weigh as much as a 20 km long run.
        avg_pace_min_per_km=pace_min_per_km(total_distance, active_seconds),
        total_calories=sum(with_calories),
        calories_from_runs=len(with_calories),
        total_steps=sum(with_steps),
        steps_from_runs=len(with_steps),
        latest_run=LatestRun(
            run_date=latest.run_date,
            distance_km=latest.distance_km,
            pace_min_per_km=latest.pace_min_per_km,
            calories_burned=latest.calories_burned,
            steps=latest.steps,
        ),
    )
