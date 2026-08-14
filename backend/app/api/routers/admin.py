"""Admin views. Role-gated, and audited wherever health data is actually returned."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_cancel_redemption_uc,
    get_create_campaign_uc,
    get_create_reward_uc,
    get_current_admin,
    get_current_superuser,
    get_fulfill_redemption_uc,
    get_list_members_uc,
    get_review_run_uc,
    get_update_campaign_uc,
    get_update_reward_uc,
    get_view_member_health_uc,
)
from app.api.schemas import (
    AdminRewardResponse,
    CampaignResponse,
    CreateCampaignRequest,
    CreateRewardRequest,
    MemberHealthResponse,
    MemberResponse,
    RedemptionResponse,
    ReviewRunRequest,
    RunResponse,
    UpdateCampaignRequest,
    UpdateRewardRequest,
)
from app.application.use_cases.list_members import ListMembers
from app.application.use_cases.manage_campaigns import (
    CreateCampaign,
    CreateCampaignCommand,
    UpdateCampaign,
    UpdateCampaignCommand,
)
from app.application.use_cases.manage_redemptions import (
    CancelRedemption,
    FulfillRedemption,
    RedemptionCommand,
)
from app.application.use_cases.manage_rewards import (
    CreateReward,
    CreateRewardCommand,
    UpdateReward,
    UpdateRewardCommand,
)
from app.application.use_cases.review_run import ReviewRun, ReviewRunCommand
from app.application.use_cases.view_member_health import (
    ViewMemberHealth,
    ViewMemberHealthCommand,
)
from app.domain.entities import Member

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/members", response_model=list[MemberResponse])
def list_members(
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[ListMembers, Depends(get_list_members_uc)],
) -> list[MemberResponse]:
    # Names and roles only — no health data, so no audit rows.
    return [MemberResponse.from_entity(m) for m in use_case.execute(admin.id)]


@router.get("/members/{member_id}/health", response_model=MemberHealthResponse)
def view_member_health(
    member_id: UUID,
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[ViewMemberHealth, Depends(get_view_member_health_uc)],
) -> MemberHealthResponse:
    # The one place a member id from the URL is honoured — and it is role-gated above,
    # consent-gated inside, and written to audit_log before anything is returned.
    view = use_case.execute(
        ViewMemberHealthCommand(actor_id=admin.id, subject_id=member_id)
    )
    return MemberHealthResponse.from_view(view)


@router.post("/runs/{run_id}/review", response_model=RunResponse)
def review_run(
    run_id: UUID,
    body: ReviewRunRequest,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[ReviewRun, Depends(get_review_run_uc)],
) -> RunResponse:
    # A mutation, so it is always audited — regardless of how sensitive the run was to
    # merely look at.
    run = use_case.execute(
        ReviewRunCommand(actor_id=superuser.id, run_id=run_id, decision=body.decision)
    )
    return RunResponse.from_entity(run)


# --------------------------------------------------------- superuser mutations
# Every endpoint below is superuser-only and writes an audit row. Admins may look at
# the club's data; changing it is a different capability.


@router.post(
    "/campaigns", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED
)
def create_campaign(
    body: CreateCampaignRequest,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[CreateCampaign, Depends(get_create_campaign_uc)],
) -> CampaignResponse:
    campaign = use_case.execute(
        CreateCampaignCommand(actor_id=superuser.id, **body.model_dump())
    )
    return CampaignResponse.from_entity(campaign)


@router.patch("/campaigns/{campaign_id}", response_model=CampaignResponse)
def update_campaign(
    campaign_id: UUID,
    body: UpdateCampaignRequest,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[UpdateCampaign, Depends(get_update_campaign_uc)],
) -> CampaignResponse:
    campaign = use_case.execute(
        UpdateCampaignCommand(
            actor_id=superuser.id, campaign_id=campaign_id, **body.model_dump()
        )
    )
    return CampaignResponse.from_entity(campaign)


@router.post(
    "/rewards", response_model=AdminRewardResponse, status_code=status.HTTP_201_CREATED
)
def create_reward(
    body: CreateRewardRequest,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[CreateReward, Depends(get_create_reward_uc)],
) -> AdminRewardResponse:
    reward = use_case.execute(CreateRewardCommand(actor_id=superuser.id, **body.model_dump()))
    return AdminRewardResponse.from_entity(reward)


@router.patch("/rewards/{reward_id}", response_model=AdminRewardResponse)
def update_reward(
    reward_id: UUID,
    body: UpdateRewardRequest,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[UpdateReward, Depends(get_update_reward_uc)],
) -> AdminRewardResponse:
    # There is no DELETE: a reward with redemptions behind it is retired with
    # is_active=false so the history stays readable.
    reward = use_case.execute(
        UpdateRewardCommand(actor_id=superuser.id, reward_id=reward_id, **body.model_dump())
    )
    return AdminRewardResponse.from_entity(reward)


@router.post("/redemptions/{redemption_id}/fulfill", response_model=RedemptionResponse)
def fulfill_redemption(
    redemption_id: UUID,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[FulfillRedemption, Depends(get_fulfill_redemption_uc)],
) -> RedemptionResponse:
    # The real gate: refuses while the balance is negative or a run is still flagged.
    redemption = use_case.execute(
        RedemptionCommand(actor_id=superuser.id, redemption_id=redemption_id)
    )
    return RedemptionResponse.from_entity(redemption)


@router.post("/redemptions/{redemption_id}/cancel", response_model=RedemptionResponse)
def cancel_redemption(
    redemption_id: UUID,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[CancelRedemption, Depends(get_cancel_redemption_uc)],
) -> RedemptionResponse:
    redemption = use_case.execute(
        RedemptionCommand(actor_id=superuser.id, redemption_id=redemption_id)
    )
    return RedemptionResponse.from_entity(redemption)
