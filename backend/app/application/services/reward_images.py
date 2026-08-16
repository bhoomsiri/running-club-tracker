"""Attaching a viewable URL to a reward.

Shared by the member catalogue and the admin one so both mint the link the same way, for
the same short window.

Evidence photos need the URL scoped to whoever is entitled to the run; a catalogue photo
does not. It is club material, shown to everyone who opens the rewards page, so any
authenticated caller may be handed one. The bucket stays private all the same — the link
is minted per request and stops working in minutes, which is what keeps the object out of
search engines and chat forwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.application.ports.image_storage import ImageStorage
from app.domain.redemption import Reward

# Long enough for a page to render, short enough that a copied link is stale almost
# immediately. Same reasoning as the evidence URLs.
IMAGE_URL_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class RewardOffer:
    reward: Reward
    image_url: str | None


def with_images(
    rewards: list[Reward],
    storage: ImageStorage,
    ttl: timedelta = IMAGE_URL_TTL,
) -> list[RewardOffer]:
    return [
        RewardOffer(
            reward=reward,
            image_url=(
                None
                if reward.image_key is None
                else storage.presigned_url(reward.image_key, ttl)
            ),
        )
        for reward in rewards
    ]
