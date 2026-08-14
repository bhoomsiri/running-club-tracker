from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.persistence.mappers import audit_to_orm
from app.domain.audit import AuditEntry


class SqlAlchemyAuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, entry: AuditEntry) -> None:
        self._session.add(audit_to_orm(entry))
        # Flush here so a failure to log surfaces before the caller decides to return
        # the data. The commit is the caller's, and must happen before that return.
        self._session.flush()
