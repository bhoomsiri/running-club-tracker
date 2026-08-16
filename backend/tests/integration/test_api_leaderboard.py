"""GET /leaderboard over HTTP.

Two things this proves that the unit tests cannot: it needs a session — unlike the
announcements it is not public — and the JSON that reaches a member carries a name, a
distance and two counts, with nothing about anybody's health, contact or department
riding along in it.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from app.api import deps
from app.config import Settings
from app.main import create_app
from tests.fakes.fake_storage import FakeImageStorage
from tests.integration.conftest import StubVerifier

pytestmark = pytest.mark.integration

DISTANCE_CAMPAIGN = UUID("11111111-1111-1111-1111-111111111111")
POINTS_CAMPAIGN = UUID("22222222-2222-2222-2222-222222222222")

ROW_FIELDS = {"rank", "member_id", "name", "total_distance_km", "points", "run_count"}


def photo(colour: tuple[int, int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (32, 32), color=colour).save(out, format="JPEG")
    return out.getvalue()


@pytest.fixture
def storage() -> FakeImageStorage:
    return FakeImageStorage()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], settings: Settings, storage: FakeImageStorage
) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[deps.get_settings_dep] = lambda: settings
    app.dependency_overrides[deps.get_session_factory_dep] = lambda: session_factory
    app.dependency_overrides[deps.get_token_verifier] = StubVerifier
    app.dependency_overrides[deps.get_image_storage] = lambda: storage
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def club(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    """Two members with runs already recorded, and their sensitive columns filled in —
    so a leak into the response would show up rather than being absent by accident."""
    ids = {"alice": uuid4(), "somchai": uuid4()}
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=DISTANCE_CAMPAIGN, code="100km", name="100 km",
                type="cumulative_distance", starts_on=date(2026, 1, 1),
                ends_on=date(2026, 12, 31), config={"target_km": 100},
            )
        )
        session.add(
            models.Campaign(
                id=POINTS_CAMPAIGN, code="rewards", name="Run for rewards",
                type="redeem_reward", starts_on=date(2026, 1, 1),
                ends_on=date(2026, 12, 31), config={"points_per_km": 1},
            )
        )
        session.add(
            models.Member(
                id=ids["alice"], clerk_user_id="user_alice", display_name="Alice",
                full_name_th="อลิศ ใจดี", sex="female", phone="0812345678",
                department="กลุ่มงานการพยาบาล", position="พยาบาลวิชาชีพ",
                emergency_contact_name="สมหญิง", emergency_contact_phone="0898765432",
            )
        )
        session.add(
            models.Member(
                id=ids["somchai"], clerk_user_id="user_somchai", display_name="Somchai",
                full_name_th="สมชาย แข็งแรง",
            )
        )
        for member_id, km in ((ids["alice"], "8"), (ids["somchai"], "21.5")):
            session.add(
                models.RunEntry(
                    id=uuid4(), member_id=member_id, distance_km=Decimal(km),
                    duration_seconds=1800, run_date=date(2026, 6, 1),
                    evidence_key=f"runs/{member_id}/{'a' * 64}.jpeg",
                    evidence_sha256="a" * 64, source="app_screenshot",
                    review_status="ok",
                )
            )
        session.commit()
    return ids


def auth(who: str = "user_alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {who}"}


def test_it_needs_a_session(client: TestClient, club: dict[str, UUID]) -> None:
    """Unlike the announcements: who at the hospital runs how far is not something to
    hand to anyone who finds the URL."""
    assert client.get("/leaderboard").status_code == 401


def test_it_ranks_by_distance(client: TestClient, club: dict[str, UUID]) -> None:
    body = client.get("/leaderboard", headers=auth()).json()

    assert [e["name"] for e in body["entries"]] == ["สมชาย แข็งแรง", "อลิศ ใจดี"]
    assert [e["rank"] for e in body["entries"]] == [1, 2]
    # A string on the wire, exact — the same Decimal discipline as everywhere else.
    assert body["entries"][0]["total_distance_km"] == "21.500"


def test_it_tells_the_caller_where_they_are(
    client: TestClient, club: dict[str, UUID]
) -> None:
    body = client.get("/leaderboard", headers=auth()).json()

    assert body["me"]["member_id"] == str(club["alice"])
    assert body["me"]["rank"] == 2
    assert body["total_members"] == 2


def test_a_row_carries_nothing_sensitive(
    client: TestClient, club: dict[str, UUID]
) -> None:
    """The widest audience of any response in this API: every member sees every row.
    Alice's sex, phone, department and emergency contact are all set in the fixture, so
    any of them appearing here would be a real leak rather than a missing field."""
    body = client.get("/leaderboard", headers=auth()).json()

    for entry in [*body["entries"], body["me"]]:
        assert set(entry) == ROW_FIELDS


def test_a_new_member_appears_the_moment_they_submit(
    client: TestClient, club: dict[str, UUID]
) -> None:
    """Provisioned just in time by their first request, and ranked from their first run
    — the leaderboard is derived from runs, not from a table anyone maintains."""
    before = client.get("/leaderboard", headers=auth("user_new")).json()
    assert before["me"]["rank"] == 3
    assert before["me"]["total_distance_km"] == "0.000"

    uploaded = client.post(
        "/runs/evidence", headers=auth("user_new"),
        files={"file": ("r.jpg", photo((7, 90, 160)), "image/jpeg")},
    )
    assert uploaded.status_code == 201, uploaded.text
    submitted = client.post(
        "/runs", headers=auth("user_new"),
        json={
            "distance_km": "30", "duration_seconds": 1800, "run_date": "2026-06-02",
            "image_key": uploaded.json()["image_key"], "source": "app_screenshot",
        },
    )
    assert submitted.status_code == 201, submitted.text

    after = client.get("/leaderboard", headers=auth("user_new")).json()
    assert after["me"]["rank"] == 1
    assert after["entries"][0]["total_distance_km"] == "30.000"
