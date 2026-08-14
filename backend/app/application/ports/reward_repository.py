from typing import Protocol
from uuid import UUID

from app.domain.redemption import Reward


class RewardRepository(Protocol):
    def get(self, reward_id: UUID) -> Reward | None: ...

    def get_for_update(self, reward_id: UUID) -> Reward | None:
        """Read the reward and hold a row lock until the transaction ends
        (SELECT ... FOR UPDATE), so two concurrent redeems serialise instead of both
        seeing the same stock."""
        ...

    def list_active_for_campaign(self, campaign_id: UUID) -> list[Reward]:
        """The catalogue a member is shown: active rewards only. Out-of-stock ones stay
        visible with stock 0 — hiding them makes the list look arbitrary."""
        ...

    def decrement_stock(self, reward_id: UUID) -> None: ...

    def increment_stock(self, reward_id: UUID) -> None:
        """Put an item back when a redemption is cancelled."""
        ...

    def add(self, reward: Reward) -> None: ...

    def save(self, reward: Reward) -> None: ...
