from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.application.ports.audit_repository import AuditRepository
from app.application.ports.clock import Clock
from app.application.ports.member_repository import MemberRepository
from app.application.ports.screening_repository import ScreeningRepository


class SensitiveViewUnitOfWork(Protocol):
    """One transaction covering an audited read of a member's sensitive details.

    Two use cases share it — the screening and the contact details — because they need
    the same thing for the same reason: the audit row must be committed before the data
    is returned, so an access that cannot be accounted for does not happen. Health has
    its own port because it also has to check consent; this one does not carry a consent
    repository it would never use.

    `members` covers the contact details, which live on the member row itself.
    """

    @property
    def members(self) -> MemberRepository: ...

    @property
    def screenings(self) -> ScreeningRepository: ...

    @property
    def audit(self) -> AuditRepository: ...

    @property
    def clock(self) -> Clock: ...

    def __enter__(self) -> SensitiveViewUnitOfWork: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...
