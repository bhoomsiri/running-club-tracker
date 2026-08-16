"""Reading the club's news.

Two use cases rather than one with a flag. The public list is served to callers with no
token at all, so "published only" has to be a property of the code path itself — a
parameter that decides it is a parameter that can be got wrong once and expose every
draft. The admin list is a different question asked by a different person.
"""

from __future__ import annotations

from uuid import UUID

from app.application.ports.announcement_repository import AnnouncementRepository
from app.application.ports.member_repository import MemberRepository
from app.domain.announcement import Announcement
from app.domain.entities import MemberRole
from app.domain.errors import MemberNotFound, NotAuthorized


class ListPublishedAnnouncements:
    """No actor: this is the one thing in the app anyone may read."""

    def __init__(self, announcements: AnnouncementRepository) -> None:
        self._announcements = announcements

    def execute(self, limit: int | None = None) -> list[Announcement]:
        return self._announcements.list_published(limit)


class ListAllAnnouncements:
    def __init__(
        self, members: MemberRepository, announcements: AnnouncementRepository
    ) -> None:
        self._members = members
        self._announcements = announcements

    def execute(self, actor_id: UUID) -> list[Announcement]:
        actor = self._members.get(actor_id)
        if actor is None:
            raise MemberNotFound(str(actor_id))
        if actor.role is not MemberRole.SUPERUSER:
            raise NotAuthorized("superuser only")
        return self._announcements.list_all()
