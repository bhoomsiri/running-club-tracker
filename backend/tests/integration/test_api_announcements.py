"""GET /announcements over HTTP — the one route in this API that answers without a token.

Everything else in the integration suite proves a caller cannot get in without a valid
session. This file proves the opposite for exactly one path, and that the path lets
nothing else through with it.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from app.api import deps
from app.config import Settings
from app.main import create_app
from tests.integration.conftest import BOSS_CLERK_ID, StubVerifier

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


@pytest.fixture
def client(
    session_factory: sessionmaker[Session], settings: Settings
) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[deps.get_settings_dep] = lambda: settings
    app.dependency_overrides[deps.get_session_factory_dep] = lambda: session_factory
    app.dependency_overrides[deps.get_token_verifier] = StubVerifier
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def boss(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            models.Member(
                id=uuid4(), clerk_user_id=BOSS_CLERK_ID, display_name="Boss", role="superuser"
            )
        )
        session.commit()


@pytest.fixture
def notices(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    ids = {"published": uuid4(), "older": uuid4(), "draft": uuid4()}
    with session_factory() as session:
        session.add(
            models.Announcement(
                id=ids["published"], title="ซ้อมวิ่งเช้าวันเสาร์",
                body="เจอกันหน้าตึกอำนวยการ 05:30 น.", is_published=True,
                created_at=NOW, updated_at=NOW,
            )
        )
        session.add(
            models.Announcement(
                id=ids["older"], title="เปิดรับสมัครสมาชิกใหม่", body="สมัครได้ที่หน้าเว็บ",
                is_published=True, created_at=NOW - timedelta(days=5),
                updated_at=NOW - timedelta(days=5),
            )
        )
        session.add(
            models.Announcement(
                id=ids["draft"], title="ยังไม่เผยแพร่", body="ร่างไว้ก่อน",
                is_published=False, created_at=NOW, updated_at=NOW,
            )
        )
        session.commit()
    return ids


def auth(who: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {who}"}


def test_it_answers_without_a_token(client: TestClient, notices: dict[str, UUID]) -> None:
    response = client.get("/announcements")

    assert response.status_code == 200
    assert [a["title"] for a in response.json()] == [
        "ซ้อมวิ่งเช้าวันเสาร์",
        "เปิดรับสมัครสมาชิกใหม่",
    ]


def test_a_draft_never_reaches_it(client: TestClient, notices: dict[str, UUID]) -> None:
    body = client.get("/announcements").json()

    assert all(a["id"] != str(notices["draft"]) for a in body)


def test_it_says_nothing_about_who_wrote_it(
    client: TestClient, notices: dict[str, UUID]
) -> None:
    """Anyone on the internet reads this, so the response carries the notice and
    nothing else — no author, no member id, not even whether it is published."""
    first = client.get("/announcements").json()[0]

    assert set(first) == {"id", "title", "body", "created_at", "updated_at"}


def test_a_bad_token_does_not_break_it(
    client: TestClient, notices: dict[str, UUID]
) -> None:
    """No dependency reads the header, so an expired session on a phone still shows the
    landing page rather than a 401."""
    response = client.get("/announcements", headers={"Authorization": "Bearer nonsense"})

    assert response.status_code == 200


def test_the_admin_list_still_needs_the_superuser(
    client: TestClient, notices: dict[str, UUID]
) -> None:
    assert client.get("/admin/announcements").status_code == 401
    assert client.get("/admin/announcements", headers=auth("user_alice")).status_code == 403


def test_the_superuser_sees_drafts_and_can_publish_one(
    client: TestClient, notices: dict[str, UUID], boss: None
) -> None:
    listed = client.get("/admin/announcements", headers=auth(BOSS_CLERK_ID)).json()
    assert {a["title"] for a in listed} >= {"ยังไม่เผยแพร่"}

    published = client.patch(
        f"/admin/announcements/{notices['draft']}",
        headers=auth(BOSS_CLERK_ID),
        json={"is_published": True},
    )
    assert published.status_code == 200, published.text

    public = client.get("/announcements").json()
    assert any(a["id"] == str(notices["draft"]) for a in public)


def test_posting_one_and_taking_it_down_again(
    client: TestClient, boss: None, session_factory: sessionmaker[Session]
) -> None:
    created = client.post(
        "/admin/announcements",
        headers=auth(BOSS_CLERK_ID),
        json={"title": "วิ่งการกุศล", "body": "รายละเอียดตามโปสเตอร์", "is_published": True},
    )
    assert created.status_code == 201, created.text
    notice_id = created.json()["id"]

    assert any(a["id"] == notice_id for a in client.get("/announcements").json())

    hidden = client.patch(
        f"/admin/announcements/{notice_id}",
        headers=auth(BOSS_CLERK_ID),
        json={"is_published": False},
    )
    assert hidden.status_code == 200

    assert all(a["id"] != notice_id for a in client.get("/announcements").json())
    # Hidden, never deleted — the row is still there to bring back.
    with session_factory() as session:
        assert session.get(models.Announcement, UUID(notice_id)) is not None
