"""The real UnitOfWork: one SQLAlchemy session, one database transaction.

Entering opens a session; every repository handed out shares it, so everything a use
case does lands in the same transaction. Leaving without an explicit `commit()` rolls
back — including when an exception is on its way out, which is what stops a redemption
from being half-written.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.sqlalchemy_points_ledger_repository import (
    SqlAlchemyPointsLedgerRepository,
)
from app.adapters.persistence.sqlalchemy_redemption_repository import (
    SqlAlchemyRedemptionRepository,
)
from app.adapters.persistence.sqlalchemy_reward_repository import SqlAlchemyRewardRepository
from app.application.ports.clock import Clock


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> SqlAlchemyUnitOfWork:
        self._session = self._session_factory()
        self._committed = False
        session = self._session
        self._rewards = SqlAlchemyRewardRepository(session)
        self._ledger = SqlAlchemyPointsLedgerRepository(session)
        self._redemptions = SqlAlchemyRedemptionRepository(session)
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
    def rewards(self) -> SqlAlchemyRewardRepository:
        self._require_active()
        return self._rewards

    @property
    def ledger(self) -> SqlAlchemyPointsLedgerRepository:
        self._require_active()
        return self._ledger

    @property
    def redemptions(self) -> SqlAlchemyRedemptionRepository:
        self._require_active()
        return self._redemptions

    @property
    def clock(self) -> Clock:
        return self._clock

    def commit(self) -> None:
        self._require_active()
        assert self._session is not None
        self._session.commit()
        # Any advisory lock taken during the transaction is released by this commit.
        self._committed = True

    def rollback(self) -> None:
        self._require_active()
        assert self._session is not None
        self._session.rollback()

    def _require_active(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork used outside a `with` block")
