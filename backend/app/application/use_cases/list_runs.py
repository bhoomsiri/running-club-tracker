"""Listing runs, with a short-lived link to each evidence image.

This is where the image IDOR is closed. A presigned URL is a bearer capability: whoever
holds it can fetch the object until it expires, with no further checks. So a URL is only
ever minted for runs that came out of a query already scoped to the entitled member —
the owner here, or an admin in `ListMemberRuns`. There is deliberately no endpoint that
turns an arbitrary key into a URL.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from app.application.ports.image_storage import ImageStorage
from app.application.ports.member_repository import MemberRepository
from app.application.ports.run_repository import RunRepository
from app.domain.entities import RunEntry
from app.domain.errors import MemberNotFound, NotAuthorized

# Long enough for a page to render the images, short enough that a leaked URL is stale
# almost immediately.
DEFAULT_URL_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class RunWithEvidence:
    run: RunEntry
    evidence_url: str


class ListMyRuns:
    def __init__(
        self,
        runs: RunRepository,
        storage: ImageStorage,
        url_ttl: timedelta = DEFAULT_URL_TTL,
    ) -> None:
        self._runs = runs
        self._storage = storage
        self._url_ttl = url_ttl

    def execute(self, member_id: UUID) -> list[RunWithEvidence]:
        # Scoped by member_id first; URLs are minted only for what comes back.
        return [
            RunWithEvidence(run, self._storage.presigned_url(run.evidence_key, self._url_ttl))
            for run in self._runs.list_by_member(member_id)
        ]


class ListMemberRuns:
    """The admin equivalent: someone else's runs, role-gated.

    Not audited: runs and their photos are ordinary personal data, not the sensitive
    health data that carries the accountability obligation. If evidence photos are ever
    treated as sensitive, this needs the same audit write as ViewMemberHealth.
    """

    def __init__(
        self,
        members: MemberRepository,
        runs: RunRepository,
        storage: ImageStorage,
        url_ttl: timedelta = DEFAULT_URL_TTL,
    ) -> None:
        self._members = members
        self._runs = runs
        self._storage = storage
        self._url_ttl = url_ttl

    def execute(self, actor_id: UUID, subject_id: UUID) -> list[RunWithEvidence]:
        actor = self._members.get(actor_id)
        if actor is None:
            raise MemberNotFound(str(actor_id))
        if not actor.role.may_view_others_health:
            raise NotAuthorized("admin only")
        if self._members.get(subject_id) is None:
            raise MemberNotFound(str(subject_id))

        return [
            RunWithEvidence(run, self._storage.presigned_url(run.evidence_key, self._url_ttl))
            for run in self._runs.list_by_member(subject_id)
        ]
