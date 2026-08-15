"""The superuser looking at ONE member's progress.

Not audited, and deliberately so: distance, points and redemptions are the club's own
activity records, not sensitive personal data, and auditing every glance at a
leaderboard row would bury the entries that matter under noise nobody reads. The
member's health, screening and contact details are separate endpoints, and each of those
writes a row.

Everything is derived exactly as `/me/summary` derives it — same policy, same
rejected-run filter, same ledger balance — so what the superuser sees about someone can
never disagree with what that member sees about themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.run_repository import RunRepository
from app.application.services.points_reconciliation import valid_runs_of
from app.domain.campaign import Campaign, CampaignProgress
from app.domain.campaigns import policy_for
from app.domain.entities import Member, MemberRole, ReviewStatus
from app.domain.errors import MemberNotFound, NotAuthorized
from app.domain.redemption import Redemption

KM = Decimal("0.001")


@dataclass(frozen=True)
class CampaignStanding:
    campaign: Campaign
    progress: CampaignProgress
    points_balance: Decimal | None


@dataclass(frozen=True)
class MemberProgressView:
    member: Member
    total_distance_km: Decimal
    run_count: int
    pending_review_count: int
    campaigns: list[CampaignStanding]
    redemptions: list[Redemption]


class ViewMemberProgress:
    def __init__(
        self,
        members: MemberRepository,
        runs: RunRepository,
        campaigns: CampaignRepository,
        ledger: PointsLedgerRepository,
        redemptions: RedemptionRepository,
    ) -> None:
        self._members = members
        self._runs = runs
        self._campaigns = campaigns
        self._ledger = ledger
        self._redemptions = redemptions

    def execute(self, actor_id: UUID, subject_id: UUID) -> MemberProgressView:
        actor = self._members.get(actor_id)
        if actor is None:
            raise MemberNotFound(str(actor_id))
        if actor.role is not MemberRole.SUPERUSER:
            raise NotAuthorized("superuser only")

        subject = self._members.get(subject_id)
        if subject is None:
            raise MemberNotFound(str(subject_id))

        all_runs = self._runs.list_by_member(subject_id)
        counted = valid_runs_of(all_runs)

        return MemberProgressView(
            member=subject,
            total_distance_km=sum(
                (run.distance_km for run in counted), start=Decimal("0")
            ).quantize(KM),
            # Every submission, rejected ones included: this is the view of what was
            # sent in, not of what counted.
            run_count=len(all_runs),
            pending_review_count=sum(
                1 for run in all_runs if run.review_status is ReviewStatus.FLAGGED
            ),
            campaigns=[
                CampaignStanding(
                    campaign=campaign,
                    progress=policy_for(campaign.type).progress(campaign, counted),
                    points_balance=(
                        self._ledger.balance(subject_id, campaign.id)
                        if policy_for(campaign.type).tracks_points
                        else None
                    ),
                )
                for campaign in self._campaigns.list_active()
            ],
            redemptions=self._redemptions.list_by_member(subject_id),
        )
