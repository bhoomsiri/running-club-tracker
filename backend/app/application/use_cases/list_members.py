"""The admin roster: names and roles only.

Deliberately carries NO health data, which is why this endpoint writes no audit rows.
Seeing that a club has 100 members is not access to anyone's sensitive data; opening one
of them is, and that is a different use case which audits every time.
"""

from __future__ import annotations

from uuid import UUID

from app.application.ports.member_repository import MemberRepository
from app.domain.entities import Member
from app.domain.errors import MemberNotFound, NotAuthorized


class ListMembers:
    def __init__(self, members: MemberRepository) -> None:
        self._members = members

    def execute(self, actor_id: UUID) -> list[Member]:
        actor = self._members.get(actor_id)
        if actor is None:
            raise MemberNotFound(str(actor_id))
        if not actor.role.may_view_others_health:
            raise NotAuthorized("admin only")
        return self._members.list_all()
