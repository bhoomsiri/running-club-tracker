"""What the member has agreed to, if anything.

The gate itself lives in `save_health_record`; this exists so the UI can apply the same
gate before offering the form. A member should be told that health data needs consent
before they type their weight into a box, not after they press save — and the answer has
three states, not two: never agreed, agreed to wording that has since changed, and
agreed to the wording in force. Only the last one opens the form.
"""

from __future__ import annotations

from uuid import UUID

from app.application.ports.consent_repository import ConsentRepository
from app.domain.consent import Consent, ConsentPurpose


class GetMyConsent:
    def __init__(self, consents: ConsentRepository) -> None:
        self._consents = consents

    def execute(self, member_id: UUID) -> Consent | None:
        # Whatever version it agreed to; the caller compares that against the wording in
        # force, so a stale agreement is distinguishable from no agreement at all.
        return self._consents.get_current(member_id, ConsentPurpose.HEALTH_DATA)
