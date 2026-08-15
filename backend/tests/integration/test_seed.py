"""The seed script, against a real database.

It writes the settings every member's points are derived from, and it is run by hand
against production — so the two things that matter are that a second run changes
nothing, and that rewards stay out unless they are asked for.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from app.seed import CAMPAIGNS, REWARDS, seed

pytestmark = pytest.mark.integration


def counts(session_factory: sessionmaker[Session]) -> tuple[int, int]:
    with session_factory() as session:
        campaigns = session.execute(
            sa.select(sa.func.count()).select_from(models.Campaign)
        ).scalar_one()
        rewards = session.execute(
            sa.select(sa.func.count()).select_from(models.Reward)
        ).scalar_one()
    return campaigns, rewards


def test_by_default_campaigns_are_seeded_and_rewards_are_not(
    session_factory: sessionmaker[Session],
) -> None:
    """The production default. Rewards are named, priced and stocked by the club through
    the superuser endpoints — seeding the placeholder catalogue would publish prizes
    nobody agreed to."""
    with session_factory() as session:
        seed(session)

    assert counts(session_factory) == (len(CAMPAIGNS), 0)


def test_the_campaigns_survive_the_early_return(
    session_factory: sessionmaker[Session],
) -> None:
    """Skipping rewards leaves the function before the commit at the bottom, so it has
    to commit on the way out — otherwise the session rolls back and the run does
    nothing at all."""
    with session_factory() as session:
        seed(session)

    with session_factory() as fresh:
        codes = set(
            fresh.execute(sa.select(models.Campaign.code)).scalars().all()
        )
    assert codes == {str(spec["code"]) for spec in CAMPAIGNS}


def test_rewards_are_seeded_when_asked_for(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        seed(session, include_rewards=True)

    assert counts(session_factory) == (len(CAMPAIGNS), len(REWARDS))


def test_running_it_twice_changes_nothing(
    session_factory: sessionmaker[Session],
) -> None:
    """It is run by hand against a live database; a second run must not double the
    catalogue or reset a campaign someone has since edited."""
    with session_factory() as session:
        seed(session, include_rewards=True)
    first = counts(session_factory)

    with session_factory() as session:
        seed(session, include_rewards=True)

    assert counts(session_factory) == first


def test_seeding_rewards_after_campaigns_only_tops_up_the_missing_half(
    session_factory: sessionmaker[Session],
) -> None:
    """The likely real sequence: campaigns in production first, rewards decided later."""
    with session_factory() as session:
        seed(session)
    with session_factory() as session:
        seed(session, include_rewards=True)

    assert counts(session_factory) == (len(CAMPAIGNS), len(REWARDS))
