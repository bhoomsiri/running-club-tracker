"""Writing and editing club news. Superuser only, and audited.

Audited even though nothing here is personal data: publishing is the one action in this
app that puts words in front of the public under the club's name, and "who posted that?"
has to have an answer. The detail carries the id and whether it is now public — never
the text, which belongs in the row rather than in a trail that outlives it.

There is no delete. Hiding is `is_published=False`, which takes a notice off every screen
that shows it while leaving it where whoever wrote it can find it again.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.admin_unit_of_work import AdminUnitOfWork
from app.application.use_cases.manage_campaigns import _require_superuser
from app.domain.announcement import Announcement
from app.domain.audit import AuditAction, AuditEntry
from app.domain.errors import AnnouncementNotFound


@dataclass(frozen=True)
class CreateAnnouncementCommand:
    actor_id: UUID
    title: str
    body: str
    is_published: bool = False


@dataclass(frozen=True)
class UpdateAnnouncementCommand:
    actor_id: UUID
    announcement_id: UUID
    title: str | None = None
    body: str | None = None
    is_published: bool | None = None


class CreateAnnouncement:
    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: CreateAnnouncementCommand) -> Announcement:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            announcement = Announcement.create(
                title=cmd.title,
                body=cmd.body,
                is_published=cmd.is_published,
                now=uow.clock.now(),
            )
            uow.announcements.add(announcement)
            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.CREATE_ANNOUNCEMENT,
                    now=uow.clock.now(),
                    detail={
                        "announcement_id": announcement.id,
                        "published": announcement.is_published,
                    },
                )
            )
            uow.commit()
        return announcement


class UpdateAnnouncement:
    def __init__(self, uow: AdminUnitOfWork) -> None:
        self._uow = uow

    def execute(self, cmd: UpdateAnnouncementCommand) -> Announcement:
        with self._uow as uow:
            actor = _require_superuser(uow, cmd.actor_id)

            announcement = uow.announcements.get(cmd.announcement_id)
            if announcement is None:
                raise AnnouncementNotFound(str(cmd.announcement_id))

            updated = announcement.with_changes(
                title=cmd.title,
                body=cmd.body,
                is_published=cmd.is_published,
                now=uow.clock.now(),
            )
            uow.announcements.save(updated)
            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.UPDATE_ANNOUNCEMENT,
                    now=uow.clock.now(),
                    detail={
                        "announcement_id": updated.id,
                        # The state it is in now, so the trail shows when something went
                        # public and when it came back down.
                        "published": updated.is_published,
                    },
                )
            )
            uow.commit()
        return updated
