"""Both implementations of every port must be substitutable for it (LSP).

These functions have no assertions to run — mypy is the test. Each one returns a
concrete implementation where the Protocol is expected, so a drift between the fake and
the real SQLAlchemy adapter fails the type check instead of surfacing later as a use
case that works in tests and breaks in production.

This is why the gate runs `mypy app tests` rather than `mypy app`.
"""

from __future__ import annotations

from app.adapters.persistence.health_unit_of_work import SqlAlchemyHealthUnitOfWork
from app.adapters.persistence.sqlalchemy_audit_repository import SqlAlchemyAuditRepository
from app.adapters.persistence.sqlalchemy_campaign_repository import (
    SqlAlchemyCampaignRepository,
)
from app.adapters.persistence.sqlalchemy_consent_repository import (
    SqlAlchemyConsentRepository,
)
from app.adapters.persistence.sqlalchemy_health_repository import SqlAlchemyHealthRepository
from app.adapters.persistence.sqlalchemy_member_repository import SqlAlchemyMemberRepository
from app.adapters.persistence.sqlalchemy_points_ledger_repository import (
    SqlAlchemyPointsLedgerRepository,
)
from app.adapters.persistence.sqlalchemy_redemption_repository import (
    SqlAlchemyRedemptionRepository,
)
from app.adapters.persistence.sqlalchemy_reward_repository import SqlAlchemyRewardRepository
from app.adapters.persistence.sqlalchemy_run_repository import SqlAlchemyRunRepository
from app.adapters.persistence.unit_of_work import SqlAlchemyUnitOfWork
from app.application.ports.audit_repository import AuditRepository
from app.application.ports.campaign_repository import CampaignRepository
from app.application.ports.consent_repository import ConsentRepository
from app.application.ports.health_repository import HealthRepository
from app.application.ports.health_unit_of_work import HealthUnitOfWork
from app.application.ports.member_repository import MemberRepository
from app.application.ports.points_ledger_repository import PointsLedgerRepository
from app.application.ports.redemption_repository import RedemptionRepository
from app.application.ports.reward_repository import RewardRepository
from app.application.ports.run_repository import RunRepository
from app.application.ports.unit_of_work import UnitOfWork
from tests.fakes.fake_health_uow import (
    FakeAuditRepository,
    FakeConsentRepository,
    FakeHealthUnitOfWork,
)
from tests.fakes.fake_uow import (
    FakePointsLedgerRepository,
    FakeRedemptionRepository,
    FakeRewardRepository,
    FakeUnitOfWork,
)
from tests.fakes.repositories import (
    FakeCampaignRepository,
    FakeHealthRepository,
    FakeMemberRepository,
    FakeRunRepository,
)


def _real_uow(uow: SqlAlchemyUnitOfWork) -> UnitOfWork:
    return uow


def _fake_uow(uow: FakeUnitOfWork) -> UnitOfWork:
    return uow


def _real_health_uow(uow: SqlAlchemyHealthUnitOfWork) -> HealthUnitOfWork:
    return uow


def _fake_health_uow(uow: FakeHealthUnitOfWork) -> HealthUnitOfWork:
    return uow


def _real_consents(repo: SqlAlchemyConsentRepository) -> ConsentRepository:
    return repo


def _fake_consents(repo: FakeConsentRepository) -> ConsentRepository:
    return repo


def _real_audit(repo: SqlAlchemyAuditRepository) -> AuditRepository:
    return repo


def _fake_audit(repo: FakeAuditRepository) -> AuditRepository:
    return repo


def _real_rewards(repo: SqlAlchemyRewardRepository) -> RewardRepository:
    return repo


def _fake_rewards(repo: FakeRewardRepository) -> RewardRepository:
    return repo


def _real_ledger(repo: SqlAlchemyPointsLedgerRepository) -> PointsLedgerRepository:
    return repo


def _fake_ledger(repo: FakePointsLedgerRepository) -> PointsLedgerRepository:
    return repo


def _real_redemptions(repo: SqlAlchemyRedemptionRepository) -> RedemptionRepository:
    return repo


def _fake_redemptions(repo: FakeRedemptionRepository) -> RedemptionRepository:
    return repo


def _real_runs(repo: SqlAlchemyRunRepository) -> RunRepository:
    return repo


def _fake_runs(repo: FakeRunRepository) -> RunRepository:
    return repo


def _real_campaigns(repo: SqlAlchemyCampaignRepository) -> CampaignRepository:
    return repo


def _fake_campaigns(repo: FakeCampaignRepository) -> CampaignRepository:
    return repo


def _real_members(repo: SqlAlchemyMemberRepository) -> MemberRepository:
    return repo


def _fake_members(repo: FakeMemberRepository) -> MemberRepository:
    return repo


def _real_health(repo: SqlAlchemyHealthRepository) -> HealthRepository:
    return repo


def _fake_health(repo: FakeHealthRepository) -> HealthRepository:
    return repo


def test_every_port_has_a_fake_and_a_real_implementation() -> None:
    """The conformance itself is checked by mypy; this keeps pytest honest about the
    file being imported."""
    assert _fake_members(FakeMemberRepository()) is not None
