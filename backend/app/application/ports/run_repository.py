from datetime import date
from typing import Protocol
from uuid import UUID

from app.domain.entities import ReviewStatus, RunEntry


class RunRepository(Protocol):
    def add(self, run: RunEntry) -> None: ...

    def get(self, run_id: UUID) -> RunEntry | None: ...

    def set_review_status(self, run_id: UUID, status: ReviewStatus) -> None:
        """An admin's decision. Never deletes the run — the history of what was
        submitted and what was decided about it both stay."""
        ...

    def list_by_member(self, member_id: UUID) -> list[RunEntry]:
        """Every run this member submitted. Campaign progress is derived by filtering
        these into each campaign's window, so there is no per-campaign query here."""
        ...

    def count_in_window(self, start: date, end: date) -> int:
        """How many runs (from anyone) fall inside these dates."""
        ...

    def has_flagged(self, member_id: UUID) -> bool:
        """Whether this member has a run still awaiting a decision."""
        ...

    def find_by_evidence_hash(self, digest: str) -> list[RunEntry]:
        """Every run submitted with this exact image, by anyone.

        Across all members on purpose: the same member reusing an image is a duplicate
        to refuse, while another member reusing it is something to flag for review.
        """
        ...
