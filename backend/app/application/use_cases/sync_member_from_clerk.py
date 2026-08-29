"""Apply a verified Clerk webhook event to the local member table.

Two rules this must not break:

  - **The member owns their display name.** It is set when the row is first created and
    never overwritten afterwards, so a `user.updated` event from Clerk cannot rename
    someone the club knows by their running nickname. The single exception is replacing
    the JIT placeholder, which is not a name anybody chose.
  - **The picture is not theirs to own, and is refreshed every time.** Unlike the name,
    the club offers no way to set one — the only place it can come from is Clerk, so a
    member who changes their Google photo expects the club to follow. Keeping the first
    one forever would mean an avatar nobody can update.
  - **Roles come from here, not from a request.** The superuser is bootstrapped by
    matching the configured clerk_user_id, and only while the club has no superuser yet
    (the database allows exactly one).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

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
    image_url: str | None = None
    # Clerk's flag for whether the member actually set a picture. False means image_url
    # is a generated default and the app should draw its own initials avatar instead.
    has_image: bool = False
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

        # Always, on create and on update: see the note at the top about why the picture
        # is treated differently from the name. Written even when it is None, because
        # removing a photo at Clerk should remove it here too.
        if (member.image_url, member.has_image) != (event.image_url, event.has_image):
            self._members.set_avatar(member.id, event.image_url, event.has_image)
            member = replace(member, image_url=event.image_url, has_image=event.has_image)

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
        return replace(member, role=MemberRole.SUPERUSER)


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
