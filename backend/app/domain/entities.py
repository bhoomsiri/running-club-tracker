"""Core entities. Frozen dataclasses; every construction path goes through `create()`
so validation lives in exactly one place."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.errors import InvalidMemberError, InvalidRunError

MAX_DISPLAY_NAME = 120

# Sanity bounds — deliberately the same numbers as the DB CHECK constraints, so a value
# the domain accepts can never be rejected by the database.
MAX_DISTANCE_KM = Decimal("200")
MAX_DURATION_SECONDS = 86_400
DISTANCE_PRECISION = Decimal("0.001")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class MemberRole(StrEnum):
    MEMBER = "member"
    ADMIN = "admin"
    SUPERUSER = "superuser"

    @property
    def may_view_others_health(self) -> bool:
        """Admins and the superuser may read another member's health data — and every
        such read must be written to audit_log (PDPA accountability)."""
        return self in (MemberRole.ADMIN, MemberRole.SUPERUSER)

    @property
    def may_edit_records(self) -> bool:
        """Correcting other people's data is the superuser's alone."""
        return self is MemberRole.SUPERUSER


@dataclass(frozen=True)
class Member:
    id: UUID
    clerk_user_id: str
    display_name: str
    role: MemberRole
    created_at: datetime
    deleted_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        clerk_user_id: str,
        display_name: str,
        now: datetime,
        role: MemberRole = MemberRole.MEMBER,
    ) -> Member:
        return cls(
            id=uuid4(),
            clerk_user_id=clerk_user_id,
            display_name=validate_display_name(display_name),
            role=role,
            created_at=now,
        )


def validate_display_name(name: str) -> str:
    """The one place the name rule lives — used when a member is created and when they
    rename themselves."""
    cleaned = name.strip()
    if not cleaned:
        raise InvalidMemberError("display_name cannot be empty")
    if len(cleaned) > MAX_DISPLAY_NAME:
        raise InvalidMemberError(f"display_name cannot exceed {MAX_DISPLAY_NAME} characters")
    return cleaned


class RunSource(StrEnum):
    APP_SCREENSHOT = "app_screenshot"
    MANUAL_PHOTO = "manual_photo"


class ReviewStatus(StrEnum):
    OK = "ok"
    FLAGGED = "flagged"
    REJECTED = "rejected"


@dataclass(frozen=True)
class RunEntry:
    """One submitted run. The single source of truth for every campaign's progress."""

    id: UUID
    member_id: UUID
    distance_km: Decimal
    duration_seconds: int
    run_date: date
    evidence_key: str
    evidence_sha256: str
    source: RunSource
    review_status: ReviewStatus
    created_at: datetime

    @property
    def is_rejected(self) -> bool:
        """A rejected run earns nothing and counts toward no campaign's progress.
        Flagged runs still count — they are awaiting a decision, not refused."""
        return self.review_status is ReviewStatus.REJECTED

    @classmethod
    def create(
        cls,
        *,
        member_id: UUID,
        distance_km: Decimal,
        duration_seconds: int,
        run_date: date,
        evidence_key: str,
        evidence_sha256: str,
        source: RunSource,
        now: datetime,
        review_status: ReviewStatus = ReviewStatus.OK,
    ) -> RunEntry:
        if not isinstance(distance_km, Decimal):
            # Guarding the type here is the point: a float would silently lose precision
            # on the way to numeric(6,3).
            raise InvalidRunError("distance_km must be a Decimal, not a float")
        if distance_km <= 0 or distance_km > MAX_DISTANCE_KM:
            raise InvalidRunError(f"distance_km must be between 0 and {MAX_DISTANCE_KM}")
        if duration_seconds <= 0 or duration_seconds > MAX_DURATION_SECONDS:
            raise InvalidRunError(f"duration_seconds must be between 0 and {MAX_DURATION_SECONDS}")
        if run_date > now.date():
            raise InvalidRunError("run_date cannot be in the future")
        if not evidence_key.strip():
            raise InvalidRunError("evidence_key is required")
        if not _SHA256_RE.match(evidence_sha256):
            raise InvalidRunError("evidence_sha256 must be 64 lowercase hex characters")

        return cls(
            id=uuid4(),
            member_id=member_id,
            distance_km=distance_km.quantize(DISTANCE_PRECISION),
            duration_seconds=duration_seconds,
            run_date=run_date,
            evidence_key=evidence_key.strip(),
            evidence_sha256=evidence_sha256,
            source=source,
            review_status=review_status,
            created_at=now,
        )
