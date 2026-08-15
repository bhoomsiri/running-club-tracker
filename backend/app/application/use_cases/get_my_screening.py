"""A member reading back their own screening, or finding they have none yet.

No consent check: this returns only what the member themselves put in, to the member
themselves. Withdrawing consent stops the club processing the answers, but it does not
take away the owner's own view of them — the same line drawn for health records.
"""

from __future__ import annotations

from uuid import UUID

from app.application.ports.screening_repository import ScreeningRepository
from app.domain.screening import Screening


class GetMyScreening:
    def __init__(self, screenings: ScreeningRepository) -> None:
        self._screenings = screenings

    def execute(self, member_id: UUID) -> Screening | None:
        return self._screenings.get_for_member(member_id)
