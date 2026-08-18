"""A member filling in or correcting their own details.

Their own, always: `member_id` comes from the verified token and there is no field on
the command for anyone else's. `role` is not reachable from here either — it is written
by the verified Clerk webhook or the bootstrap setting, never by anything a client
sends, so this cannot become a way to promote yourself.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.clock import Clock
from app.application.ports.member_repository import MemberRepository
from app.domain.entities import Member, Sex, ShirtSize, build_profile
from app.domain.errors import MemberNotFound


@dataclass(frozen=True)
class UpdateMyProfileCommand:
    member_id: UUID  # from the verified token, never from the request body
    full_name_th: str
    birth_year: int
    sex: Sex
    position: str
    department: str
    shirt_size: ShirtSize
    phone: str
    emergency_contact_name: str
    emergency_contact_phone: str


class UpdateMyProfile:
    def __init__(self, members: MemberRepository, clock: Clock) -> None:
        self._members = members
        self._clock = clock

    def execute(self, cmd: UpdateMyProfileCommand) -> Member:
        member = self._members.get(cmd.member_id)
        if member is None:
            raise MemberNotFound(str(cmd.member_id))

        # All of it together: this is not a patch of individual fields, because a profile
        # with half an emergency contact is not useful to anyone at the roadside.
        profile = build_profile(
            full_name_th=cmd.full_name_th,
            birth_year=cmd.birth_year,
            sex=cmd.sex,
            position=cmd.position,
            department=cmd.department,
            shirt_size=cmd.shirt_size,
            phone=cmd.phone,
            emergency_contact_name=cmd.emergency_contact_name,
            emergency_contact_phone=cmd.emergency_contact_phone,
            now=self._clock.now(),
        )
        self._members.set_profile(member.id, profile)
        return member.with_profile(profile)
