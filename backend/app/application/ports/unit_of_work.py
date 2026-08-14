from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.clock import Clock
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.reward_repository import RewardRepository


class UnitOfWork(Protocol):
    """One transaction, several repositories.

    Entering begins a transaction; leaving without an explicit `commit()` must roll
    back. This is what makes the redemption sequence (lock -> check balance -> insert
    redemption + negative ledger row -> decrement stock) atomic.
    """

    # Read-only properties, not plain attributes: a mutable attribute in a Protocol is
    # invariant, which would mean no implementation could expose a concrete repository
    # type — not even the in-memory fakes. Concrete classes may still satisfy these
    # with ordinary instance attributes.
    @property
    def rewards(self) -> RewardRepository: ...

    @property
    def ledger(self) -> PointsLedgerRepository: ...

    @property
    def redemptions(self) -> RedemptionRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
