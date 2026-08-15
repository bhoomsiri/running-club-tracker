"""Every member's progress on one screen, for the superuser.

What this deliberately does NOT return: health measurements, screening answers, sex,
phone numbers, the emergency contact. Those are sensitive personal data, and reading
them is an audited act — a table that loads them for a hundred members at once would
write a hundred audit rows for a glance, or worse, none at all. They belong to a
drill-down that records who looked at whose, one member at a time.

Superuser only, not admin. An admin may read health data with an audit trail; a list of
everyone's standing is a different thing, and the club has one person running it.

Everything here is derived the same way the member's own screen derives it — the same
policy, the same rejected-run filter, the same ledger balance — so the two cannot
disagree about someone's progress.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.run_repository import RunRepository
from app.application.services.points_reconciliation import valid_runs_of
from app.domain.campaign import Campaign, CampaignProgress
from app.domain.campaigns import policy_for
from app.domain.entities import Member, MemberRole, ReviewStatus, RunEntry
from app.domain.errors import MemberNotFound, NotAuthorized

KM = Decimal("0.001")


@dataclass(frozen=True)
class MemberCampaignProgress:
    campaign: Campaign
    progress: CampaignProgress
    points_balance: Decimal | None


@dataclass(frozen=True)
class MemberOverview:
    member: Member
    total_distance_km: Decimal
    run_count: int
    pending_review_count: int
    campaigns: list[MemberCampaignProgress]


@dataclass(frozen=True)
class ClubOverview:
    campaigns: list[Campaign]
    members: list[MemberOverview]


class GetClubOverview:
    def __init__(
        self,
        members: MemberRepository,
        runs: RunRepository,
        campaigns: CampaignRepository,
        ledger: PointsLedgerRepository,
    ) -> None:
        self._members = members
        self._runs = runs
        self._campaigns = campaigns
        self._ledger = ledger

    def execute(self, actor_id: UUID) -> ClubOverview:
        actor = self._members.get(actor_id)
        if actor is None:
            raise MemberNotFound(str(actor_id))
        # Checked here as well as at the router: the router gate is convenience, this is
        # the control.
        if actor.role is not MemberRole.SUPERUSER:
            raise NotAuthorized("superuser only")

        campaigns = self._campaigns.list_active()
        # Three queries for the whole club rather than three per member: one for the
        # runs, one per campaign for the balances.
        runs_by_member = _group_by_member(self._runs.list_all())
        balances = {
            campaign.id: self._ledger.balances_for_campaign(campaign.id)
            for campaign in campaigns
            if policy_for(campaign.type).tracks_points
        }

        rows = [
            self._overview_for(member, runs_by_member.get(member.id, []), campaigns, balances)
            for member in self._members.list_all()
        ]
        return ClubOverview(campaigns=campaigns, members=rows)

    def _overview_for(
        self,
        member: Member,
        all_runs: list[RunEntry],
        campaigns: list[Campaign],
        balances: dict[UUID, dict[UUID, Decimal]],
    ) -> MemberOverview:
        # Rejected runs count for nothing, exactly as on the member's own screen.
        counted = valid_runs_of(all_runs)

        return MemberOverview(
            member=member,
            total_distance_km=sum(
                (run.distance_km for run in counted), start=Decimal("0")
            ).quantize(KM),
            # Every submission, including rejected ones: this is the admin's view of
            # what someone has sent in, not of what counted.
            run_count=len(all_runs),
            pending_review_count=sum(
                1 for run in all_runs if run.review_status is ReviewStatus.FLAGGED
            ),
            campaigns=[
                MemberCampaignProgress(
                    campaign=campaign,
                    progress=policy_for(campaign.type).progress(campaign, counted),
                    points_balance=(
                        balances[campaign.id].get(member.id, Decimal("0"))
                        if campaign.id in balances
                        else None
                    ),
                )
                for campaign in campaigns
            ],
        )


def _group_by_member(runs: list[RunEntry]) -> dict[UUID, list[RunEntry]]:
    grouped: dict[UUID, list[RunEntry]] = {}
    for run in runs:
        grouped.setdefault(run.member_id, []).append(run)
    return grouped
