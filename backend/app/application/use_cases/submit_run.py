"""Save a run the member has confirmed, and credit the points it earns.

This is where AI output stops being a suggestion: whatever the extractor read, the values
arriving here are the ones the member reviewed, and they still go through
`RunEntry.create()`'s sanity rules before anything is stored.

Evidence reuse is handled in two different ways on purpose:
  - the SAME member submitting the same image twice is a duplicate, and refused;
  - a DIFFERENT member submitting an image someone else already used is flagged for a
    human to look at, not auto-refused — two people can legitimately photograph the same
    finish-line board, and accusing a member automatically would be worse than a review.

Points are settled in the same transaction as the run, by reconciling the ledger against
what each active campaign's policy says the member has now earned — not by crediting a
fixed amount per run. That distinction is what makes a "10 km in a day" campaign work,
where a day is carried over the line by several runs together.

A flagged run still earns: the admin review that rejects it is what reconciles the points
back down, which keeps one path for "these points were wrong" instead of two.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from app.application.ports.run_submission_unit_of_work import RunSubmissionUnitOfWork
from app.application.services.points_reconciliation import (
    reconcile_all_campaigns,
    valid_runs_of,
)
from app.domain.entities import ReviewStatus, RunEntry, RunSource
from app.domain.errors import DuplicateEvidence, InvalidRunError, NotAuthorized
from app.domain.evidence import digest_from_key, is_owned_by


@dataclass(frozen=True)
class SubmitRunCommand:
    member_id: UUID  # from the verified token
    distance_km: Decimal
    duration_seconds: int
    run_date: date
    image_key: str
    source: RunSource


class SubmitRun:
    def __init__(self, uow: RunSubmissionUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: SubmitRunCommand) -> RunEntry:
        # The key must be one this member uploaded — otherwise a caller could attach
        # somebody else's photo to their own run.
        if not is_owned_by(cmd.image_key, str(cmd.member_id)):
            raise NotAuthorized("evidence does not belong to this member")

        digest = digest_from_key(cmd.image_key)

        with self._uow as uow:
            existing = uow.runs.find_by_evidence_hash(digest)
            if any(run.member_id == cmd.member_id for run in existing):
                raise DuplicateEvidence("this image has already been submitted")

            now = uow.clock.now()
            active = uow.campaigns.list_active()
            # A run has to belong to something. The windows come from the campaign rows,
            # never from a hardcoded date, so next year's activity needs no code change.
            if cmd.run_date > now.date():
                raise InvalidRunError("run_date cannot be in the future")
            if not any(campaign.contains(cmd.run_date) for campaign in active):
                raise InvalidRunError(
                    f"{cmd.run_date} is outside every active campaign's window"
                )

            run = RunEntry.create(
                member_id=cmd.member_id,
                distance_km=cmd.distance_km,
                duration_seconds=cmd.duration_seconds,
                run_date=cmd.run_date,
                evidence_key=cmd.image_key,
                evidence_sha256=digest,
                source=cmd.source,
                now=now,
                # Used by someone else already: a human decides, the run is still recorded.
                review_status=ReviewStatus.FLAGGED if existing else ReviewStatus.OK,
            )
            uow.runs.add(run)

            # Earning is a reconciliation, not a per-run credit: in a daily-threshold
            # campaign this run may have pushed its DAY over the line together with
            # earlier runs, and no single run owns that point.
            reconcile_all_campaigns(
                ledger=uow.ledger,
                campaigns=active,
                member_id=run.member_id,
                # add() has already flushed the new run, so it is in this list.
                valid_runs=valid_runs_of(uow.runs.list_by_member(run.member_id)),
                trigger_run_id=run.id,
                now=now,
            )
            uow.commit()

        return run
