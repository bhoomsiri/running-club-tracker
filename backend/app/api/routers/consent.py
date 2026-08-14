"""Granting and withdrawing consent for health data (PDPA)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import (
    get_current_member_id,
    get_grant_consent_uc,
    get_settings_dep,
    get_withdraw_consent_uc,
)
from app.api.schemas import ConsentResponse
from app.application.use_cases.grant_consent import GrantConsent, GrantConsentCommand
from app.application.use_cases.withdraw_consent import (
    WithdrawConsent,
    WithdrawConsentCommand,
)
from app.config import Settings

router = APIRouter(prefix="/consent", tags=["consent"])


@router.post("", response_model=ConsentResponse, status_code=status.HTTP_201_CREATED)
def grant_consent(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[GrantConsent, Depends(get_grant_consent_uc)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ConsentResponse:
    consent = use_case.execute(GrantConsentCommand(member_id=member_id))
    return ConsentResponse.from_entity(consent, settings.consent_version)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_consent(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[WithdrawConsent, Depends(get_withdraw_consent_uc)],
) -> Response:
    # Idempotent: withdrawing when nothing is active is a 204 too, because the member
    # has what they asked for either way.
    use_case.execute(WithdrawConsentCommand(member_id=member_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
