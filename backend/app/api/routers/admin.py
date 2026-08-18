"""Admin views. Role-gated, and audited wherever health data is actually returned."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import (
    get_cancel_redemption_uc,
    get_club_overview_uc,
    get_create_announcement_uc,
    get_create_campaign_uc,
    get_create_reward_uc,
    get_current_admin,
    get_current_superuser,
    get_fulfill_redemption_uc,
    get_list_admin_campaigns_uc,
    get_list_admin_rewards_uc,
    get_list_all_announcements_uc,
    get_list_members_uc,
    get_list_pending_redemptions_uc,
    get_review_run_uc,
    get_set_member_role_uc,
    get_update_announcement_uc,
    get_update_campaign_uc,
    get_update_reward_uc,
    get_upload_reward_image_uc,
    get_view_member_contact_uc,
    get_view_member_health_uc,
    get_view_member_progress_uc,
    get_view_member_screening_uc,
)
from app.api.schemas import (
    AdminAnnouncementResponse,
    AdminRewardResponse,
    CampaignResponse,
    ClubOverviewResponse,
    CreateAnnouncementRequest,
    CreateCampaignRequest,
    CreateRewardRequest,
    MemberContactResponse,
    MemberHealthResponse,
    MemberProgressResponse,
    MemberResponse,
    MemberScreeningResponse,
    PendingRedemptionResponse,
    RedemptionResponse,
    ReviewRunRequest,
    RewardImageResponse,
    RunResponse,
    UpdateAnnouncementRequest,
    UpdateCampaignRequest,
    UpdateMemberRoleRequest,
    UpdateRewardRequest,
)
from app.application.use_cases.get_club_overview import GetClubOverview
from app.application.use_cases.list_admin_catalogue import (
    ListAdminCampaigns,
    ListAdminRewards,
)
from app.application.use_cases.list_announcements import ListAllAnnouncements
from app.application.use_cases.list_members import ListMembers
from app.application.use_cases.list_pending_redemptions import ListPendingRedemptions
from app.application.use_cases.manage_announcements import (
    CreateAnnouncement,
    CreateAnnouncementCommand,
    UpdateAnnouncement,
    UpdateAnnouncementCommand,
)
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
from app.application.use_cases.set_member_role import SetMemberRole, SetMemberRoleCommand
from app.application.use_cases.upload_reward_image import (
    UploadRewardImage,
    UploadRewardImageCommand,
)
from app.application.use_cases.view_member_contact import (
    ViewMemberContact,
    ViewMemberContactCommand,
)
from app.application.use_cases.view_member_health import (
    ViewMemberHealth,
    ViewMemberHealthCommand,
)
from app.application.use_cases.view_member_progress import ViewMemberProgress
from app.application.use_cases.view_member_screening import (
    ViewMemberScreening,
    ViewMemberScreeningCommand,
)
from app.domain.entities import Member
from app.domain.errors import InvalidImage
from app.domain.evidence import MAX_IMAGE_BYTES

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview", response_model=ClubOverviewResponse)
def club_overview(
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[GetClubOverview, Depends(get_club_overview_uc)],
) -> ClubOverviewResponse:
    """Everyone's standing on one screen.

    No health data, no screening answers, none of the sensitive profile fields. Reading
    those is an audited act about one named member; a table cannot do it for a hundred
    people at once and still mean anything.
    """
    return ClubOverviewResponse.from_overview(use_case.execute(admin.id))


@router.get("/members", response_model=list[MemberResponse])
def list_members(
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[ListMembers, Depends(get_list_members_uc)],
) -> list[MemberResponse]:
    # Names and roles only — no health data, so no audit rows.
    return [MemberResponse.from_entity(m) for m in use_case.execute(admin.id)]


@router.get("/members/{member_id}/summary", response_model=MemberProgressResponse)
def member_progress(
    member_id: UUID,
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[ViewMemberProgress, Depends(get_view_member_progress_uc)],
) -> MemberProgressResponse:
    """Activity records only, so no audit row. The three endpoints below are the ones
    that touch sensitive data, and each of those writes one."""
    return MemberProgressResponse.from_view(use_case.execute(admin.id, member_id))


@router.get("/members/{member_id}/screening", response_model=MemberScreeningResponse)
def member_screening(
    member_id: UUID,
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[ViewMemberScreening, Depends(get_view_member_screening_uc)],
) -> MemberScreeningResponse:
    """Audited: the row is committed before the answers are returned."""
    return MemberScreeningResponse.from_view(
        use_case.execute(ViewMemberScreeningCommand(actor_id=admin.id, subject_id=member_id))
    )


@router.get("/members/{member_id}/contact", response_model=MemberContactResponse)
def member_contact(
    member_id: UUID,
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[ViewMemberContact, Depends(get_view_member_contact_uc)],
) -> MemberContactResponse:
    """Audited. Collected so someone can be reached in an emergency, which is precisely
    why opening them is an event the club should be able to account for."""
    return MemberContactResponse.from_entity(
        use_case.execute(ViewMemberContactCommand(actor_id=admin.id, subject_id=member_id))
    )


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
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[ReviewRun, Depends(get_review_run_uc)],
) -> RunResponse:
    # A mutation, so it is always audited — regardless of how sensitive the run was to
    # merely look at.
    run = use_case.execute(
        ReviewRunCommand(actor_id=admin.id, run_id=run_id, decision=body.decision)
    )
    return RunResponse.from_entity(run)


# --------------------------------------------------------- superuser mutations
# Every endpoint below is superuser-only and writes an audit row. Admins may look at the
# club's data and decide runs; changing what the club offers — and who may look — is a
# different capability.


@router.patch("/members/{member_id}/role", response_model=MemberResponse)
def set_member_role(
    member_id: UUID,
    body: UpdateMemberRoleRequest,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[SetMemberRole, Depends(get_set_member_role_uc)],
) -> MemberResponse:
    """Make somebody a helper, or take it back.

    The endpoint that widens access to everyone else's data, so it is the narrowest one
    here: superuser only, member/admin only, never the superuser's own row, and audited
    whether or not anything changed. The role is read from the database on every request,
    so removing it takes effect on the demoted admin's very next call.
    """
    member = use_case.execute(
        SetMemberRoleCommand(
            actor_id=superuser.id, subject_id=member_id, role=body.role
        )
    )
    return MemberResponse.from_entity(member)


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


@router.get("/campaigns", response_model=list[CampaignResponse])
def list_campaigns(
    boss: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[ListAdminCampaigns, Depends(get_list_admin_campaigns_uc)],
) -> list[CampaignResponse]:
    """Closed ones included — a finished activity is still something to look at, and a
    correction to it still has to be possible."""
    return [CampaignResponse.from_entity(c) for c in use_case.execute(boss.id)]


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


@router.get("/announcements", response_model=list[AdminAnnouncementResponse])
def list_admin_announcements(
    boss: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[ListAllAnnouncements, Depends(get_list_all_announcements_uc)],
) -> list[AdminAnnouncementResponse]:
    """Drafts and hidden notices included — this is where they are found again."""
    return [AdminAnnouncementResponse.from_entity(a) for a in use_case.execute(boss.id)]


@router.post(
    "/announcements",
    response_model=AdminAnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_announcement(
    body: CreateAnnouncementRequest,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[CreateAnnouncement, Depends(get_create_announcement_uc)],
) -> AdminAnnouncementResponse:
    announcement = use_case.execute(
        CreateAnnouncementCommand(actor_id=superuser.id, **body.model_dump())
    )
    return AdminAnnouncementResponse.from_entity(announcement)


@router.patch(
    "/announcements/{announcement_id}", response_model=AdminAnnouncementResponse
)
def update_announcement(
    announcement_id: UUID,
    body: UpdateAnnouncementRequest,
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[UpdateAnnouncement, Depends(get_update_announcement_uc)],
) -> AdminAnnouncementResponse:
    # There is no DELETE here either: is_published=false takes a notice off every screen
    # while leaving it where whoever wrote it can find it.
    announcement = use_case.execute(
        UpdateAnnouncementCommand(
            actor_id=superuser.id, announcement_id=announcement_id, **body.model_dump()
        )
    )
    return AdminAnnouncementResponse.from_entity(announcement)


@router.post(
    "/rewards/image",
    response_model=RewardImageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_reward_image(
    superuser: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[UploadRewardImage, Depends(get_upload_reward_image_uc)],
    file: Annotated[UploadFile, File()],
) -> RewardImageResponse:
    """Store a catalogue photo and return its key. Attaching it to a reward is the
    separate, audited call that follows.

    Declared before POST /rewards so the literal path wins the match, and read the same
    way an evidence upload is: at most one byte past the limit, and the bytes decide what
    the file is — the filename and the declared content-type are ignored.
    """
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise InvalidImage(f"file exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit")

    stored = use_case.execute(
        UploadRewardImageCommand(actor_id=superuser.id, data=data)
    )
    return RewardImageResponse(image_key=stored.image_key)


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


@router.get("/rewards", response_model=list[AdminRewardResponse])
def list_admin_rewards(
    campaign_id: UUID,
    boss: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[ListAdminRewards, Depends(get_list_admin_rewards_uc)],
) -> list[AdminRewardResponse]:
    """Retired rewards included. They are withdrawn, never deleted, and one that
    vanished from this screen would look deleted."""
    return [
        AdminRewardResponse.from_offer(offer)
        for offer in use_case.execute(boss.id, campaign_id)
    ]


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


@router.get("/redemptions", response_model=list[PendingRedemptionResponse])
def pending_redemptions(
    boss: Annotated[Member, Depends(get_current_superuser)],
    use_case: Annotated[ListPendingRedemptions, Depends(get_list_pending_redemptions_uc)],
) -> list[PendingRedemptionResponse]:
    """The queue of rewards waiting to be handed over.

    Without it the fulfil and cancel endpoints below could only be reached by knowing a
    redemption's id, which nobody does.
    """
    return [PendingRedemptionResponse.from_row(r) for r in use_case.execute(boss.id)]


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
