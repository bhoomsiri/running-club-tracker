"""The superuser reading ONE member's contact details.

Phone number, sex, birth year, emergency contact. Collected so somebody can be reached
if a member collapses on a run — which is exactly why looking at them is an event worth
recording: the club can show it opened the details when it needed to, and can show it
did not do so otherwise.

Audited on the same terms as health and screening: the row is committed before the data
is returned, so an access that cannot be accounted for does not happen. The row says
whose details were opened, never what they contained.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.sensitive_view_unit_of_work import SensitiveViewUnitOfWork
from app.domain.audit import AuditAction, AuditEntry
from app.domain.entities import Member, MemberRole
from app.domain.errors import MemberNotFound, NotAuthorized


@dataclass(frozen=True)
class ViewMemberContactCommand:
    actor_id: UUID  # from the verified token
    subject_id: UUID  # only ever supplied on an admin endpoint


class ViewMemberContact:
    def __init__(self, uow: SensitiveViewUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: ViewMemberContactCommand) -> Member:
        with self._uow as uow:
            actor = uow.members.get(cmd.actor_id)
            if actor is None:
                raise MemberNotFound(str(cmd.actor_id))
            if actor.role is not MemberRole.SUPERUSER:
                raise NotAuthorized("superuser only")

            subject = uow.members.get(cmd.subject_id)
            if subject is None:
                raise MemberNotFound(str(cmd.subject_id))

            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.VIEW_CONTACT,
                    subject_member_id=subject.id,
                    # Whether there was anything to see, not what it was.
                    detail={"profile_complete": subject.profile.is_complete},
                    now=uow.clock.now(),
                )
            )
            uow.commit()

        return subject
