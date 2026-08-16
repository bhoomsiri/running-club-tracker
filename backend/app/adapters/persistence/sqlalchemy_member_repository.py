from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.adapters.persistence.mappers import member_to_domain, member_to_orm
from app.domain.entities import Member, MemberProfile, MemberRole
from app.domain.errors import MemberAlreadyExists


class SqlAlchemyMemberRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_superuser(self) -> Member | None:
        row = self._session.execute(
            sa.select(models.Member).where(models.Member.role == MemberRole.SUPERUSER.value)
        ).scalar_one_or_none()
        return member_to_domain(row) if row else None

    def list_all(self) -> list[Member]:
        rows = self._session.execute(
            sa.select(models.Member)
            .where(models.Member.deleted_at.is_(None))
            .order_by(models.Member.display_name)
        ).scalars()
        return [member_to_domain(r) for r in rows]

    def add(self, member: Member) -> None:
        # A SAVEPOINT, not the whole transaction: losing the provisioning race must not
        # discard everything else the caller has already done in this request.
        try:
            with self._session.begin_nested():
                self._session.add(member_to_orm(member))
                self._session.flush()
        except IntegrityError as e:
            # uq_member_clerk_user_id: two first requests raced, or the webhook got here
            # first. The savepoint is rolled back; the session stays usable so the caller
            # can re-read the winner.
            raise MemberAlreadyExists(member.clerk_user_id) from e

    def set_role(self, member_id: UUID, role: MemberRole) -> None:
        self._session.execute(
            sa.update(models.Member)
            .where(models.Member.id == member_id)
            .values(role=role.value, updated_at=sa.func.now())
        )
        self._session.flush()

    def set_display_name(self, member_id: UUID, display_name: str) -> None:
        self._session.execute(
            sa.update(models.Member)
            .where(models.Member.id == member_id)
            .values(display_name=display_name, updated_at=sa.func.now())
        )
        self._session.flush()

    def set_profile(self, member_id: UUID, profile: MemberProfile) -> None:
        """Profile only. `role` is not reachable from here on purpose — it is written by
        the verified webhook or the bootstrap setting, never by anything a member sends.
        """
        self._session.execute(
            sa.update(models.Member)
            .where(models.Member.id == member_id)
            .values(
                full_name_th=profile.full_name_th,
                birth_year=profile.birth_year,
                sex=profile.sex.value if profile.sex else None,
                position=profile.position,
                department=profile.department,
                phone=profile.phone,
                emergency_contact_name=profile.emergency_contact_name,
                emergency_contact_phone=profile.emergency_contact_phone,
                updated_at=sa.func.now(),
            )
        )
        self._session.flush()

    def get(self, member_id: UUID) -> Member | None:
        row = self._session.get(models.Member, member_id)
        # A member awaiting erasure is treated as gone.
        if row is None or row.deleted_at is not None:
            return None
        return member_to_domain(row)

    def get_by_clerk_id(self, clerk_user_id: str) -> Member | None:
        row = self._session.execute(
            sa.select(models.Member).where(models.Member.clerk_user_id == clerk_user_id)
        ).scalar_one_or_none()
        if row is None or row.deleted_at is not None:
            return None
        return member_to_domain(row)
