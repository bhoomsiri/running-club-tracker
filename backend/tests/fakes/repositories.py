"""In-memory read-side fakes. Each one filters by member_id exactly like the real
repository will, so a use case that leaks another member's data fails here too."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from uuid import UUID

from app.domain.campaign import Campaign
from app.domain.entities import Member, MemberProfile, MemberRole, ReviewStatus, RunEntry
from app.domain.errors import MemberAlreadyExists
from app.domain.health import HealthRecord
from app.domain.screening import Screening


class FakeMemberRepository:
    def __init__(self, members: list[Member] | None = None) -> None:
        self._items = {m.id: m for m in members or []}

    def get(self, member_id: UUID) -> Member | None:
        member = self._items.get(member_id)
        return None if member is None or member.deleted_at is not None else member

    def get_by_clerk_id(self, clerk_user_id: str) -> Member | None:
        return next(
            (m for m in self._items.values() if m.clerk_user_id == clerk_user_id), None
        )

    def get_superuser(self) -> Member | None:
        return next(
            (m for m in self._items.values() if m.role is MemberRole.SUPERUSER), None
        )

    def list_all(self) -> list[Member]:
        return [m for m in self._items.values() if m.deleted_at is None]

    def add(self, member: Member) -> None:
        # Mirrors uq_member_clerk_user_id, so the race path is exercised in unit tests.
        if self.get_by_clerk_id(member.clerk_user_id) is not None:
            raise MemberAlreadyExists(member.clerk_user_id)
        self._items[member.id] = member

    def set_role(self, member_id: UUID, role: MemberRole) -> None:
        self._items[member_id] = replace(self._items[member_id], role=role)

    def set_display_name(self, member_id: UUID, display_name: str) -> None:
        self._items[member_id] = replace(self._items[member_id], display_name=display_name)

    def set_avatar(self, member_id: UUID, image_url: str | None, has_image: bool) -> None:
        self._items[member_id] = replace(
            self._items[member_id], image_url=image_url, has_image=has_image
        )

    def set_profile(self, member_id: UUID, profile: MemberProfile) -> None:
        self._items[member_id] = replace(self._items[member_id], profile=profile)


class FakeScreeningRepository:
    def __init__(self, screenings: list[Screening] | None = None) -> None:
        self._items: dict[UUID, Screening] = {s.member_id: s for s in screenings or []}

    def get_for_member(self, member_id: UUID) -> Screening | None:
        return self._items.get(member_id)

    def upsert(self, screening: Screening) -> Screening:
        # member_id is unique in the real table, so one per member here too.
        self._items[screening.member_id] = screening
        return screening


class FakeRunRepository:
    def __init__(self, runs: list[RunEntry] | None = None) -> None:
        self._items: list[RunEntry] = list(runs or [])

    def add(self, run: RunEntry) -> None:
        self._items.append(run)

    def get(self, run_id: UUID) -> RunEntry | None:
        return next((r for r in self._items if r.id == run_id), None)

    def list_all(self) -> list[RunEntry]:
        return list(self._items)

    def set_review_status(self, run_id: UUID, status: ReviewStatus) -> None:
        self._items = [
            replace(r, review_status=status) if r.id == run_id else r for r in self._items
        ]

    def list_by_member(self, member_id: UUID) -> list[RunEntry]:
        return [r for r in self._items if r.member_id == member_id]

    def find_by_evidence_hash(self, digest: str) -> list[RunEntry]:
        return [r for r in self._items if r.evidence_sha256 == digest]

    def count_in_window(self, start: date, end: date) -> int:
        return sum(1 for r in self._items if start <= r.run_date <= end)

    def has_flagged(self, member_id: UUID) -> bool:
        return any(
            r.member_id == member_id and r.review_status is ReviewStatus.FLAGGED
            for r in self._items
        )


class FakeCampaignRepository:
    def __init__(self, campaigns: list[Campaign] | None = None) -> None:
        self._items: list[Campaign] = list(campaigns or [])

    def get(self, campaign_id: UUID) -> Campaign | None:
        return next((c for c in self._items if c.id == campaign_id), None)

    def get_by_code(self, code: str) -> Campaign | None:
        return next((c for c in self._items if c.code == code), None)

    def list_all(self) -> list[Campaign]:
        return list(self._items)

    def add(self, campaign: Campaign) -> None:
        self._items.append(campaign)

    def save(self, campaign: Campaign) -> None:
        self._items = [campaign if c.id == campaign.id else c for c in self._items]

    def list_active(self) -> list[Campaign]:
        return [c for c in self._items if c.is_active]


class FakeHealthRepository:
    def __init__(self, records: list[HealthRecord] | None = None) -> None:
        self._items: list[HealthRecord] = list(records or [])

    def list_by_member(self, member_id: UUID) -> list[HealthRecord]:
        return [r for r in self._items if r.member_id == member_id]

    def upsert(self, record: HealthRecord) -> HealthRecord:
        existing = next(
            (
                r
                for r in self._items
                if r.member_id == record.member_id
                and r.campaign_id == record.campaign_id
                and r.phase is record.phase
            ),
            None,
        )
        if existing is None:
            self._items.append(record)
            return record
        # Correcting a measurement keeps the original row's id.
        updated = replace(record, id=existing.id)
        self._items = [updated if r is existing else r for r in self._items]
        return updated
