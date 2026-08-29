"""An admin reading ONE member's contact details.

Phone number, sex, birth year, emergency contact. Collected so somebody can be reached
if a member collapses on a run — which is exactly why looking at them is an event worth
recording: the club can show it opened the details when it needed to, and can show it
did not do so otherwise.

Audited on the same terms as health and screening: the row is committed before the data
is returned, so an access that cannot be accounted for does not happen. The row says
whose details were opened, never what they contained.

Deliberately NOT gated on consent, unlike those two. The lawful basis here is the club's
interest in the safety of the people running for it (PDPA มาตรา 24), not the consent that
covers holding health measurements — so a member who withdraws that consent stops the
club processing their weight and their screening, and stays reachable if they collapse on
a run. Gating this would have taken the phone number away at the moment it was collected
for.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.contact_view_unit_of_work import ContactViewUnitOfWork
from app.domain.audit import AuditAction, AuditEntry
from app.domain.entities import Member
from app.domain.errors import MemberNotFound, NotAuthorized


@dataclass(frozen=True)
class ViewMemberContactCommand:
    actor_id: UUID  # from the verified token
    subject_id: UUID  # only ever supplied on an admin endpoint


class ViewMemberContact:
    def __init__(self, uow: ContactViewUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: ViewMemberContactCommand) -> Member:
        with self._uow as uow:
            actor = uow.members.get(cmd.actor_id)
            if actor is None:
                raise MemberNotFound(str(cmd.actor_id))
            if not actor.role.may_view_others_health:
                raise NotAuthorized("admin only")

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
