"""The transaction behind submitting a run: the run and its points, together."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.sqlalchemy_campaign_repository import (
    SqlAlchemyCampaignRepository,
)
from app.adapters.persistence.sqlalchemy_points_ledger_repository import (
    SqlAlchemyPointsLedgerRepository,
)
from app.adapters.persistence.sqlalchemy_run_repository import SqlAlchemyRunRepository
from app.application.ports.clock import Clock


class SqlAlchemyRunSubmissionUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> SqlAlchemyRunSubmissionUnitOfWork:
        self._session = self._session_factory()
        self._committed = False
        session = self._session
        self._runs = SqlAlchemyRunRepository(session)
        self._campaigns = SqlAlchemyCampaignRepository(session)
        self._ledger = SqlAlchemyPointsLedgerRepository(session)
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
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    @property
    def runs(self) -> SqlAlchemyRunRepository:
        self._require_active()
        return self._runs

    @property
    def campaigns(self) -> SqlAlchemyCampaignRepository:
        self._require_active()
        return self._campaigns

    @property
    def ledger(self) -> SqlAlchemyPointsLedgerRepository:
        self._require_active()
        return self._ledger

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
