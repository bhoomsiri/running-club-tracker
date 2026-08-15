"""GET /consent — the state the UI gates the health form on.

Three states, not two. A member who never agreed and one whose agreement predates a
change in the wording both have to be asked again, and the screen has to be able to tell
them apart from someone who is free to fill the form in.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from tests.integration.conftest import CONSENT_VERSION

pytestmark = pytest.mark.integration

ALICE = "user_alice"


def auth(clerk_user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {clerk_user_id}"}


@pytest.fixture(autouse=True)
def alice(session_factory: sessionmaker[Session]) -> None:
    # Provisioned just in time by the first authenticated call, so nothing to seed.
    return None


def test_a_member_who_never_agreed_gets_null(client: TestClient) -> None:
    """Null, not 404: never having agreed is an ordinary state, and the screen should
    not have to treat it as an error to know to show the consent text."""
    response = client.get("/consent", headers=auth(ALICE))

    assert response.status_code == 200
    assert response.json() is None


def test_after_granting_it_is_active(client: TestClient) -> None:
    assert client.post("/consent", headers=auth(ALICE)).status_code == 201

    body = client.get("/consent", headers=auth(ALICE)).json()

    assert body["active"] is True
    assert body["purpose"] == "health_data"
    assert body["version"] == CONSENT_VERSION
    assert body["withdrawn_at"] is None


def test_after_withdrawing_the_member_is_back_to_having_none(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """Null again, because the repository only ever returns a consent that has not been
    withdrawn. To the screen that is the same answer as never having agreed, which is
    right: either way the member has to be asked before the form opens.

    The row itself is not deleted, and that matters for PDPA accountability — the club
    must be able to show when consent was given and when it was taken back. That record
    just isn't this endpoint's job.
    """
    client.post("/consent", headers=auth(ALICE))
    assert client.delete("/consent", headers=auth(ALICE)).status_code == 204

    assert client.get("/consent", headers=auth(ALICE)).json() is None

    with session_factory() as session:
        withdrawn = session.query(models.Consent).one()
        assert withdrawn.withdrawn_at is not None, "the record must survive withdrawal"


def test_consent_to_older_wording_is_reported_as_inactive(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    """The case that would otherwise pass silently: the member agreed, the club changed
    what it was asking for, and the form must close until they agree again."""
    client.post("/consent", headers=auth(ALICE))
    with session_factory() as session:
        consent = session.query(models.Consent).one()
        consent.version = "v0-older-wording"
        session.commit()

    body = client.get("/consent", headers=auth(ALICE)).json()

    assert body["version"] == "v0-older-wording"
    assert body["active"] is False
    assert body["withdrawn_at"] is None, "not withdrawn — just out of date"


def test_one_member_never_sees_another_members_consent(client: TestClient) -> None:
    client.post("/consent", headers=auth(ALICE))

    assert client.get("/consent", headers=auth("user_somchai")).json() is None


def test_it_needs_a_token(client: TestClient) -> None:
    assert client.get("/consent").status_code == 401
