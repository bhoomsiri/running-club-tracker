"""Core entities. Frozen dataclasses; every construction path goes through `create()`
so validation lives in exactly one place."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.calendar import club_today
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


class Sex(StrEnum):
    """Recorded because it changes how exercise risk is read, not for anything else.
    Sensitive: it is never part of a response an admin can reach without an audit row."""

    MALE = "male"
    FEMALE = "female"


class ShirtSize(StrEnum):
    """Which finisher shirt to order for this member.

    A closed set rather than free text, because these values end up on a purchase order:
    "L" and "ไซส์ L" and "l" are one size to a person and three to a spreadsheet. The
    club prints one run of shirts and cannot re-order for a typo.
    """

    XS = "XS"
    S = "S"
    M = "M"
    L = "L"
    XL = "XL"
    XL2 = "2XL"
    XL3 = "3XL"
    XL4 = "4XL"
    XL5 = "5XL"


@dataclass(frozen=True)
class MemberProfile:
    """What the club needs in order to run an activity safely.

    All optional on the entity, because a member exists from their first authenticated
    request and fills this in afterwards — `is_complete` is what the onboarding gate
    asks. The emergency contact is the reason this is collected at all: someone has to
    be reachable if a member collapses on a run.

    `position` and `department` are the member's job and unit at the hospital. They are
    ordinary personal data rather than the มาตรา 26 kind — which is why, unlike `sex`
    and the emergency contact, they may appear in an admin list without an audit row.
    They stay free text here even though the form offers a picker: the list of units is
    the hospital's to change, not this app's, and a member whose unit is missing from it
    types their own. A column constrained to today's org chart would reject them.

    `shirt_size` is different — it is a closed set (`ShirtSize`), because it is read off
    when the finisher shirts are ordered and there is no re-order for a typo.
    """

    full_name_th: str | None = None
    birth_year: int | None = None
    sex: Sex | None = None
    position: str | None = None
    department: str | None = None
    shirt_size: ShirtSize | None = None
    phone: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None

    @property
    def is_complete(self) -> bool:
        return all(
            value is not None
            for value in (
                self.full_name_th,
                self.birth_year,
                self.sex,
                self.position,
                self.department,
                self.shirt_size,
                self.phone,
                self.emergency_contact_name,
                self.emergency_contact_phone,
            )
        )


@dataclass(frozen=True)
class Member:
    id: UUID
    clerk_user_id: str
    display_name: str
    role: MemberRole
    created_at: datetime
    profile: MemberProfile = field(default_factory=MemberProfile)
    deleted_at: datetime | None = None

    @property
    def preferred_name(self) -> str:
        """What to show wherever a member is named.

        The Thai full name once they have given it, because that is what the club calls
        them and what belongs on a screening form. `display_name` — which comes from
        Clerk — is the fallback until then.
        """
        return self.profile.full_name_th or self.display_name

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

    def with_profile(self, profile: MemberProfile) -> Member:
        return replace(self, profile=profile)


MAX_FULL_NAME = 200
MAX_CONTACT_NAME = 200
# Hospital job titles and unit names run long ("พยาบาลวิชาชีพชำนาญการ", "กลุ่มงาน…").
MAX_WORK_FIELD = 160
MIN_BIRTH_YEAR = 1900
# Nobody younger than this is running a club activity unaccompanied; it also catches a
# birth year typed where the current year was meant.
MIN_AGE_YEARS = 10

_PHONE_RE = re.compile(r"^0\d{8,9}$")


def build_profile(
    *,
    full_name_th: str,
    birth_year: int,
    sex: Sex,
    position: str,
    department: str,
    shirt_size: ShirtSize,
    phone: str,
    emergency_contact_name: str,
    emergency_contact_phone: str,
    now: datetime,
) -> MemberProfile:
    """The one place a profile is validated, whichever path builds it."""
    return MemberProfile(
        full_name_th=_required_text("full_name_th", full_name_th, MAX_FULL_NAME),
        birth_year=_validate_birth_year(birth_year, now),
        sex=sex,
        position=_required_text("position", position, MAX_WORK_FIELD),
        department=_required_text("department", department, MAX_WORK_FIELD),
        shirt_size=shirt_size,
        phone=_validate_phone("phone", phone),
        emergency_contact_name=_required_text(
            "emergency_contact_name", emergency_contact_name, MAX_CONTACT_NAME
        ),
        emergency_contact_phone=_validate_phone(
            "emergency_contact_phone", emergency_contact_phone
        ),
    )


def _required_text(field_name: str, value: str, limit: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise InvalidMemberError(f"{field_name} cannot be empty")
    if len(cleaned) > limit:
        raise InvalidMemberError(f"{field_name} cannot exceed {limit} characters")
    return cleaned


def _validate_birth_year(year: int, now: datetime) -> int:
    if not (MIN_BIRTH_YEAR <= year <= now.year - MIN_AGE_YEARS):
        raise InvalidMemberError(
            f"birth_year must be between {MIN_BIRTH_YEAR} and {now.year - MIN_AGE_YEARS}"
        )
    return year


def _validate_phone(field_name: str, value: str) -> str:
    """Stored as digits only, so the same number typed three ways is one number.

    An emergency contact that cannot be dialled is worse than none — it looks like the
    club has one.
    """
    digits = re.sub(r"[\s-]", "", value.strip())
    if not _PHONE_RE.match(digits):
        raise InvalidMemberError(
            f"{field_name} must be a Thai phone number, e.g. 0812345678"
        )
    return digits


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
        if run_date > club_today(now):
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
