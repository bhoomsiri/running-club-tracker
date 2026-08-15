from typing import Protocol
from uuid import UUID

from app.domain.screening import Screening


class ScreeningRepository(Protocol):
    def get_for_member(self, member_id: UUID) -> Screening | None:
        """Sensitive data: the caller must already have established that it is entitled
        to this member's screening (the owner, or an audited admin read)."""
        ...

    def upsert(self, screening: Screening) -> Screening:
        """Insert, or replace the member's single record. Returns what is now stored."""
        ...
