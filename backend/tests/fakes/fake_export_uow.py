"""The export unit of work, faked.

Audit rows are staged until commit, like the other fakes, so a test can prove the thing
the export turns on: that a failure anywhere leaves no audit row claiming a file was
made, and that no file is returned unless the rows that account for it committed.
"""

from __future__ import annotations

from types import TracebackType

from tests.fakes.fake_health_uow import FakeConsentRepository
from tests.fakes.fake_uow import (
    FakeAuditRepository,
    FakePointsLedgerRepository,
    FakeRedemptionRepository,
    FakeRewardRepository,
    FixedClock,
)
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeHealthRepository,
    FakeMemberRepository,
    FakeRunRepository,
    FakeScreeningRepository,
)


class FakeExportUnitOfWork:
    def __init__(
        self,
        *,
        members: FakeMemberRepository | None = None,
        campaigns: FakeCampaignRepository | None = None,
        rewards: FakeRewardRepository | None = None,
        redemptions: FakeRedemptionRepository | None = None,
        ledger: FakePointsLedgerRepository | None = None,
        runs: FakeRunRepository | None = None,
        screenings: FakeScreeningRepository | None = None,
        health: FakeHealthRepository | None = None,
        consents: FakeConsentRepository | None = None,
        audit: FakeAuditRepository | None = None,
        clock: FixedClock,
    ) -> None:
        self.members = members or FakeMemberRepository()
        self.campaigns = campaigns or FakeCampaignRepository([])
        self.rewards = rewards or FakeRewardRepository()
        self.redemptions = redemptions or FakeRedemptionRepository()
        self.ledger = ledger or FakePointsLedgerRepository()
        self.runs = runs or FakeRunRepository()
        self.screenings = screenings or FakeScreeningRepository()
        self.health = health or FakeHealthRepository()
        self.consents = consents or FakeConsentRepository()
        self.audit = audit or FakeAuditRepository()
        self.clock = clock
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeExportUnitOfWork:
        self.committed = False
        self.rolled_back = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self.rollback()

    def commit(self) -> None:
        self.audit.commit()
        self.committed = True

    def rollback(self) -> None:
        self.audit.rollback()
        self.rolled_back = True
