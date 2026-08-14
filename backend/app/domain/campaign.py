"""Campaigns and the policy abstraction.

An activity format varies in exactly two ways: what one run contributes, and how those
contributions roll up. Both live behind `CampaignPolicy`, so adding next year's format
is a new policy file plus one registry line — never an `if campaign.type == ...`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from app.domain.entities import RunEntry
from app.domain.errors import InvalidCampaignError


class CampaignType(StrEnum):
    CUMULATIVE_DISTANCE = "cumulative_distance"
    REDEEM_REWARD = "redeem_reward"
    DAILY_THRESHOLD_REWARD = "daily_threshold_reward"


@dataclass(frozen=True)
class Campaign:
    id: UUID
    code: str
    name: str
    type: CampaignType
    starts_on: date
    ends_on: date
    config: Mapping[str, object]
    is_active: bool

    @classmethod
    def create(
        cls,
        *,
        code: str,
        name: str,
        type: CampaignType,
        starts_on: date,
        ends_on: date,
        config: Mapping[str, object] | None = None,
        is_active: bool = True,
        id: UUID | None = None,
    ) -> Campaign:
        if not code.strip():
            raise InvalidCampaignError("code is required")
        if ends_on < starts_on:
            raise InvalidCampaignError("ends_on cannot be before starts_on")
        return cls(
            id=id or uuid4(),
            code=code.strip(),
            name=name.strip(),
            type=type,
            starts_on=starts_on,
            ends_on=ends_on,
            config=dict(config or {}),
            is_active=is_active,
        )

    def contains(self, run_date: date) -> bool:
        """Is this run inside the campaign's window? Progress is derived by filtering
        runs through here at read time — there is no stored progress to drift."""
        return self.starts_on <= run_date <= self.ends_on

    def required_decimal(self, key: str) -> Decimal:
        """Read a numeric policy parameter out of `config` as an exact Decimal.

        Goes via `str()` because JSON numbers arrive as int/float; `Decimal(0.1)` would
        carry binary float error into reward maths.
        """
        raw = self.config.get(key)
        if raw is None:
            raise InvalidCampaignError(f"campaign {self.code!r} config is missing {key!r}")
        try:
            value = Decimal(str(raw))
        except (InvalidOperation, ValueError) as e:
            msg = f"campaign {self.code!r} config {key!r} is not a number"
            raise InvalidCampaignError(msg) from e
        if value <= 0:
            raise InvalidCampaignError(f"campaign {self.code!r} config {key!r} must be positive")
        return value


@dataclass(frozen=True)
class CampaignProgress:
    """What a member has accumulated in one campaign."""

    campaign_id: UUID
    value: Decimal
    unit: str
    target: Decimal | None  # None when the campaign has no finish line
    completed: bool

    @property
    def percent(self) -> Decimal | None:
        if self.target is None or self.target == 0:
            return None
        return min(Decimal("100"), (self.value / self.target * 100).quantize(Decimal("0.1")))


class CampaignPolicy(Protocol):
    """What one run contributes, and how contributions roll up."""

    @property
    def required_config(self) -> tuple[str, ...]:
        """The config keys this format cannot work without.

        Declared by the policy so campaign creation can be validated without anyone
        keeping a second list of "what does this type need?" somewhere else.
        """
        ...

    @property
    def tracks_points(self) -> bool:
        """Does this format put points in the ledger? Callers that need a balance ask
        the policy this instead of inspecting `campaign.type` — the registry stays the
        only place that knows which type means what."""
        ...

    def contribution(self, campaign: Campaign, run: RunEntry) -> Decimal: ...

    def progress(self, campaign: Campaign, runs: Sequence[RunEntry]) -> CampaignProgress: ...


def validate_config_for(campaign: Campaign) -> None:
    """Every key the campaign's policy needs is present and a positive number.

    Called when a campaign is created or edited, so a malformed config is refused at the
    door rather than surfacing later as a member's progress silently failing to compute.
    """
    from app.domain.campaigns import policy_for

    for key in policy_for(campaign.type).required_config:
        campaign.required_decimal(key)
