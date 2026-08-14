"""Health data — sensitive personal data under PDPA (มาตรา 26).

Two rules shape this module:
  - BMI is never stored. It is derived from weight + height at read time, so it can
    never drift out of agreement with the values it came from.
  - An unknown measurement is None. Nothing here invents a number to fill a gap
    (golden rule #4) — a missing weight or height yields a BMI of None, not a guess.

Writing a record is gated by consent; that gate lives in the use case, not here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from app.domain.errors import InvalidHealthRecordError

BMI_PRECISION = Decimal("0.1")

# Plausible ranges — the same bounds as the DB CHECK constraints.
_RANGES: dict[str, tuple[Decimal, Decimal]] = {
    "weight_kg": (Decimal("0.01"), Decimal("399.99")),
    "height_cm": (Decimal("80"), Decimal("250")),
    "resting_hr": (Decimal("20"), Decimal("250")),
    "systolic": (Decimal("50"), Decimal("300")),
    "diastolic": (Decimal("30"), Decimal("200")),
}


class HealthPhase(StrEnum):
    BEFORE = "before"
    AFTER = "after"


def bmi(weight_kg: Decimal | None, height_cm: Decimal | None) -> Decimal | None:
    """kg / m^2, to one decimal place. None whenever either input is unknown."""
    if weight_kg is None or height_cm is None or height_cm <= 0:
        return None
    metres = height_cm / Decimal("100")
    return (weight_kg / (metres * metres)).quantize(BMI_PRECISION, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class HealthRecord:
    id: UUID
    member_id: UUID
    campaign_id: UUID
    phase: HealthPhase
    measured_on: date
    weight_kg: Decimal | None
    height_cm: Decimal | None
    resting_hr: int | None
    systolic: int | None
    diastolic: int | None
    retention_until: datetime
    created_at: datetime

    @classmethod
    def create(
        cls,
        *,
        member_id: UUID,
        campaign_id: UUID,
        phase: HealthPhase,
        measured_on: date,
        campaign_ends_on: date,
        retention_days: int,
        now: datetime,
        weight_kg: Decimal | None = None,
        height_cm: Decimal | None = None,
        resting_hr: int | None = None,
        systolic: int | None = None,
        diastolic: int | None = None,
    ) -> HealthRecord:
        _check("weight_kg", weight_kg)
        _check("height_cm", height_cm)
        _check("resting_hr", resting_hr)
        _check("systolic", systolic)
        _check("diastolic", diastolic)
        if measured_on > now.date():
            raise InvalidHealthRecordError("measured_on cannot be in the future")

        return cls(
            id=uuid4(),
            member_id=member_id,
            campaign_id=campaign_id,
            phase=phase,
            measured_on=measured_on,
            weight_kg=weight_kg,
            height_cm=height_cm,
            resting_hr=resting_hr,
            systolic=systolic,
            diastolic=diastolic,
            # The retention promise, frozen onto the record at write time.
            retention_until=datetime.combine(
                campaign_ends_on + timedelta(days=retention_days), time(0, 0), tzinfo=UTC
            ),
            created_at=now,
        )

    def bmi(self, *, fallback_height_cm: Decimal | None = None) -> Decimal | None:
        return bmi(self.weight_kg, self.height_cm or fallback_height_cm)


def _check(field: str, value: Decimal | int | None) -> None:
    if value is None:
        return
    low, high = _RANGES[field]
    if not (low <= Decimal(value) <= high):
        raise InvalidHealthRecordError(f"{field} must be between {low} and {high}")


@dataclass(frozen=True)
class HealthComparison:
    """A member's before/after for one campaign, with BMI derived for each side."""

    campaign_id: UUID
    before: HealthRecord | None
    after: HealthRecord | None
    bmi_before: Decimal | None
    bmi_after: Decimal | None
    bmi_delta: Decimal | None

    @classmethod
    def build(cls, campaign_id: UUID, records: Sequence[HealthRecord]) -> HealthComparison:
        mine = [r for r in records if r.campaign_id == campaign_id]
        before = next((r for r in mine if r.phase is HealthPhase.BEFORE), None)
        after = next((r for r in mine if r.phase is HealthPhase.AFTER), None)

        # Height is usually captured once, in the 'before' record. The 'after' form
        # doesn't ask for it again, so fall back to the height from the same campaign.
        baseline_height = before.height_cm if before else None
        bmi_before = before.bmi() if before else None
        bmi_after = after.bmi(fallback_height_cm=baseline_height) if after else None

        return cls(
            campaign_id=campaign_id,
            before=before,
            after=after,
            bmi_before=bmi_before,
            bmi_after=bmi_after,
            bmi_delta=(
                (bmi_after - bmi_before)
                if bmi_before is not None and bmi_after is not None
                else None
            ),
        )
