"""The club's news — the one endpoint in this app that answers without a token.

It has to be: the landing page is for people who have not signed up, and a notice board
they cannot read is not an invitation. So this router deliberately has no
`get_current_member_id` dependency, and that absence is the feature.

Two things follow from it and are worth keeping in mind before adding anything here:
published rows are all that may ever be returned, which is enforced by the repository
query rather than by a filter a caller could forget; and the limit, since there is no
member to key on, falls back to the caller's address — SlowAPIMiddleware applies the
global default to every route, this one included.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_list_published_announcements_uc
from app.api.schemas import AnnouncementResponse
from app.application.use_cases.list_announcements import ListPublishedAnnouncements

router = APIRouter(tags=["announcements"])


@router.get("/announcements", response_model=list[AnnouncementResponse])
def list_announcements(
    use_case: Annotated[
        ListPublishedAnnouncements, Depends(get_list_published_announcements_uc)
    ],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> list[AnnouncementResponse]:
    """Published notices, newest first. No authentication, by design."""
    return [AnnouncementResponse.from_entity(a) for a in use_case.execute(limit)]
