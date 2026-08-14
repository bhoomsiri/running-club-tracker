"""Turn a verified identity into a member row (just-in-time provisioning).

The Clerk `user.created` webhook is the normal way a member appears. This exists for the
race where a brand-new member's first API request arrives before that webhook does: the
token is already verified, so refusing them would be wrong, and waiting is worse.

It only ever creates an ordinary member. Promotion to admin or superuser happens through
the verified webhook / bootstrap setting alone — never on the strength of a request.
"""

from __future__ import annotations

from app.application.ports.clock import Clock
from app.application.ports.member_repository import MemberRepository
from app.application.ports.token_verifier import VerifiedIdentity
from app.domain.entities import Member, MemberRole
from app.domain.errors import MemberAlreadyExists, MemberNotFound

# What a JIT-created member is called until the webhook supplies their real name. The
# webhook may replace exactly this value and nothing else, so a name the member chose
# themselves is never overwritten.
PLACEHOLDER_DISPLAY_NAME = "สมาชิกใหม่"


class EnsureMember:
    def __init__(self, members: MemberRepository, clock: Clock) -> None:
        self._members = members
        self._clock = clock

    def execute(self, identity: VerifiedIdentity) -> Member:
        existing = self._members.get_by_clerk_id(identity.clerk_user_id)
        if existing is not None:
            return existing

        member = Member.create(
            clerk_user_id=identity.clerk_user_id,
            display_name=identity.display_name or PLACEHOLDER_DISPLAY_NAME,
            now=self._clock.now(),
            role=MemberRole.MEMBER,
        )
        try:
            self._members.add(member)
        except MemberAlreadyExists:
            # Another request (or the webhook) won the race. Theirs is the real row.
            won = self._members.get_by_clerk_id(identity.clerk_user_id)
            if won is None:  # pragma: no cover - would mean the row vanished mid-flight
                raise MemberNotFound(identity.clerk_user_id) from None
            return won
        return member
