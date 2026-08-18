"""The superuser making somebody a helper, or taking it back.

This is the one endpoint that hands out access to other people's data, so it is the one
place worth being blunt about what it will not do:

- **Only the superuser may call it.** An admin cannot promote a friend, and cannot
  demote the admin who is about to review their run.
- **It cannot create a superuser.** `ASSIGNABLE` is member and admin only. The superuser
  comes from the verified Clerk webhook or the bootstrap setting, and the database
  enforces at most one — a second one arriving through here would either violate that
  index or, worse, not.
- **It cannot touch the superuser's own row.** Nobody demotes the person who is meant to
  be able to fix things, including themselves by mistake.

Every successful call writes an audit row, the no-op included: "who made whom what, and
when" is the question this table exists to answer, and a call that changed nothing is
still somebody having tried. The row carries the old and the new role, never a name.

The change takes effect on the next request. Roles are read from the member row on every
authenticated request and never from the token, so a demoted admin loses access as soon
as their current request finishes — there is no cached claim to wait out.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from app.application.ports.admin_unit_of_work import AdminUnitOfWork
from app.application.use_cases.manage_campaigns import _require_superuser
from app.domain.audit import AuditAction, AuditEntry
from app.domain.entities import Member, MemberRole
from app.domain.errors import MemberNotFound, NotAuthorized

# What this endpoint is allowed to write. Not a validation detail — it is the rule that
# keeps a second superuser from existing.
ASSIGNABLE = (MemberRole.MEMBER, MemberRole.ADMIN)


@dataclass(frozen=True)
class SetMemberRoleCommand:
    actor_id: UUID  # from the verified token
    subject_id: UUID
    role: MemberRole


class SetMemberRole:
    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: SetMemberRoleCommand) -> Member:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            if cmd.role not in ASSIGNABLE:
                raise NotAuthorized("only member and admin can be granted here")

            subject = uow.members.get(cmd.subject_id)
            if subject is None:
                raise MemberNotFound(str(cmd.subject_id))
            if subject.role is MemberRole.SUPERUSER:
                raise NotAuthorized("the superuser's role cannot be changed")

            previous = subject.role
            # Idempotent: setting the role somebody already has succeeds and changes
            # nothing, so a double tap on a slow connection is not an error to explain.
            if previous is not cmd.role:
                uow.members.set_role(subject.id, cmd.role)

            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.CHANGE_ROLE,
                    subject_member_id=subject.id,
                    detail={"from_role": previous.value, "to_role": cmd.role.value},
                    now=uow.clock.now(),
                )
            )
            uow.commit()

        return replace(subject, role=cmd.role)
