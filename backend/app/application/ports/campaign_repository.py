from typing import Protocol
from uuid import UUID

from app.domain.campaign import Campaign


class CampaignRepository(Protocol):
    def get(self, campaign_id: UUID) -> Campaign | None: ...

    def get_by_code(self, code: str) -> Campaign | None: ...

    def list_active(self) -> list[Campaign]: ...

    def list_all(self) -> list[Campaign]: ...

    def add(self, campaign: Campaign) -> None: ...

    def save(self, campaign: Campaign) -> None:
        """Persist edits to name / dates / config / is_active. `type` is never changed
        here — see UpdateCampaign for why."""
        ...
