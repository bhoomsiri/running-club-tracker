"""A member recording their own before/after health data.

The consent gate lives in the use case, so this router stays thin — it cannot forget to
apply it, and neither can any future caller.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_member_id, get_save_health_uc
from app.api.schemas import HealthRecordResponse, SaveHealthRequest
from app.application.use_cases.save_health_record import (
    SaveHealthRecord,
    SaveHealthRecordCommand,
)

router = APIRouter(prefix="/health", tags=["health"])


@router.post("", response_model=HealthRecordResponse, status_code=status.HTTP_201_CREATED)
def save_health(
    body: SaveHealthRequest,
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[SaveHealthRecord, Depends(get_save_health_uc)],
) -> HealthRecordResponse:
    record = use_case.execute(
        # member_id comes from the token, never from `body` — the DTO has no such field.
        SaveHealthRecordCommand(member_id=member_id, **body.model_dump())
    )
    return HealthRecordResponse.from_entity(record)
