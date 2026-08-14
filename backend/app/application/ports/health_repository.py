from typing import Protocol
from uuid import UUID

from app.domain.health import HealthRecord


class HealthRepository(Protocol):
    def list_by_member(self, member_id: UUID) -> list[HealthRecord]:
        """Sensitive data: every caller must already have established that it is
        entitled to this member's records (owner, or an audited admin read)."""
        ...

    def upsert(self, record: HealthRecord) -> HealthRecord:
        """Insert, or replace the member's existing record for the same campaign and
        phase. Returns what is now stored — keeping the original row's id when one
        already existed, so the record's history stays one row."""
        ...
