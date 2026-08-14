"""The transaction behind a superuser's changes: the mutation and its audit row."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence.sqlalchemy_audit_repository import SqlAlchemyAuditRepository
from app.adapters.persistence.sqlalchemy_campaign_repository import (
    SqlAlchemyCampaignRepository,
)
from app.adapters.persistence.sqlalchemy_member_repository import SqlAlchemyMemberRepository
from app.adapters.persistence.sqlalchemy_points_ledger_repository import (
    SqlAlchemyPointsLedgerRepository,
)
from app.adapters.persistence.sqlalchemy_redemption_repository import (
    SqlAlchemyRedemptionRepository,
)
from app.adapters.persistence.sqlalchemy_reward_repository import SqlAlchemyRewardRepository
from app.adapters.persistence.sqlalchemy_run_repository import SqlAlchemyRunRepository
from app.application.ports.clock import Clock


class SqlAlchemyAdminUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> SqlAlchemyAdminUnitOfWork:
        self._session = self._session_factory()
        self._committed = False
        session = self._session
        self._runs = SqlAlchemyRunRepository(session)
        self._campaigns = SqlAlchemyCampaignRepository(session)
        self._ledger = SqlAlchemyPointsLedgerRepository(session)
        self._members = SqlAlchemyMemberRepository(session)
        self._audit = SqlAlchemyAuditRepository(session)
        self._rewards = SqlAlchemyRewardRepository(session)
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
    def members(self) -> SqlAlchemyMemberRepository:
        self._require_active()
        return self._members

    @property
    def audit(self) -> SqlAlchemyAuditRepository:
        self._require_active()
        return self._audit

    @property
    def rewards(self) -> SqlAlchemyRewardRepository:
        self._require_active()
        return self._rewards

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
        self._committed = True

    def rollback(self) -> None:
        self._require_active()
        assert self._session is not None
        self._session.rollback()

    def _require_active(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork used outside a `with` block")
