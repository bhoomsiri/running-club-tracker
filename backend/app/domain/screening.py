"""PAR-Q+ style pre-exercise screening — sensitive personal data under PDPA (มาตรา 26).

The questions are answered once per member and revised as needed; one record per member,
not one per campaign, because what they describe is the member's health, not their
participation in a particular activity.

Two rules shape this module:
  - A "yes" is a reason to advise, never a reason to block. The club is not a doctor's
    surgery and this form is not a diagnosis: it tells a member that a professional
    should look at them before they train hard. Refusing them entry on the strength of
    eleven checkboxes would be both wrong and unenforceable.
  - Answers are never logged and never summarised into anything that leaves the domain
    except the count of "yes" answers, which is what an audit row is allowed to record.

The question wording shown to members lives in the frontend; what is stored here are the
keys, so the two can be translated or reworded without a migration. `version` records
which instrument the member answered, so a future revision does not silently change what
their answers meant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.calendar import club_today
from app.domain.errors import InvalidScreeningError

PARQ_VERSION = "parq-plus-th-v1"


class ScreeningGroup(StrEnum):
    CARDIOVASCULAR = "cardiovascular"
    CONDITIONS = "conditions"
    HISTORY = "history"


# The eleven questions, in the order they are asked. Kept here rather than in the API
# layer so the domain can say what a complete answer set is.
QUESTIONS: tuple[tuple[str, ScreeningGroup], ...] = (
    ("heart_condition", ScreeningGroup.CARDIOVASCULAR),
    ("chest_pain_activity", ScreeningGroup.CARDIOVASCULAR),
    ("chest_pain_at_rest", ScreeningGroup.CARDIOVASCULAR),
    ("dizziness_or_fainting", ScreeningGroup.CARDIOVASCULAR),
    ("high_blood_pressure", ScreeningGroup.CONDITIONS),
    ("diabetes", ScreeningGroup.CONDITIONS),
    ("asthma_or_lung_disease", ScreeningGroup.CONDITIONS),
    ("bone_or_joint_problem", ScreeningGroup.CONDITIONS),
    ("family_heart_disease", ScreeningGroup.HISTORY),
    ("prescribed_medication", ScreeningGroup.HISTORY),
    ("other_reason_not_to_exercise", ScreeningGroup.HISTORY),
)

QUESTION_KEYS: frozenset[str] = frozenset(key for key, _ in QUESTIONS)


@dataclass(frozen=True)
class Screening:
    id: UUID
    member_id: UUID
    version: str
    answers: dict[str, bool]
    risk_acknowledged: bool
    screened_on: date
    created_at: datetime
    updated_at: datetime

    @property
    def yes_count(self) -> int:
        return sum(1 for answer in self.answers.values() if answer)

    @property
    def needs_medical_advice(self) -> bool:
        """One "yes" is enough. The point of the instrument is to catch the single
        condition that matters, not to score a total."""
        return self.yes_count > 0

    @classmethod
    def create(
        cls,
        *,
        member_id: UUID,
        answers: dict[str, bool],
        risk_acknowledged: bool,
        screened_on: date,
        now: datetime,
        existing: Screening | None = None,
        version: str = PARQ_VERSION,
    ) -> Screening:
        """Build the member's screening, or a revision of it.

        `existing` keeps the id and created_at when a member answers again, so the
        record stays one row with a history of one — the club needs to know what is
        true now, and the answers are sensitive enough that keeping every draft is a
        liability rather than an asset.
        """
        validated = _validate_answers(answers)
        if screened_on > club_today(now):
            raise InvalidScreeningError("screened_on cannot be in the future")

        return cls(
            id=existing.id if existing else uuid4(),
            member_id=member_id,
            version=version,
            answers=validated,
            risk_acknowledged=risk_acknowledged,
            screened_on=screened_on,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )


def _validate_answers(answers: dict[str, bool]) -> dict[str, bool]:
    """Every question answered, nothing invented, nothing extra.

    A missing answer is not treated as "no": an unanswered cardiac question read as a
    clean result is exactly the failure this screening exists to prevent (golden
    rule #4 — an unknown is never filled in with a value).
    """
    missing = sorted(QUESTION_KEYS - answers.keys())
    if missing:
        raise InvalidScreeningError(f"unanswered questions: {', '.join(missing)}")

    unknown = sorted(answers.keys() - QUESTION_KEYS)
    if unknown:
        raise InvalidScreeningError(f"unknown questions: {', '.join(unknown)}")

    for key, value in answers.items():
        if not isinstance(value, bool):
            raise InvalidScreeningError(f"answer to {key} must be true or false")

    # Rebuilt in question order, so a stored record reads the same way every time.
    return {key: answers[key] for key, _ in QUESTIONS}
