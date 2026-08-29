"""One transaction covering an admin's audited read of a member's screening.

Split out from what used to be a shared `SensitiveViewUnitOfWork` carrying both this and
the contact details. They stopped being the same thing the day the club decided they rest
on different legal bases: a screening is health data and rides on the member's consent,
while the emergency contact rides on keeping people safe (PDPA มาตรา 24) and is reachable
whatever the consent record says. One port holding both would have let either use case
pick up a repository it must not use, and — worse — would have said the two were alike.

Same reason to exist as `HealthUnitOfWork`, one table over: the audit entry must be
committed before the answers are returned, so an access that cannot be accounted for does
not happen.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.audit_repository import AuditRepository
from app.application.ports.clock import Clock
from app.application.ports.consent_repository import ConsentRepository
from app.application.ports.member_repository import MemberRepository
from app.application.ports.screening_repository import ScreeningRepository


class ScreeningViewUnitOfWork(Protocol):
    @property
    def members(self) -> MemberRepository: ...

    @property
    def screenings(self) -> ScreeningRepository: ...

    @property
    def consents(self) -> ConsentRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> ScreeningViewUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
