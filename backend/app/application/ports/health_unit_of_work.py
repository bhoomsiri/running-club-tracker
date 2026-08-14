from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.audit_repository import AuditRepository
from app.application.ports.clock import Clock
from app.application.ports.consent_repository import ConsentRepository
from app.application.ports.health_repository import HealthRepository
from app.application.ports.member_repository import MemberRepository


class HealthUnitOfWork(Protocol):
    """One transaction covering an admin's access to someone else's health data.

    Deliberately a separate port from the redemption `UnitOfWork` rather than extra
    attributes bolted onto it: each use case depends only on the repositories it
    actually uses (ISP), and neither port grows into a god-object holding every
    repository in the app.

    Its reason to exist is atomicity between the audit write and the read: the entry
    must be committed before the data is handed back, so that an access which cannot be
    logged does not happen.
    """

    @property
    def members(self) -> MemberRepository: ...

    @property
    def consents(self) -> ConsentRepository: ...

    @property
    def health(self) -> HealthRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> HealthUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
