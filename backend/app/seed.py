"""Seed this year's activities, and optionally the reward catalogue.

Run once against a fresh database, after `alembic upgrade head`:

    cd backend && python -m app.seed                    # campaigns only
    cd backend && SEED_REWARDS=true python -m app.seed  # campaigns + rewards

Campaigns are seeded every time; rewards are opt-in because their names, costs and
stock are the club's decision and are meant to be set by a superuser through the API
rather than fixed here. The placeholder catalogue below is for a demo or a fresh local
database — seeding it into production would publish prizes nobody agreed to.

Idempotent: campaigns are matched by `code` and rewards by (campaign, name), so running
it twice changes nothing. It only ever inserts — it will not overwrite a campaign that
has already been edited, because members' points are derived from these settings and
silently changing them would rewrite history.
"""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.adapters.persistence import models
from app.db import get_session_factory

# ปีนี้: two activities running side by side over the same window.
STARTS_ON = date(2026, 8, 15)
ENDS_ON = date(2026, 9, 30)

CAMPAIGNS = [
    {
        "code": "hundred-km-2026",
        "name": "สะสมระยะ 100 กิโลเมตร",
        "type": "cumulative_distance",
        "config": {"target_km": 100},
    },
    {
        "code": "daily-10km-2026",
        "name": "วันละ 10 กิโลเมตร สะสมแลกของรางวัล",
        "type": "daily_threshold_reward",
        # A day counts once its runs total 10 km, and only if submitted by the next day.
        "config": {
            "qualifying_km": 10,
            "points_per_qualifying_day": 1,
            "submit_within_days": 1,
        },
    },
]

# Costs are in points, i.e. qualifying days.
REWARDS = [
    {"name": "ขวดน้ำประจำชมรม", "points_cost": Decimal("5"), "stock": 30},
    {"name": "ผ้าบัฟ", "points_cost": Decimal("8"), "stock": 25},
    {"name": "เสื้อวิ่งประจำปี", "points_cost": Decimal("15"), "stock": 20},
    {"name": "กระเป๋าคาดเอว", "points_cost": Decimal("20"), "stock": 10},
    {"name": "รองเท้าวิ่ง (ของรางวัลใหญ่)", "points_cost": Decimal("30"), "stock": 3},
]

REWARD_CAMPAIGN_CODE = "daily-10km-2026"


def seed(session: Session, *, include_rewards: bool = False) -> None:
    campaign_ids: dict[str, uuid.UUID] = {}

    for spec in CAMPAIGNS:
        existing = session.execute(
            sa.select(models.Campaign).where(models.Campaign.code == spec["code"])
        ).scalar_one_or_none()
        if existing is not None:
            campaign_ids[str(spec["code"])] = existing.id
            print(f"campaign {spec['code']}: already exists, left untouched")
            continue

        campaign = models.Campaign(
            id=uuid.uuid4(),
            code=spec["code"],
            name=spec["name"],
            type=spec["type"],
            starts_on=STARTS_ON,
            ends_on=ENDS_ON,
            config=spec["config"],
            is_active=True,
        )
        session.add(campaign)
        session.flush()
        campaign_ids[str(spec["code"])] = campaign.id
        print(f"campaign {spec['code']}: created")

    if not include_rewards:
        # Commit what has been done before leaving, or the campaigns roll back with the
        # session and the run achieves nothing.
        session.commit()
        print("rewards: skipped (set SEED_REWARDS=true to seed them too)")
        return

    created = 0
    skipped = 0
    rewards_campaign_id = campaign_ids[REWARD_CAMPAIGN_CODE]
    for reward in REWARDS:
        exists = session.execute(
            sa.select(models.Reward).where(
                models.Reward.campaign_id == rewards_campaign_id,
                models.Reward.name == reward["name"],
            )
        ).scalar_one_or_none()
        if exists is not None:
            skipped += 1
            continue
        session.add(
            models.Reward(
                id=uuid.uuid4(),
                campaign_id=rewards_campaign_id,
                name=reward["name"],
                points_cost=reward["points_cost"],
                stock=reward["stock"],
                is_active=True,
            )
        )
        created += 1

    # Reward names are Thai; printing counts keeps this readable on a Windows console
    # that isn't UTF-8.
    print(f"rewards: {created} created, {skipped} already present")
    session.commit()


def main() -> None:
    include_rewards = os.getenv("SEED_REWARDS", "false").lower() == "true"
    with get_session_factory()() as session:
        seed(session, include_rewards=include_rewards)
    print("seed complete")


if __name__ == "__main__":
    main()
