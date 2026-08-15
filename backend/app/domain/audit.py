"""The accountability trail: who accessed whose sensitive data, and when.

`detail` is for context only — ids, a campaign, a count. Golden rule #8 means it must
never carry the data itself: no weights, no blood pressure, no email, no tokens. That
rule is enforced here rather than trusted, because an audit log is exactly the sort of
place a stray `detail=record.__dict__` ends up, and logs travel and persist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.errors import InvalidAuditEntry

# Values may only be simple scalars. A Decimal or a float is almost always a measurement,
# and a dict or an object is almost always a record being dumped wholesale.
_ALLOWED_VALUE_TYPES = (str, int, bool, type(None))

# Fragments that must never appear ANYWHERE in a key. Matched as substrings of the
# key with separators removed, so `access_token`, `memberEmail` and `weightKg` are all
# caught — an exact-name denylist only ever catches the spelling you thought of.
_FORBIDDEN_FRAGMENTS = (
    "weight", "height", "bmi", "restinghr", "heartrate",
    "systolic", "diastolic", "bloodpressure",
    "email", "token", "password", "secret", "phone",
)


def _normalise(key: str) -> str:
    return "".join(ch for ch in key.lower() if ch.isalnum())


class AuditAction(StrEnum):
    VIEW_HEALTH = "view_health"
    VIEW_SCREENING = "view_screening"
    VIEW_CONTACT = "view_contact"
    EDIT_HEALTH = "edit_health"
    EDIT_MEMBER = "edit_member"
    ADJUST_POINTS = "adjust_points"
    REVERSE_RUN = "reverse_run"
    REVIEW_RUN = "review_run"
    CREATE_CAMPAIGN = "create_campaign"
    UPDATE_CAMPAIGN = "update_campaign"
    CREATE_REWARD = "create_reward"
    UPDATE_REWARD = "update_reward"
    FULFILL_REDEMPTION = "fulfill_redemption"
    CANCEL_REDEMPTION = "cancel_redemption"


@dataclass(frozen=True)
class AuditEntry:
    id: UUID
    actor_member_id: UUID
    action: AuditAction
    subject_member_id: UUID | None
    detail: Mapping[str, str | int | bool | None]
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        actor_member_id: UUID,
        action: AuditAction,
        now: datetime,
        subject_member_id: UUID | None = None,
        detail: Mapping[str, object] | None = None,
    ) -> AuditEntry:
        return cls(
            id=uuid4(),
            actor_member_id=actor_member_id,
            action=action,
            subject_member_id=subject_member_id,
            detail=_safe_detail(detail or {}),
            created_at=now,
        )


def _safe_detail(detail: Mapping[str, object]) -> dict[str, str | int | bool | None]:
    clean: dict[str, str | int | bool | None] = {}
    for key, value in detail.items():
        normalised = _normalise(key)
        for fragment in _FORBIDDEN_FRAGMENTS:
            if fragment in normalised:
                raise InvalidAuditEntry(f"{key!r} is sensitive and must never be logged")
        if isinstance(value, UUID):
            clean[key] = str(value)
            continue
        if not isinstance(value, _ALLOWED_VALUE_TYPES):
            raise InvalidAuditEntry(
                f"audit detail {key!r} must be a simple scalar, got {type(value).__name__}"
            )
        clean[key] = value
    return clean
