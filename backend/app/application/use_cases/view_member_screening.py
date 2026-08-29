"""An admin reading ONE member's pre-exercise screening.

The same conditions as reading someone's health data, for the same reasons:

  1. the actor's role permits it — checked here as well as at the router, because the
     router gate is convenience and this is the control;
  2. the subject's consent is currently active. A screening is a cardiac and medication
     history: it is health data under มาตรา 26 in the same way a weight is, so the same
     basis governs it. Withdrawn consent closes this door even though the answers still
     exist — and even though their owner can still see them;
  3. the answers exist. A member who has not been screened yields nothing rather than a
     row of assumed "no"s;
  4. the access is written to audit_log AND COMMITTED before anything is returned. If
     the audit write fails, the whole thing fails and the caller gets nothing: an access
     that cannot be accounted for must not happen.

Condition 2 arrived later than the rest. Until then a member could withdraw consent, be
refused at `/admin/members/{id}/health`, and have their screening answers read on the
next endpoint along — which made withdrawal mean rather less than it appeared to.

Admins may read it, on the same terms as health data: this is a member's cardiac and
medication history, so the price of access is a row in audit_log with the reader's name
on it. That is what makes handing the capability to three people accountable rather than
merely convenient.

The audit row records that a screening was looked at and how many answers were "yes" —
never which questions, and never the answers themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.application.ports.screening_view_unit_of_work import ScreeningViewUnitOfWork
from app.domain.audit import AuditAction, AuditEntry
from app.domain.consent import ConsentPurpose
from app.domain.entities import Member
from app.domain.errors import ConsentRequired, MemberNotFound, NotAuthorized
from app.domain.screening import Screening


@dataclass(frozen=True)
class ViewMemberScreeningCommand:
    actor_id: UUID  # from the verified token
    subject_id: UUID  # only ever supplied on an admin endpoint


@dataclass(frozen=True)
class MemberScreeningView:
    subject: Member
    screening: Screening | None


class ViewMemberScreening:
    def __init__(self, uow: ScreeningViewUnitOfWork, consent_version: str) -> None:
        self._uow = uow
        self._consent_version = consent_version

    def execute(self, cmd: ViewMemberScreeningCommand) -> MemberScreeningView:
        with self._uow as uow:
            actor = uow.members.get(cmd.actor_id)
            if actor is None:
                raise MemberNotFound(str(cmd.actor_id))
            if not actor.role.may_view_others_health:
                raise NotAuthorized("admin only")

            subject = uow.members.get(cmd.subject_id)
            if subject is None:
                raise MemberNotFound(str(cmd.subject_id))

            consent = uow.consents.get_current(cmd.subject_id, ConsentPurpose.HEALTH_DATA)
            if consent is None or not consent.is_active(self._consent_version):
                # Refused BEFORE the audit row is written, exactly as the health read
                # refuses: an access that did not happen must not appear in the log as
                # though it did.
                raise ConsentRequired(
                    "this member's consent for health_data is not active"
                )

            screening = uow.screenings.get_for_member(cmd.subject_id)

            uow.audit.record(
                AuditEntry.create(
                    actor_member_id=actor.id,
                    action=AuditAction.VIEW_SCREENING,
                    subject_member_id=subject.id,
                    # Context only. Never which questions, never the answers.
                    detail={
                        "has_screening": screening is not None,
                        "yes_count": screening.yes_count if screening else 0,
                    },
                    now=uow.clock.now(),
                )
            )
            # Commit BEFORE returning: past this line the access is on the record. If
            # this raises, the `with` block rolls back and nothing is returned.
            uow.commit()

        return MemberScreeningView(subject=subject, screening=screening)
