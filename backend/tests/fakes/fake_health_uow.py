"""Fakes for the consent / health side.

`FakeAuditRepository` lives in fake_uow.py (the run-review UoW needs it too) and is
re-exported here so the health tests read naturally.

`FakeHealthUnitOfWork` stages writes until commit, exactly like the redemption fake, so
a test can prove that a failed audit write leaves no trace — and that the data is only
handed back once the audit is committed.
"""

from __future__ import annotations

from types import TracebackType
from uuid import UUID

from app.domain.consent import Consent, ConsentPurpose
from app.domain.health import HealthRecord
from tests.fakes.fake_uow import FakeAuditRepository, FixedClock
from tests.fakes.repositories import FakeHealthRepository, FakeMemberRepository


class FakeConsentRepository:
    def __init__(self, consents: list[Consent] | None = None) -> None:
        self._items: list[Consent] = list(consents or [])
        self._staged: list[Consent] = []

    def get_current(self, member_id: UUID, purpose: ConsentPurpose) -> Consent | None:
        return next(
            (
                c
                for c in self._items
                if c.member_id == member_id and c.purpose is purpose and c.withdrawn_at is None
            ),
            None,
        )

    def add(self, consent: Consent) -> None:
        self._staged.append(consent)

    def save(self, consent: Consent) -> None:
        self._staged.append(consent)

    def all_consents(self) -> list[Consent]:
        return list(self._items)

    def commit(self) -> None:
        for consent in self._staged:
            self._items = [c for c in self._items if c.id != consent.id]
            self._items.append(consent)
        self._staged.clear()

    def rollback(self) -> None:
        self._staged.clear()


class ImmediateConsentRepository(FakeConsentRepository):
    """For use cases that aren't wrapped in a UnitOfWork (grant/withdraw/save health):
    a write is visible as soon as it is made."""

    def add(self, consent: Consent) -> None:
        super().add(consent)
        self.commit()

    def save(self, consent: Consent) -> None:
        super().save(consent)
        self.commit()


class FakeHealthUnitOfWork:
    def __init__(
        self,
        *,
        members: FakeMemberRepository,
        consents: FakeConsentRepository,
        health: FakeHealthRepository,
        audit: FakeAuditRepository,
        clock: FixedClock,
    ) -> None:
        self.members = members
        self.consents = consents
        self.health = health
        self.audit = audit
        self.clock = clock
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> FakeHealthUnitOfWork:
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
        self.consents.commit()
        self.audit.commit()
        self.committed = True

    def rollback(self) -> None:
        self.consents.rollback()
        self.audit.rollback()
        self.rolled_back = True


def health_records(*records: HealthRecord) -> FakeHealthRepository:
    return FakeHealthRepository(list(records))


__all__ = [
    "FakeAuditRepository",
    "FakeConsentRepository",
    "FakeHealthUnitOfWork",
    "ImmediateConsentRepository",
    "health_records",
]
