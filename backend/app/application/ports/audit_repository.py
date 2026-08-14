from typing import Protocol

from app.domain.audit import AuditEntry


class AuditRepository(Protocol):
    def record(self, entry: AuditEntry) -> None:
        """Write the access record. Callers must commit this BEFORE returning the data
        it describes — an access that isn't logged must not happen at all."""
        ...
