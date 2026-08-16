from typing import Protocol
from uuid import UUID

from app.domain.announcement import Announcement


class AnnouncementRepository(Protocol):
    def list_published(self, limit: int | None = None) -> list[Announcement]:
        """What the public sees: published only, newest first.

        The filter lives here rather than at the caller because this list is served
        without a token — an unpublished draft reaching it is a leak, not a display bug.
        """
        ...

    def list_all(self) -> list[Announcement]:
        """Drafts and hidden notices included — the superuser's own screen."""
        ...

    def get(self, announcement_id: UUID) -> Announcement | None: ...

    def add(self, announcement: Announcement) -> None: ...

    def save(self, announcement: Announcement) -> None: ...
