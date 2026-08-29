"""The two audited-read units of work, faked.

Writes are staged until commit, exactly like the health fake, so a test can prove the two
things that matter: that a failed audit write leaves no trace, and that data is only
handed back once the audit row is committed.

Two fakes rather than one, mirroring the ports. The screening read carries consent
because a screening is health data; the contact read does not, because the emergency
contact rests on the club's safety interest instead — and a fake that carried a consent
repository the contact use case must never consult would quietly make that testable the
wrong way round.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType

from tests.fakes.fake_health_uow import FakeConsentRepository
from tests.fakes.fake_uow import FakeAuditRepository, FixedClock
from tests.fakes.repositories import FakeMemberRepository, FakeScreeningRepository

DEFAULT_NOW = datetime(2026, 8, 20, 9, 0, tzinfo=UTC)


class FakeContactViewUnitOfWork:
    def __init__(
        self,
        members: FakeMemberRepository | None = None,
        clock: FixedClock | None = None,
        audit: FakeAuditRepository | None = None,
    ) -> None:
        self._members = members or FakeMemberRepository()
        self._audit = audit or FakeAuditRepository()
        self._clock = clock or FixedClock(DEFAULT_NOW)
        self.committed = False
        self.fail_on_commit = False

    def __enter__(self) -> FakeContactViewUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if not self.committed:
            self._audit.rollback()

    @property
    def members(self) -> FakeMemberRepository:
        return self._members

    @property
    def audit(self) -> FakeAuditRepository:
        return self._audit

    @property
    def clock(self) -> FixedClock:
        return self._clock

    def commit(self) -> None:
        if self.fail_on_commit:
            raise RuntimeError("audit write failed")
        self._audit.commit()
        self.committed = True

    def rollback(self) -> None:
        self._audit.rollback()


class FakeScreeningViewUnitOfWork(FakeContactViewUnitOfWork):
    def __init__(
        self,
        members: FakeMemberRepository | None = None,
        screenings: FakeScreeningRepository | None = None,
        clock: FixedClock | None = None,
        audit: FakeAuditRepository | None = None,
        consents: FakeConsentRepository | None = None,
    ) -> None:
        super().__init__(members=members, clock=clock, audit=audit)
        self._screenings = screenings or FakeScreeningRepository()
        self._consents = consents or FakeConsentRepository()

    def __enter__(self) -> FakeScreeningViewUnitOfWork:
        return self

    @property
    def screenings(self) -> FakeScreeningRepository:
        return self._screenings

    @property
    def consents(self) -> FakeConsentRepository:
        return self._consents
