from typing import Protocol
from uuid import UUID

from app.domain.redemption import Redemption, RedemptionStatus


class RedemptionRepository(Protocol):
    def add(self, redemption: Redemption) -> None: ...

    def get(self, redemption_id: UUID) -> Redemption | None: ...

    def list_by_member(self, member_id: UUID) -> list[Redemption]: ...

    def list_pending(self) -> list[Redemption]: ...

    def list_all(self) -> list[Redemption]:
        """Every redemption whatever its status, oldest first — for the export, where
        the cancelled ones matter as much as the pending."""
        ...

    def set_status(self, redemption_id: UUID, status: RedemptionStatus) -> None: ...

    def exists_for_reward(self, reward_id: UUID) -> bool:
        """Whether anyone has ever redeemed this reward. A reward with history is
        retired with is_active=False, never deleted."""
        ...
