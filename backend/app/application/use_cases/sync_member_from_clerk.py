"""Apply a verified Clerk webhook event to the local member table.

Two rules this must not break:

  - **The member owns their display name.** It is set when the row is first created and
    never overwritten afterwards, so a `user.updated` event from Clerk cannot rename
    someone the club knows by their running nickname. The single exception is replacing
    the JIT placeholder, which is not a name anybody chose.
  - **Roles come from here, not from a request.** The superuser is bootstrapped by
    matching the configured clerk_user_id, and only while the club has no superuser yet
    (the database allows exactly one).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.application.ports.clock import Clock
from app.application.ports.member_repository import MemberRepository
from app.application.use_cases.ensure_member import PLACEHOLDER_DISPLAY_NAME
from app.domain.entities import Member, MemberRole, validate_display_name
from app.domain.errors import InvalidMemberError, MemberAlreadyExists


@dataclass(frozen=True)
class ClerkUserEvent:
    clerk_user_id: str
    display_name: str | None
    # Used only to derive a readable name when Clerk has none; never stored, never logged.
    email: str | None = None
    created: bool = True


class SyncMemberFromClerk:
    def __init__(
        self,
        members: MemberRepository,
        clock: Clock,
        superuser_clerk_user_id: str | None = None,
    ) -> None:
        self._members = members
        self._clock = clock
        self._superuser_clerk_user_id = superuser_clerk_user_id

    def execute(self, event: ClerkUserEvent) -> Member:
        existing = self._members.get_by_clerk_id(event.clerk_user_id)
        name = _readable_name(event)

        if existing is None:
            member = Member.create(
                clerk_user_id=event.clerk_user_id,
                display_name=name,
                now=self._clock.now(),
                role=MemberRole.MEMBER,
            )
            try:
                self._members.add(member)
            except MemberAlreadyExists:
                member = self._members.get_by_clerk_id(event.clerk_user_id) or member
        else:
            member = existing
            # Only ever fills in the placeholder — a real name stays as the member set it.
            if member.display_name == PLACEHOLDER_DISPLAY_NAME and name != PLACEHOLDER_DISPLAY_NAME:
                self._members.set_display_name(member.id, name)

        return self._bootstrap_superuser(member)

    def _bootstrap_superuser(self, member: Member) -> Member:
        if self._superuser_clerk_user_id is None:
            return member
        if member.clerk_user_id != self._superuser_clerk_user_id:
            return member
        if member.role is MemberRole.SUPERUSER:
            return member

        # At most one superuser exists, enforced by uq_member_single_superuser. If the
        # seat is taken by someone else, leave this member alone rather than letting the
        # database reject the whole webhook.
        current = self._members.get_superuser()
        if current is not None and current.id != member.id:
            return member

        self._members.set_role(member.id, MemberRole.SUPERUSER)
        return Member(
            id=member.id,
            clerk_user_id=member.clerk_user_id,
            display_name=member.display_name,
            role=MemberRole.SUPERUSER,
            created_at=member.created_at,
            deleted_at=member.deleted_at,
        )


def _readable_name(event: ClerkUserEvent) -> str:
    """A member is never left nameless: Clerk's name, else the local part of their
    email, else a neutral placeholder the webhook may replace later."""
    for candidate in (event.display_name, _local_part(event.email)):
        if candidate:
            try:
                return validate_display_name(candidate)
            except InvalidMemberError:
                continue
    return PLACEHOLDER_DISPLAY_NAME


def _local_part(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.split("@", 1)[0] or None
