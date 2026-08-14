from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.audit_repository import AuditRepository
from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.clock import Clock
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.reward_repository import RewardRepository
from app.application.ports.run_repository import RunRepository


class AdminUnitOfWork(Protocol):
    """One transaction for a superuser's change to the club's settings or records.

    Wider than the other units of work because these operations genuinely span that
    much: cancelling a redemption moves the redemption, the ledger and the reward's
    stock at once, and every one of them must land with its audit row or not at all.
    """

    @property
    def members(self) -> MemberRepository: ...

    @property
    def campaigns(self) -> CampaignRepository: ...

    @property
    def rewards(self) -> RewardRepository: ...

    @property
    def redemptions(self) -> RedemptionRepository: ...

    @property
    def ledger(self) -> PointsLedgerRepository: ...

    @property
    def runs(self) -> RunRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> AdminUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
