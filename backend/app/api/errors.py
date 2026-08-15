"""Domain errors -> HTTP status codes, in one table.

Routers therefore contain no error translation: any use case can raise a domain error
and every endpoint answers with the same status for it. A domain error that isn't listed
becomes a 500, which is the honest answer for a rule we forgot to map.

Messages are safe to return: domain errors carry ids and limits, never measurements,
tokens, or email.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.domain.errors import (
    CampaignNotFound,
    ConsentRequired,
    DomainError,
    DuplicateEvidence,
    EvidenceNotFound,
    ExtractionFailed,
    InsufficientPoints,
    InvalidAuditEntry,
    InvalidCampaignError,
    InvalidConsentError,
    InvalidHealthRecordError,
    InvalidImage,
    InvalidLedgerEntry,
    InvalidMemberError,
    InvalidRewardError,
    InvalidRunError,
    InvalidScreeningError,
    InvalidToken,
    MemberAlreadyExists,
    MemberNotFound,
    NotAuthorized,
    OutOfStock,
    RedemptionNotFound,
    RedemptionNotPending,
    RewardUnavailable,
    RunNotFound,
    UnknownCampaignType,
    UnresolvedRuns,
)

logger = logging.getLogger(__name__)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    InvalidToken: 401,
    # 403 for both: one is "your role may not", the other "there is no lawful basis".
    # Neither tells the caller anything about whether the data exists.
    NotAuthorized: 403,
    ConsentRequired: 403,
    MemberNotFound: 404,
    RunNotFound: 404,
    CampaignNotFound: 404,
    RedemptionNotFound: 404,
    EvidenceNotFound: 404,
    # 409: the request was well-formed, the world just isn't in a state that allows it.
    InsufficientPoints: 409,
    OutOfStock: 409,
    RewardUnavailable: 409,
    MemberAlreadyExists: 409,
    RedemptionNotPending: 409,
    # The member's points are not settled yet, so the item must not be handed over.
    UnresolvedRuns: 409,
    # The same member re-submitting an image they already used.
    DuplicateEvidence: 409,
    # 415: the bytes are not an image type we accept.
    InvalidImage: 415,
    ExtractionFailed: 502,
    # 422: the values themselves are wrong.
    InvalidRunError: 422,
    InvalidMemberError: 422,
    InvalidCampaignError: 422,
    InvalidRewardError: 422,
    InvalidHealthRecordError: 422,
    InvalidScreeningError: 422,
    InvalidConsentError: 422,
    InvalidLedgerEntry: 422,
    InvalidAuditEntry: 422,
    UnknownCampaignType: 422,
}


def status_for(error: DomainError) -> int:
    for error_type in type(error).__mro__:
        if error_type in STATUS_BY_ERROR:
            return STATUS_BY_ERROR[error_type]
    return 500


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status = status_for(exc)
        if status >= 500:
            # Log the action and the member, never the payload (golden rule #8).
            logger.error(
                "unmapped domain error",
                extra={
                    "member_id": str(getattr(request.state, "member_id", "")),
                    "error": type(exc).__name__,
                },
            )
        if status >= 500:
            # The message may name internals; the caller gets a generic one and the
            # details stay in the log (member_id + error type only).
            return JSONResponse(status_code=status, content={"detail": "internal error"})
        return JSONResponse(status_code=status, content={"detail": str(exc)})
