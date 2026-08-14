from typing import Protocol
from uuid import UUID

from app.domain.entities import Member, MemberRole


class MemberRepository(Protocol):
    def get(self, member_id: UUID) -> Member | None: ...

    def get_by_clerk_id(self, clerk_user_id: str) -> Member | None: ...

    def get_superuser(self) -> Member | None:
        """The one superuser, if the club has one yet (the database allows at most one)."""
        ...

    def list_all(self) -> list[Member]: ...

    def add(self, member: Member) -> None:
        """Raises MemberAlreadyExists if this clerk_user_id is already provisioned —
        two simultaneous first requests must not create two rows."""
        ...

    def set_role(self, member_id: UUID, role: MemberRole) -> None:
        """Roles are only ever written from the verified webhook or the bootstrap
        setting — never from anything a client sends."""
        ...

    def set_display_name(self, member_id: UUID, display_name: str) -> None: ...
