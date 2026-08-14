from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.audit_repository import AuditRepository
from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.clock import Clock
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.run_repository import RunRepository


class RunReviewUnitOfWork(Protocol):
    """One transaction for an admin's decision about a run.

    The decision, the points it changes, and the audit row all commit together. Any two
    of them apart would be worse than none: a rejected run whose points survived is a
    member spending points they no longer have, and a points change with no audit row is
    an unexplained balance.
    """

    @property
    def members(self) -> MemberRepository: ...

    @property
    def runs(self) -> RunRepository: ...

    @property
    def campaigns(self) -> CampaignRepository: ...

    @property
    def ledger(self) -> PointsLedgerRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> RunReviewUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
