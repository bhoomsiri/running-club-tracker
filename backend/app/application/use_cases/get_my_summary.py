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

It is deliberately NOT gated on consent either. Consent governs what the CLUB may do
with the data, not whether the person it describes may look at it — withdrawing stops
the club processing it and does not make it somebody else's, so the owner keeps seeing
their own measurements on every screen that shows them (PDPA มาตรา 30). The gate that
makes withdrawal mean something is on the other side: an admin reading someone else's
health data requires active consent, and so does the export.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.clock import Clock
from app.application.ports.health_repository import HealthRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.run_repository import RunRepository
from app.application.services.points_reconciliation import valid_runs_of
from app.domain.calendar import club_today
from app.domain.campaign import Campaign, CampaignProgress
from app.domain.campaigns import policy_for
from app.domain.entities import Member, RunEntry
from app.domain.errors import MemberNotFound
from app.domain.health import HealthComparison
from app.domain.pace import pace_min_per_km
from app.domain.redemption import Redemption

KM = Decimal("0.001")

# A week of bars, and eight points of trend. Both are what the dashboard draws; neither
# is a rule about anything, so they live here rather than in the domain.
RECENT_DAYS = 7
RECENT_PACE_RUNS = 8


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
class DayDistance:
    """How far the member ran on one calendar day, in the club's timezone.

    Zero here is a fact, not a missing value: the day is in the window whether or not
    anything was run on it, and "you ran nothing on Tuesday" is exactly what the chart is
    for. That is the opposite of `total_calories`, where zero would mean "no screenshot
    said" — which is why that one travels with a count and this one does not.
    """

    day: date
    distance_km: Decimal


@dataclass(frozen=True)
class RunPace:
    run_date: date
    pace_min_per_km: Decimal


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
    # Always exactly RECENT_DAYS entries, oldest first, ending on the club's today. The
    # window is a property of the calendar rather than of the member, so it is the same
    # seven days for someone who has never run — a screen with no runs to draw shows an
    # empty state off `run_count`, not off a short list.
    last_seven_days: list[DayDistance]
    # Up to RECENT_PACE_RUNS of the member's most recent runs, oldest first, so a chart
    # reads left to right. Fewer when they have run fewer times; empty when never.
    recent_paces: list[RunPace]


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
        clock: Clock,
    ) -> None:
        self._members = members
        self._runs = runs
        self._campaigns = campaigns
        self._ledger = ledger
        self._redemptions = redemptions
        self._health = health
        self._clock = clock

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
            # The window ends on the club's today, not on the member's last run: a chart
            # that slid back to whenever they last went out would show a full week to
            # someone who has not run in a month.
            activity=_activity_totals(runs, total_distance, club_today(self._clock.now())),
        )

    def _health_for(self, member_id: UUID) -> list[HealthComparison]:
        records = self._health.list_by_member(member_id)
        # Includes campaigns that have already ended: the member keeps access to their
        # own history (PDPA right of access), not just to what is running now.
        return [
            HealthComparison.build(campaign_id, records)
            for campaign_id in dict.fromkeys(r.campaign_id for r in records)
        ]


def _activity_totals(
    runs: list[RunEntry], total_distance: Decimal, today: date
) -> ActivityTotals:
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
            last_seven_days=_last_seven_days([], today),
            recent_paces=[],
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
        last_seven_days=_last_seven_days(runs, today),
        recent_paces=_recent_paces(runs),
    )


def _last_seven_days(runs: list[RunEntry], today: date) -> list[DayDistance]:
    """The window ending today, every day present, two runs on one day added together."""
    window = [today - timedelta(days=offset) for offset in reversed(range(RECENT_DAYS))]
    ran: dict[date, Decimal] = {}
    for run in runs:
        if run.run_date in window:
            ran[run.run_date] = ran.get(run.run_date, Decimal("0")) + run.distance_km
    return [DayDistance(day, ran.get(day, Decimal("0")).quantize(KM)) for day in window]


def _recent_paces(runs: list[RunEntry]) -> list[RunPace]:
    """The last few runs in the order they happened, so a trend line reads left to right.

    Sorted the same way `latest_run` picks its winner — by the day run, with the
    submission breaking a tie — so the rightmost point and the "latest run" card can
    never disagree about which run came last.
    """
    ordered = sorted(runs, key=lambda run: (run.run_date, run.created_at))
    return [
        RunPace(run_date=run.run_date, pace_min_per_km=run.pace_min_per_km)
        for run in ordered[-RECENT_PACE_RUNS:]
    ]
