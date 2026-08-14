from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class RunDraft:
    """A *suggestion* read off a screenshot. Never a fact.

    Any field the model could not read confidently is None with a warning beside it —
    it never guesses a number (golden rules #3 and #4). The member confirms or corrects
    every value before anything is saved, and the confirmed values are what get stored.
    """

    distance_km: Decimal | None = None
    duration_seconds: int | None = None
    run_date: date | None = None
    confidence: Decimal = Decimal("0")
    warnings: list[str] = field(default_factory=list)


class RunExtractor(Protocol):
    def extract(self, image: bytes, kind: str) -> RunDraft: ...
