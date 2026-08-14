"""The audit guarantee, against a real database.

The fake proves the use case's logic. This proves the transaction actually behaves that
way in PostgreSQL: the audit row is durable before the data is returned, and a failed
audit write takes the whole access down with it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from app.adapters.persistence.health_unit_of_work import SqlAlchemyHealthUnitOfWork
from app.application.use_cases.save_health_record import (
    SaveHealthRecord,
    SaveHealthRecordCommand,
)
from app.application.use_cases.view_member_health import (
    ViewMemberHealth,
    ViewMemberHealthCommand,
)
from app.domain.audit import AuditEntry
from app.domain.consent import ConsentPurpose
from app.domain.errors import ConsentRequired, NotAuthorized
from app.domain.health import HealthPhase
from tests.fakes.fake_uow import FixedClock

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 15, 9, 0, tzinfo=UTC)
VERSION = "v2"
CAMPAIGN = UUID("11111111-1111-1111-1111-111111111111")


class ExplodingAuditRepository:
    """Stands in for an audit write that fails at the database."""

    def record(self, entry: AuditEntry) -> None:
        raise RuntimeError("audit backend is down")


class BrokenAuditUnitOfWork(SqlAlchemyHealthUnitOfWork):
    @property
    def audit(self) -> ExplodingAuditRepository:  # type: ignore[override]
        return ExplodingAuditRepository()


def seed(
    session_factory: sessionmaker[Session],
    *,
    consent_version: str | None = VERSION,
    withdrawn: bool = False,
    admin_role: str = "admin",
) -> tuple[UUID, UUID]:
    alice, admin = uuid4(), uuid4()
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="100km", name="100 km", type="cumulative_distance",
                starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
                config={"target_km": 100},
            )
        )
        session.add(models.Member(id=alice, clerk_user_id="clerk_alice", display_name="Alice"))
        session.add(
            models.Member(
                id=admin, clerk_user_id="clerk_admin", display_name="Admin", role=admin_role
            )
        )
        session.flush()  # members must exist before rows that reference them

        if consent_version is not None:
            session.add(
                models.Consent(
                    id=uuid4(), member_id=alice, purpose="health_data",
                    version=consent_version, granted_at=NOW,
                    withdrawn_at=NOW if withdrawn else None,
                )
            )
        session.flush()
        session.add(
            models.HealthRecord(
                id=uuid4(), member_id=alice, campaign_id=CAMPAIGN, phase="before",
                measured_on=date(2026, 6, 1), weight_kg=Decimal("70.5"),
                height_cm=Decimal("172.5"), retention_until=datetime(2028, 12, 30, tzinfo=UTC),
            )
        )
        session.commit()
    return alice, admin


def audit_rows(session_factory: sessionmaker[Session]) -> list[models.AuditLog]:
    with session_factory() as session:
        return list(session.execute(sa.select(models.AuditLog)).scalars())


def test_a_successful_admin_view_leaves_a_committed_audit_row(
    session_factory: sessionmaker[Session],
) -> None:
    alice, admin = seed(session_factory)
    use_case = ViewMemberHealth(
        SqlAlchemyHealthUnitOfWork(session_factory, FixedClock(NOW)), VERSION
    )

    view = use_case.execute(ViewMemberHealthCommand(actor_id=admin, subject_id=alice))

    assert view.health[0].bmi_before == Decimal("23.7")
    rows = audit_rows(session_factory)
    assert len(rows) == 1
    assert rows[0].action == "view_health"
    assert rows[0].actor_member_id == admin
    assert rows[0].subject_member_id == alice
    assert rows[0].detail == {"campaign_count": 1}


def test_a_failed_audit_write_returns_nothing_and_leaves_no_row(
    session_factory: sessionmaker[Session],
) -> None:
    alice, admin = seed(session_factory)
    use_case = ViewMemberHealth(BrokenAuditUnitOfWork(session_factory, FixedClock(NOW)), VERSION)

    with pytest.raises(RuntimeError):
        use_case.execute(ViewMemberHealthCommand(actor_id=admin, subject_id=alice))

    assert audit_rows(session_factory) == []


def test_withdrawn_consent_blocks_the_admin_and_writes_no_audit_row(
    session_factory: sessionmaker[Session],
) -> None:
    alice, admin = seed(session_factory, withdrawn=True)
    use_case = ViewMemberHealth(
        SqlAlchemyHealthUnitOfWork(session_factory, FixedClock(NOW)), VERSION
    )

    with pytest.raises(ConsentRequired):
        use_case.execute(ViewMemberHealthCommand(actor_id=admin, subject_id=alice))

    assert audit_rows(session_factory) == []


def test_superseded_consent_wording_blocks_the_admin(
    session_factory: sessionmaker[Session],
) -> None:
    alice, admin = seed(session_factory, consent_version="v1")
    use_case = ViewMemberHealth(
        SqlAlchemyHealthUnitOfWork(session_factory, FixedClock(NOW)), VERSION
    )

    with pytest.raises(ConsentRequired):
        use_case.execute(ViewMemberHealthCommand(actor_id=admin, subject_id=alice))


def test_an_ordinary_member_is_refused(session_factory: sessionmaker[Session]) -> None:
    alice, _ = seed(session_factory)
    use_case = ViewMemberHealth(
        SqlAlchemyHealthUnitOfWork(session_factory, FixedClock(NOW)), VERSION
    )

    with pytest.raises(NotAuthorized):
        use_case.execute(ViewMemberHealthCommand(actor_id=alice, subject_id=alice))

    assert audit_rows(session_factory) == []


def test_the_consent_gate_holds_against_the_real_unique_index(
    session_factory: sessionmaker[Session],
) -> None:
    """Writing health data without consent is refused before any row is attempted."""
    from app.adapters.persistence.sqlalchemy_campaign_repository import (
        SqlAlchemyCampaignRepository,
    )
    from app.adapters.persistence.sqlalchemy_consent_repository import (
        SqlAlchemyConsentRepository,
    )
    from app.adapters.persistence.sqlalchemy_health_repository import (
        SqlAlchemyHealthRepository,
    )

    alice, _ = seed(session_factory, consent_version=None)
    with session_factory() as session:
        use_case = SaveHealthRecord(
            consents=SqlAlchemyConsentRepository(session),
            campaigns=SqlAlchemyCampaignRepository(session),
            health=SqlAlchemyHealthRepository(session),
            clock=FixedClock(NOW),
            consent_version=VERSION,
            retention_days=730,
        )

        with pytest.raises(ConsentRequired):
            use_case.execute(
                SaveHealthRecordCommand(
                    member_id=alice, campaign_id=CAMPAIGN, phase=HealthPhase.AFTER,
                    measured_on=date(2026, 6, 10), weight_kg=Decimal("69.0"),
                )
            )
        session.rollback()

    with session_factory() as session:
        count = session.execute(
            sa.select(sa.func.count()).select_from(models.HealthRecord)
        ).scalar_one()
    assert count == 1  # only the seeded 'before' record


def test_consent_repository_reads_only_the_active_row(
    session_factory: sessionmaker[Session],
) -> None:
    from app.adapters.persistence.sqlalchemy_consent_repository import (
        SqlAlchemyConsentRepository,
    )

    alice, _ = seed(session_factory, consent_version="v1")
    with session_factory() as session:
        repo = SqlAlchemyConsentRepository(session)
        current = repo.get_current(alice, ConsentPurpose.HEALTH_DATA)
        assert current is not None

        repo.save(current.withdraw(NOW))
        session.commit()

        assert repo.get_current(alice, ConsentPurpose.HEALTH_DATA) is None
