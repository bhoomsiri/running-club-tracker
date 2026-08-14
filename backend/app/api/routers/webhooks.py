"""Clerk webhooks — a public endpoint, so every payload is signature-verified.

No authentication dependency here on purpose: Clerk cannot send a bearer token. The svix
signature IS the authentication, which is why an unverified payload must never reach the
use case.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.adapters.auth.clerk_webhook import ClerkWebhookVerifier, to_user_event
from app.api.deps import get_sync_member_uc, get_webhook_verifier
from app.application.use_cases.sync_member_from_clerk import SyncMemberFromClerk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/clerk", status_code=status.HTTP_204_NO_CONTENT)
async def clerk_webhook(
    request: Request,
    verifier: Annotated[ClerkWebhookVerifier, Depends(get_webhook_verifier)],
    use_case: Annotated[SyncMemberFromClerk, Depends(get_sync_member_uc)],
) -> Response:
    # The raw bytes are what was signed — parsing first and re-serialising would change
    # them and break verification.
    payload = await request.body()
    verified = verifier.verify(payload, dict(request.headers))

    event = to_user_event(verified)
    if event is None:
        # Acknowledged and ignored. Deletion in particular is a deliberate erasure flow,
        # not a webhook side effect.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    member = use_case.execute(event)
    # member_id and action only: no email, no name, no payload (golden rule #8).
    logger.info("member synced", extra={"member_id": str(member.id), "action": "sync_member"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
