from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.clock import Clock
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.run_repository import RunRepository


class RunSubmissionUnitOfWork(Protocol):
    """One transaction covering a run and the points it earns.

    They belong together: a run that is stored without its ledger rows leaves a member
    permanently short of points, and ledger rows without their run are unexplainable.
    Committing them separately would eventually produce both.
    """

    @property
    def runs(self) -> RunRepository: ...

    @property
    def campaigns(self) -> CampaignRepository: ...

    @property
    def ledger(self) -> PointsLedgerRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> RunSubmissionUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
