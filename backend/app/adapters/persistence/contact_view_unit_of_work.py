"""The transaction behind an audited read of a member's contact details.

Carries no consent repository, deliberately — see
`application/ports/contact_view_unit_of_work.py`: the emergency contact rests on the
club's safety interest rather than on consent for health data.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.sqlalchemy_audit_repository import SqlAlchemyAuditRepository
from app.adapters.persistence.sqlalchemy_member_repository import SqlAlchemyMemberRepository
from app.application.ports.clock import Clock


class SqlAlchemyContactViewUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> SqlAlchemyContactViewUnitOfWork:
        self._session = self._session_factory()
        self._committed = False
        session = self._session
        self._members = SqlAlchemyMemberRepository(session)
        self._audit = SqlAlchemyAuditRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        try:
            if not self._committed:
                # The case that matters: the audit write failed, so the read that
                # depended on it is discarded with it.
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    @property
    def members(self) -> SqlAlchemyMemberRepository:
        self._require_active()
        return self._members

    @property
    def audit(self) -> SqlAlchemyAuditRepository:
        self._require_active()
        return self._audit

    @property
    def clock(self) -> Clock:
        return self._clock

    def commit(self) -> None:
        self._require_active()
        assert self._session is not None
        self._session.commit()
        self._committed = True

    def rollback(self) -> None:
        self._require_active()
        assert self._session is not None
        self._session.rollback()

    def _require_active(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork used outside a `with` block")
