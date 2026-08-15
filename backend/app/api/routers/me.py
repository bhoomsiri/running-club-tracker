"""Endpoints a member uses about themselves. Everything here is scoped to the token."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_current_member,
    get_current_member_id,
    get_my_summary_uc,
    get_onboarding_status_uc,
    get_update_profile_uc,
)
from app.api.schemas import (
    MemberProfileResponse,
    MemberSummaryResponse,
    OnboardingStatusResponse,
    UpdateProfileRequest,
)
from app.application.use_cases.get_my_summary import GetMySummary
from app.application.use_cases.get_onboarding_status import GetOnboardingStatus
from app.application.use_cases.update_my_profile import (
    UpdateMyProfile,
    UpdateMyProfileCommand,
)
from app.domain.entities import Member

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/summary", response_model=MemberSummaryResponse)
def my_summary(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[GetMySummary, Depends(get_my_summary_uc)],
) -> MemberSummaryResponse:
    # There is no member_id parameter on this route by design: the only id it can read
    # is the caller's own, so there is nothing to tamper with.
    return MemberSummaryResponse.from_summary(use_case.execute(member_id))


@router.get("/profile", response_model=MemberProfileResponse)
def my_profile(
    member: Annotated[Member, Depends(get_current_member)],
) -> MemberProfileResponse:
    return MemberProfileResponse.from_entity(member)


@router.patch("/profile", response_model=MemberProfileResponse)
def update_my_profile(
    body: UpdateProfileRequest,
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[UpdateMyProfile, Depends(get_update_profile_uc)],
) -> MemberProfileResponse:
    member = use_case.execute(
        # member_id comes from the token; the DTO has no such field to override it.
        UpdateMyProfileCommand(member_id=member_id, **body.model_dump())
    )
    return MemberProfileResponse.from_entity(member)


@router.get("/onboarding", response_model=OnboardingStatusResponse)
def my_onboarding(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[GetOnboardingStatus, Depends(get_onboarding_status_uc)],
) -> OnboardingStatusResponse:
    """What this member still has to do before they are set up.

    Reports; does not enforce. The redirect lives in the frontend, and each individual
    write is guarded by its own rule whatever this says.
    """
    return OnboardingStatusResponse.from_status(use_case.execute(member_id))
