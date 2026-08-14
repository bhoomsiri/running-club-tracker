"""Endpoints a member uses about themselves. Everything here is scoped to the token."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import get_current_member_id, get_my_summary_uc
from app.api.schemas import MemberSummaryResponse
from app.application.use_cases.get_my_summary import GetMySummary

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/summary", response_model=MemberSummaryResponse)
def my_summary(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[GetMySummary, Depends(get_my_summary_uc)],
) -> MemberSummaryResponse:
    # There is no member_id parameter on this route by design: the only id it can read
    # is the caller's own, so there is nothing to tamper with.
    return MemberSummaryResponse.from_summary(use_case.execute(member_id))
