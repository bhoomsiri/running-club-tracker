"""Club news.

The one thing that makes this different from everything else in the app: a published
announcement is readable by anyone on the internet, with no token. That is the point —
the landing page has to say something to a nurse who has not signed up yet — but it also
means this is the only table whose contents can leak by design rather than by mistake.
Nothing personal, nothing about anyone's health, belongs in a `body`. The rule cannot be
enforced from here (it is free text a human types), so it is said in the admin form as
well, where the person typing will see it.

Unpublishing rather than deleting, for the same reason rewards are retired: a notice
someone has already read and asked about should still be findable by whoever wrote it.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.errors import InvalidAnnouncementError

MAX_TITLE = 200
# Long enough for a real notice with a schedule in it, short enough that a paste of an
# entire document is refused rather than stored.
MAX_BODY = 20_000


@dataclass(frozen=True)
class Announcement:
    id: UUID
    title: str
    body: str
    is_published: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(
        cls,
        *,
        title: str,
        body: str,
        now: datetime,
        is_published: bool = False,
    ) -> Announcement:
        """Unpublished unless asked otherwise: a draft that goes public the instant it is
        saved is a draft nobody can proofread."""
        return cls(
            id=uuid4(),
            title=_required("title", title, MAX_TITLE),
            body=_required("body", body, MAX_BODY),
            is_published=is_published,
            created_at=now,
            updated_at=now,
        )

    def with_changes(
        self,
        *,
        now: datetime,
        title: str | None = None,
        body: str | None = None,
        is_published: bool | None = None,
    ) -> Announcement:
        """Each field omitted means unchanged, so toggling publication does not require
        resending the text."""
        return replace(
            self,
            title=_required("title", title, MAX_TITLE) if title is not None else self.title,
            body=_required("body", body, MAX_BODY) if body is not None else self.body,
            is_published=(
                is_published if is_published is not None else self.is_published
            ),
            updated_at=now,
        )


def _required(field_name: str, value: str, limit: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InvalidAnnouncementError(f"{field_name} cannot be empty")
    if len(cleaned) > limit:
        raise InvalidAnnouncementError(f"{field_name} cannot exceed {limit} characters")
    return cleaned
