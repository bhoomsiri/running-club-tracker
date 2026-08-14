"""Submitting runs: upload evidence, optionally have it read, then confirm.

Three endpoints, matching the three steps the member goes through:

    POST /runs/evidence  -> validate, scrub metadata, store, return a key
    POST /runs/extract   -> read that image, return a DRAFT (nothing is saved)
    POST /runs           -> save what the member confirmed

The middle step is optional: a member without a tracking app photographs their treadmill
and types the numbers in. The last step is the only one that writes a run, and it
re-validates everything regardless of where the values came from.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile, status

from app.api.deps import (
    get_current_admin,
    get_current_member_id,
    get_extract_run_uc,
    get_list_member_runs_uc,
    get_list_my_runs_uc,
    get_submit_run_uc,
    get_upload_evidence_uc,
)
from app.api.limiter import extract_limit, limiter
from app.api.schemas import (
    EvidenceResponse,
    ExtractRequest,
    ExtractResultResponse,
    RunResponse,
    RunWithEvidenceResponse,
    SubmitRunRequest,
)
from app.application.use_cases.extract_run_draft import ExtractRunDraft, ExtractRunDraftCommand
from app.application.use_cases.list_runs import ListMemberRuns, ListMyRuns
from app.application.use_cases.submit_run import SubmitRun, SubmitRunCommand
from app.application.use_cases.upload_evidence import UploadEvidence, UploadEvidenceCommand
from app.domain.entities import Member
from app.domain.errors import InvalidImage
from app.domain.evidence import MAX_IMAGE_BYTES

router = APIRouter(tags=["runs"])


@router.post(
    "/runs/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED
)
async def upload_evidence(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[UploadEvidence, Depends(get_upload_evidence_uc)],
    file: Annotated[UploadFile, File()],
) -> EvidenceResponse:
    # Read at most one byte more than the limit: enough to know it is too big, without
    # pulling an arbitrarily large upload into memory first.
    data = await file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise InvalidImage(f"file exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit")

    # The declared content-type and the filename are ignored entirely — the use case
    # decides what this is from the bytes themselves.
    stored = use_case.execute(UploadEvidenceCommand(member_id=member_id, data=data))
    return EvidenceResponse(image_key=stored.image_key, sha256=stored.sha256)


@router.post("/runs/extract", response_model=ExtractResultResponse)
@limiter.limit(extract_limit)
def extract_run(
    request: Request,  # required by the limiter
    body: ExtractRequest,
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[ExtractRunDraft, Depends(get_extract_run_uc)],
) -> ExtractResultResponse:
    # Returns a draft to be confirmed by a human. Nothing is written here.
    draft = use_case.execute(
        ExtractRunDraftCommand(member_id=member_id, image_key=body.image_key)
    )
    return ExtractResultResponse.from_draft(draft)


@router.post("/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
def submit_run(
    body: SubmitRunRequest,
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[SubmitRun, Depends(get_submit_run_uc)],
) -> RunResponse:
    run = use_case.execute(SubmitRunCommand(member_id=member_id, **body.model_dump()))
    return RunResponse.from_entity(run)


@router.get("/me/runs", response_model=list[RunWithEvidenceResponse])
def my_runs(
    member_id: Annotated[UUID, Depends(get_current_member_id)],
    use_case: Annotated[ListMyRuns, Depends(get_list_my_runs_uc)],
) -> list[RunWithEvidenceResponse]:
    return [RunWithEvidenceResponse.from_result(r) for r in use_case.execute(member_id)]


@router.get(
    "/admin/members/{member_id}/runs", response_model=list[RunWithEvidenceResponse]
)
def member_runs(
    member_id: UUID,
    admin: Annotated[Member, Depends(get_current_admin)],
    use_case: Annotated[ListMemberRuns, Depends(get_list_member_runs_uc)],
) -> list[RunWithEvidenceResponse]:
    return [
        RunWithEvidenceResponse.from_result(r)
        for r in use_case.execute(actor_id=admin.id, subject_id=member_id)
    ]
