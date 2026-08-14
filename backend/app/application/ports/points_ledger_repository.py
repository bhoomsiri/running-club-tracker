from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.domain.redemption import PointsEntry


class PointsLedgerRepository(Protocol):
    def serialize_account(self, member_id: UUID, campaign_id: UUID) -> None:
        """Make this member's balance in this campaign exclusive for the rest of the
        transaction; other callers block here until it ends.

        Needed because a balance is SUM(delta) over rows that don't exist yet. Locking
        the existing ledger rows achieves nothing: two transactions can both read the
        same balance and then each INSERT a new negative row — a phantom write, and a
        double-spend. Serialising per (member, campaign) is what actually prevents it.

        Call it BEFORE reading the balance, inside the same transaction. Implementations
        that aren't transactional (the in-memory fake) may make this a no-op.

        Two disciplines every ledger-writing use case must keep (see CLAUDE.md rule #5):
          - EVERY path that writes a ledger row calls this first — adjustments and
            reversals too, not just redemptions. This is a mutex: it protects the
            account only while all writers take it.
          - Lock order is always reward row -> account. `redeem_reward` calls
            `rewards.get_for_update()` and then this; taking them the other way round
            in a new use case risks a deadlock against it.
        """
        ...

    def balance(self, member_id: UUID, campaign_id: UUID) -> Decimal:
        """SUM(delta) for this member in this campaign. Always computed, never cached."""
        ...

    def credited_total(self, member_id: UUID, campaign_id: UUID) -> Decimal:
        """SUM(delta) over EARNING rows only — run_earned and reversal.

        Deliberately excludes `adjustment`: a superuser's manual correction is not
        earning, so reconciliation must not treat it as already-credited and quietly
        undo it on the next run. Excludes `redeemed` too — spending is not un-earning.
        """
        ...

    def has_entries_for_campaign(self, campaign_id: UUID) -> bool:
        """Whether any points have moved in this campaign — history that a change of
        campaign type would silently reinterpret."""
        ...

    def add(self, entry: PointsEntry) -> None: ...
