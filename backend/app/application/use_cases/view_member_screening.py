"""The superuser reading ONE member's pre-exercise screening.

The same three conditions as reading someone's health data, for the same reasons:

  1. the actor's role permits it — checked here as well as at the router, because the
     router gate is convenience and this is the control;
  2. the answers exist. A member who has not been screened yields nothing rather than a
     row of assumed "no"s;
  3. the access is written to audit_log AND COMMITTED before anything is returned. If
     the audit write fails, the whole thing fails and the caller gets nothing: an access
     that cannot be accounted for must not happen.

Superuser rather than admin. This is a member's cardiac and medication history, and the
club has one person answerable for it.

The audit row records that a screening was looked at and how many answers were "yes" —
never which questions, and never the answers themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.sensitive_view_unit_of_work import SensitiveViewUnitOfWork
from app.domain.audit import AuditAction, AuditEntry
from app.domain.entities import Member, MemberRole
from app.domain.errors import MemberNotFound, NotAuthorized
from app.domain.screening import Screening


@dataclass(frozen=True)
class ViewMemberScreeningCommand:
    actor_id: UUID  # from the verified token
    subject_id: UUID  # only ever supplied on an admin endpoint


@dataclass(frozen=True)
class MemberScreeningView:
    subject: Member
    screening: Screening | None


class ViewMemberScreening:
    def __init__(self, uow: SensitiveViewUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: ViewMemberScreeningCommand) -> MemberScreeningView:
        with self._uow as uow:
            actor = uow.members.get(cmd.actor_id)
            if actor is None:
                raise MemberNotFound(str(cmd.actor_id))
            if actor.role is not MemberRole.SUPERUSER:
                raise NotAuthorized("superuser only")

            subject = uow.members.get(cmd.subject_id)
            if subject is None:
                raise MemberNotFound(str(cmd.subject_id))

            screening = uow.screenings.get_for_member(cmd.subject_id)

            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.VIEW_SCREENING,
                    subject_member_id=subject.id,
                    # Context only. Never which questions, never the answers.
                    detail={
                        "has_screening": screening is not None,
                        "yes_count": screening.yes_count if screening else 0,
                    },
                    now=uow.clock.now(),
                )
            )
            # Commit BEFORE returning: past this line the access is on the record. If
            # this raises, the `with` block rolls back and nothing is returned.
            uow.commit()

        return MemberScreeningView(subject=subject, screening=screening)
