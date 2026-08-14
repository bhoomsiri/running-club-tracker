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
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.health_repository import HealthRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.run_repository import RunRepository
from app.application.services.points_reconciliation import valid_runs_of
from app.domain.campaign import Campaign, CampaignProgress
from app.domain.campaigns import policy_for
from app.domain.entities import Member
from app.domain.errors import MemberNotFound
from app.domain.health import HealthComparison
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
class MemberSummary:
    member: Member
    total_distance_km: Decimal
    campaigns: list[CampaignSummary]
    redemptions: list[Redemption]
    health: list[HealthComparison]


class GetMySummary:
    def __init__(
        self,
        members: MemberRepository,
        runs: RunRepository,
        campaigns: CampaignRepository,
        ledger: PointsLedgerRepository,
        redemptions: RedemptionRepository,
        health: HealthRepository,
    ) -> None:
        self._members = members
        self._runs = runs
        self._campaigns = campaigns
        self._ledger = ledger
        self._redemptions = redemptions
        self._health = health

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

        records = self._health.list_by_member(member_id)
        # Includes campaigns that have already ended: the member keeps access to their
        # own history (PDPA right of access), not just to what is running now.
        health = [
            HealthComparison.build(campaign_id, records)
            for campaign_id in dict.fromkeys(r.campaign_id for r in records)
        ]

        return MemberSummary(
            member=member,
            total_distance_km=total_distance,
            campaigns=campaigns,
            redemptions=self._redemptions.list_by_member(member_id),
            health=health,
        )
