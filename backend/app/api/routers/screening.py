"""A member's own PAR-Q+ pre-exercise screening.

Sensitive personal data under PDPA, so the consent gate lives in the use case where no
caller can miss it. Reading back one's own answers needs no consent check — withdrawing
stops the club processing them, it does not take away the owner's view of them.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_current_member_id,
    get_my_screening_uc,
    get_save_screening_uc,
)
from app.api.schemas import SaveScreeningRequest, ScreeningResponse
from app.application.use_cases.get_my_screening import GetMyScreening
from app.application.use_cases.save_my_screening import (
    SaveMyScreening,
    SaveMyScreeningCommand,
)

router = APIRouter(prefix="/screening", tags=["screening"])


@router.get("", response_model=ScreeningResponse | None)
def my_screening(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[GetMyScreening, Depends(get_my_screening_uc)],
) -> ScreeningResponse | None:
    """Null when the member has not been screened yet — an ordinary state, not a 404."""
    screening = use_case.execute(member_id)
    return None if screening is None else ScreeningResponse.from_entity(screening)


@router.post("", response_model=ScreeningResponse)
def save_my_screening(
    body: SaveScreeningRequest,
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[SaveMyScreening, Depends(get_save_screening_uc)],
) -> ScreeningResponse:
    # 200 rather than 201: answering again replaces the member's single record, so this
    # is not always a creation and the caller should not have to care which it was.
    screening = use_case.execute(
        SaveMyScreeningCommand(member_id=member_id, **body.model_dump())
    )
    return ScreeningResponse.from_entity(screening)
