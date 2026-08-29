"""One transaction covering an admin's audited read of a member's contact details.

Narrower than it looks: the details live on the member row, so this needs `members` and
somewhere to write the audit entry, and nothing else. It carries NO consent repository,
and that absence is the decision rather than an omission — see below.

The emergency contact is collected so somebody can be reached if a member collapses on a
run. Its lawful basis is that safety interest (PDPA มาตรา 24), not the consent that
covers holding health measurements, so withdrawing consent for health data does not make
a member unreachable in an emergency. Gating this on that consent would have meant the
club could not phone the person's family at the moment the number was collected for.

What withdrawal does close is the health data itself and the screening — see
`HealthUnitOfWork` and `ScreeningViewUnitOfWork`, both of which do carry consent.

Opening the details is still an event: the audit entry is committed before anything is
returned, so the club can show when it looked and, just as importantly, when it did not.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.audit_repository import AuditRepository
from app.application.ports.clock import Clock
from app.application.ports.member_repository import MemberRepository


class ContactViewUnitOfWork(Protocol):
    @property
    def members(self) -> MemberRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> ContactViewUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
