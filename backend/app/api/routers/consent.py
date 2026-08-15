"""Granting and withdrawing consent for health data (PDPA)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import (
    get_current_member_id,
    get_grant_consent_uc,
    get_my_consent_uc,
    get_settings_dep,
    get_withdraw_consent_uc,
)
from app.api.schemas import ConsentResponse
from app.application.use_cases.get_my_consent import GetMyConsent
from app.application.use_cases.grant_consent import GrantConsent, GrantConsentCommand
from app.application.use_cases.withdraw_consent import (
    WithdrawConsent,
    WithdrawConsentCommand,
)
from app.config import Settings

router = APIRouter(prefix="/consent", tags=["consent"])


@router.get("", response_model=ConsentResponse | None)
def my_consent(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[GetMyConsent, Depends(get_my_consent_uc)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> ConsentResponse | None:
    """The caller's own consent, or null if there is none in force.

    Null rather than 404: having never agreed is an ordinary state for a member, not a
    missing resource. A withdrawn consent reads as null too — the repository only
    returns one that has not been withdrawn — which is the same answer as far as the UI
    is concerned, since both mean "ask again". The withdrawal itself is still on record;
    it is simply not what this endpoint reports.

    The remaining case is the one worth the endpoint existing: a consent that is present
    and not withdrawn, but given to wording that has since changed. That comes back with
    `active: false`, and `active` is what the UI must gate the health form on.
    """
    consent = use_case.execute(member_id)
    return None if consent is None else ConsentResponse.from_entity(
        consent, settings.consent_version
    )


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
