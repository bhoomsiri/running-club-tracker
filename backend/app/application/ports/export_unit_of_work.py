"""One transaction covering the whole export.

The widest unit of work in the app, and the only one where that is the point rather
than a smell: the export's job is to read every table at one instant and account for
having done so. Splitting it would mean the sheets came from different moments and the
audit rows from a different transaction than the data they describe.

Its reason to exist is the same as `HealthUnitOfWork`'s, one size up: the audit entries
must commit together with the read that produced the file, so an export that cannot be
accounted for does not happen.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.audit_repository import AuditRepository
from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.clock import Clock
from app.application.ports.consent_repository import ConsentRepository
from app.application.ports.health_repository import HealthRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.reward_repository import RewardRepository
from app.application.ports.run_repository import RunRepository
from app.application.ports.screening_repository import ScreeningRepository


class ExportUnitOfWork(Protocol):
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
    def screenings(self) -> ScreeningRepository: ...

    @property
    def health(self) -> HealthRepository: ...

    @property
    def consents(self) -> ConsentRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> ExportUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
