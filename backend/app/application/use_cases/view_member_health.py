"""An admin or superuser reading ONE member's health data.

Three conditions, all of them required:

  1. the actor's role permits it (checked here as well as at the router — the router
     gate is convenience, this one is the control);
  2. the subject's consent is currently active, because consent is the club's basis for
     processing their health data at all. Withdrawn consent closes this door even
     though the data still exists — and even though its owner can still see it;
  3. the access is written to audit_log AND COMMITTED before any data is returned. If
     the audit write fails, the whole thing fails and the caller gets nothing: an
     access that cannot be accounted for must not happen.

Only reads that actually return health data are audited (one row per subject). The
admin member list shows no health data, so it writes no audit rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.health_unit_of_work import HealthUnitOfWork
from app.domain.audit import AuditAction, AuditEntry
from app.domain.consent import ConsentPurpose
from app.domain.entities import Member
from app.domain.errors import ConsentRequired, MemberNotFound, NotAuthorized
from app.domain.health import HealthComparison


@dataclass(frozen=True)
class ViewMemberHealthCommand:
    actor_id: UUID  # from the verified token
    subject_id: UUID  # the member being looked at — only ever on an admin endpoint


@dataclass(frozen=True)
class MemberHealthView:
    subject: Member
    health: list[HealthComparison]


class ViewMemberHealth:
    def __init__(self, uow: HealthUnitOfWork, consent_version: str) -> None:
        self._uow = uow
        self._consent_version = consent_version

    def execute(self, cmd: ViewMemberHealthCommand) -> MemberHealthView:
        with self._uow as uow:
            actor = uow.members.get(cmd.actor_id)
            if actor is None:
                raise MemberNotFound(str(cmd.actor_id))
            if not actor.role.may_view_others_health:
                raise NotAuthorized("only an admin or the superuser may view health data")

            subject = uow.members.get(cmd.subject_id)
            if subject is None:
                raise MemberNotFound(str(cmd.subject_id))

            consent = uow.consents.get_current(cmd.subject_id, ConsentPurpose.HEALTH_DATA)
            if consent is None or not consent.is_active(self._consent_version):
                raise ConsentRequired(
                    "this member's consent for health_data is not active"
                )

            records = uow.health.list_by_member(cmd.subject_id)
            comparisons = [
                HealthComparison.build(campaign_id, records)
                for campaign_id in dict.fromkeys(r.campaign_id for r in records)
            ]

            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.VIEW_HEALTH,
                    subject_member_id=subject.id,
                    # Context only — never the measurements themselves.
                    detail={"campaign_count": len(comparisons)},
                    now=uow.clock.now(),
                )
            )
            # Commit BEFORE returning: past this line the access is on the record. If
            # this raises, the `with` block rolls back and nothing is returned.
            uow.commit()

        return MemberHealthView(subject=subject, health=comparisons)
