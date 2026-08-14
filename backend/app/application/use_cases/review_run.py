"""An admin decides whether a submitted run counts.

Rejecting is not a delete: the run stays, marked, and the points it was worth are
reconciled back down. That way the history still shows what was submitted and what was
decided about it.

Points are NOT reversed row-by-row. In a daily-threshold campaign the rejected run may
never have carried a ledger row of its own while still being the reason a day qualified,
so the ledger is reconciled against the policy over the member's remaining valid runs —
the same operation that runs on submission.

Every decision writes an audit row: accountability for a mutation doesn't depend on how
sensitive the data was to read.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from app.application.ports.run_review_unit_of_work import RunReviewUnitOfWork
from app.application.services.points_reconciliation import (
    reconcile_all_campaigns,
    valid_runs_of,
)
from app.domain.audit import AuditAction, AuditEntry
from app.domain.entities import ReviewStatus, RunEntry
from app.domain.errors import MemberNotFound, NotAuthorized, RunNotFound


@dataclass(frozen=True)
class ReviewRunCommand:
    actor_id: UUID  # from the verified token
    run_id: UUID
    decision: ReviewStatus


class ReviewRun:
    def __init__(self, uow: RunReviewUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: ReviewRunCommand) -> RunEntry:
        with self._uow as uow:
            actor = uow.members.get(cmd.actor_id)
            if actor is None:
                raise MemberNotFound(str(cmd.actor_id))
            # Mutations are the superuser's alone; an admin may look but not decide.
            # If admins should help review one day, that is a new `may_moderate`
            # capability on the role, not a loosening of this check.
            if not actor.role.may_edit_records:
                raise NotAuthorized("superuser only")

            run = uow.runs.get(cmd.run_id)
            if run is None:
                raise RunNotFound(str(cmd.run_id))

            reviewed = replace(run, review_status=cmd.decision)
            uow.runs.set_review_status(run.id, cmd.decision)

            now = uow.clock.now()
            # Whatever the decision, settle the member's points against it. Approving a
            # previously rejected run credits them back by exactly the same route.
            reconcile_all_campaigns(
                ledger=uow.ledger,
                # list_all, NOT list_active: a campaign that has been closed since the
                # run was submitted still owes a correction. `is_active` says whether a
                # campaign accepts new work, not whether its points are final — and each
                # policy filters by its own date window anyway, so campaigns that have
                # nothing to do with this run reconcile to a delta of zero.
                campaigns=uow.campaigns.list_all(),
                member_id=run.member_id,
                valid_runs=valid_runs_of(uow.runs.list_by_member(run.member_id)),
                trigger_run_id=run.id,
                now=now,
            )

            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.REVIEW_RUN,
                    subject_member_id=run.member_id,
                    # Context only: ids and the decision, never the evidence itself.
                    detail={"run_id": run.id, "decision": cmd.decision.value},
                    now=now,
                )
            )
            uow.commit()

        return reviewed
