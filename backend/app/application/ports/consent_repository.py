from typing import Protocol
from uuid import UUID

from app.domain.consent import Consent, ConsentPurpose


class ConsentRepository(Protocol):
    def get_current(self, member_id: UUID, purpose: ConsentPurpose) -> Consent | None:
        """The member's not-yet-withdrawn consent for this purpose, whatever version it
        agreed to — comparing that version against the wording in force is the use
        case's job, so a stale agreement can be told apart from none at all.
        """
        ...

    def add(self, consent: Consent) -> None: ...

    def save(self, consent: Consent) -> None:
        """Persist a change to an existing consent (i.e. its withdrawal)."""
        ...
