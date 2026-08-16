"""GET /rewards and the earn -> see -> redeem loop, end to end over HTTP."""

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
from tests.integration.conftest import BOSS_CLERK_ID, StubVerifier

pytestmark = pytest.mark.integration

REWARDS_CAMPAIGN = UUID("22222222-2222-2222-2222-222222222222")
DISTANCE_CAMPAIGN = UUID("11111111-1111-1111-1111-111111111111")


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
def catalogue(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    ids = {"alice": uuid4(), "shirt": uuid4(), "cap": uuid4(), "retired": uuid4()}
    with session_factory() as session:
        session.add(
            models.Campaign(
                id=REWARDS_CAMPAIGN, code="rewards", name="Run for rewards",
                type="redeem_reward", starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
                config={"points_per_km": 2},
            )
        )
        session.add(
            models.Campaign(
                id=DISTANCE_CAMPAIGN, code="100km", name="100 km",
                type="cumulative_distance", starts_on=date(2026, 1, 1),
                ends_on=date(2026, 12, 31), config={"target_km": 100},
            )
        )
        session.add(
            models.Member(id=ids["alice"], clerk_user_id="user_alice", display_name="Alice")
        )
        session.add(
            models.Reward(
                id=ids["shirt"], campaign_id=REWARDS_CAMPAIGN, name="Shirt",
                points_cost=Decimal("10"), stock=3,
            )
        )
        session.add(
            models.Reward(
                id=ids["cap"], campaign_id=REWARDS_CAMPAIGN, name="Cap",
                points_cost=Decimal("500"), stock=1,
            )
        )
        session.add(
            models.Reward(
                id=ids["retired"], campaign_id=REWARDS_CAMPAIGN, name="Last year's medal",
                points_cost=Decimal("1"), stock=9, is_active=False,
            )
        )
        session.commit()
    return ids


def auth(who: str = "user_alice") -> dict[str, str]:
    return {"Authorization": f"Bearer {who}"}


def submit_run(client: TestClient, km: str, colour: tuple[int, int, int]) -> None:
    uploaded = client.post(
        "/runs/evidence", headers=auth(), files={"file": ("r.jpg", photo(colour), "image/jpeg")}
    )
    assert uploaded.status_code == 201, uploaded.text
    created = client.post(
        "/runs",
        headers=auth(),
        json={
            "distance_km": km, "duration_seconds": 1800, "run_date": "2026-06-01",
            "image_key": uploaded.json()["image_key"], "source": "app_screenshot",
        },
    )
    assert created.status_code == 201, created.text


def test_the_catalogue_needs_a_token(client: TestClient) -> None:
    assert client.get("/rewards").status_code == 401


def test_only_campaigns_that_use_points_appear(
    client: TestClient, catalogue: dict[str, UUID]
) -> None:
    body = client.get("/rewards", headers=auth()).json()

    assert [c["code"] for c in body] == ["rewards"]  # the 100 km campaign has no rewards


def test_retired_rewards_are_not_listed(
    client: TestClient, catalogue: dict[str, UUID]
) -> None:
    body = client.get("/rewards", headers=auth()).json()

    assert {r["name"] for r in body[0]["rewards"]} == {"Shirt", "Cap"}


def test_a_new_member_sees_a_zero_balance_and_can_afford_nothing(
    client: TestClient, catalogue: dict[str, UUID]
) -> None:
    body = client.get("/rewards", headers=auth()).json()

    assert body[0]["points_balance"] == "0"
    assert all(r["can_redeem"] is False for r in body[0]["rewards"])


def test_running_earns_points_that_show_up_in_the_catalogue(
    client: TestClient, catalogue: dict[str, UUID]
) -> None:
    """The loop that was missing: submitting a run has to move the balance."""
    submit_run(client, "5.25", (10, 20, 30))

    body = client.get("/rewards", headers=auth()).json()

    assert body[0]["points_balance"] == "10.50"  # 5.25 km x 2
    shirt = next(r for r in body[0]["rewards"] if r["name"] == "Shirt")
    cap = next(r for r in body[0]["rewards"] if r["name"] == "Cap")
    assert shirt["can_redeem"] is True  # costs 10
    assert cap["can_redeem"] is False  # costs 500


def test_the_summary_shows_earned_and_spendable_separately(
    client: TestClient, catalogue: dict[str, UUID]
) -> None:
    submit_run(client, "5.25", (10, 20, 30))

    summary = client.get("/me/summary", headers=auth()).json()

    rewards = next(c for c in summary["campaigns"] if c["code"] == "rewards")
    assert rewards["value"] == "10.50"  # earned, from the policy
    assert rewards["points_balance"] == "10.50"  # spendable, from the ledger


def test_redeeming_moves_the_balance_and_the_catalogue_follows(
    client: TestClient, catalogue: dict[str, UUID]
) -> None:
    submit_run(client, "5.25", (10, 20, 30))

    redeemed = client.post(f"/rewards/{catalogue['shirt']}/redeem", headers=auth())

    assert redeemed.status_code == 201
    body = client.get("/rewards", headers=auth()).json()
    assert body[0]["points_balance"] == "0.50"  # 10.50 - 10
    shirt = next(r for r in body[0]["rewards"] if r["name"] == "Shirt")
    assert shirt["stock"] == 2
    assert shirt["can_redeem"] is False  # no longer affordable

    summary = client.get("/me/summary", headers=auth()).json()
    rewards = next(c for c in summary["campaigns"] if c["code"] == "rewards")
    # Earned stays where it was; only the spendable balance moved.
    assert rewards["value"] == "10.50"
    assert rewards["points_balance"] == "0.50"


def test_two_runs_accumulate(client: TestClient, catalogue: dict[str, UUID]) -> None:
    submit_run(client, "5.25", (10, 20, 30))
    submit_run(client, "4.75", (200, 100, 50))

    body = client.get("/rewards", headers=auth()).json()

    assert body[0]["points_balance"] == "20.00"


def test_one_members_points_are_not_visible_to_another(
    client: TestClient, catalogue: dict[str, UUID]
) -> None:
    submit_run(client, "5.25", (10, 20, 30))

    body = client.get("/rewards", headers=auth("user_someone_else")).json()

    assert body[0]["points_balance"] == "0"


@pytest.fixture
def boss(session_factory: sessionmaker[Session]) -> None:
    """Seeded, not provisioned just in time: a first request makes an ordinary member,
    because the role only ever comes from the webhook or the bootstrap setting."""
    with session_factory() as session:
        session.add(
            models.Member(
                id=uuid4(), clerk_user_id=BOSS_CLERK_ID, display_name="Boss", role="superuser"
            )
        )
        session.commit()


class TestRewardPhotos:
    """Uploading a catalogue photo, and the one key a reward must never be pointed at."""

    def upload(self, client: TestClient) -> str:
        response = client.post(
            "/admin/rewards/image",
            headers=auth(BOSS_CLERK_ID),
            files={"file": ("shirt.jpg", photo((10, 120, 200)), "image/jpeg")},
        )
        assert response.status_code == 201, response.text
        return str(response.json()["image_key"])

    def test_a_member_cannot_upload_one(
        self, client: TestClient, catalogue: dict[str, UUID]
    ) -> None:
        response = client.post(
            "/admin/rewards/image",
            headers=auth(),
            files={"file": ("shirt.jpg", photo((1, 2, 3)), "image/jpeg")},
        )

        assert response.status_code == 403

    def test_a_photo_reaches_the_member_catalogue_as_a_link(
        self,
        client: TestClient,
        catalogue: dict[str, UUID],
        boss: None,
        storage: FakeImageStorage,
    ) -> None:
        key = self.upload(client)
        assert key.startswith("rewards/")

        patched = client.patch(
            f"/admin/rewards/{catalogue['shirt']}",
            headers=auth(BOSS_CLERK_ID),
            json={"image_key": key},
        )
        assert patched.status_code == 200, patched.text

        body = client.get("/rewards", headers=auth()).json()
        shirt = next(r for r in body[0]["rewards"] if r["name"] == "Shirt")
        cap = next(r for r in body[0]["rewards"] if r["name"] == "Cap")

        assert shirt["image_url"] is not None and key in shirt["image_url"]
        assert cap["image_url"] is None
        assert all(signed.startswith("rewards/") for signed, _ in storage.signed)

    def test_a_reward_cannot_be_pointed_at_someone_elses_evidence(
        self, client: TestClient, catalogue: dict[str, UUID], boss: None
    ) -> None:
        """The whole reason the key is validated: every member is handed a URL for
        whatever a reward names."""
        submit_run(client, "5", (200, 30, 30))
        evidence = client.get("/me/runs", headers=auth()).json()[0]["evidence_url"]
        stolen = evidence.split("?")[0].split("storage.test/")[1]
        assert stolen.startswith("runs/")

        response = client.patch(
            f"/admin/rewards/{catalogue['shirt']}",
            headers=auth(BOSS_CLERK_ID),
            json={"image_key": stolen},
        )

        assert response.status_code == 422
        listed = client.get("/rewards", headers=auth()).json()
        assert all(r["image_url"] is None for r in listed[0]["rewards"])

    def test_a_file_that_is_not_an_image_is_refused(
        self, client: TestClient, boss: None
    ) -> None:
        response = client.post(
            "/admin/rewards/image",
            headers=auth(BOSS_CLERK_ID),
            files={"file": ("x.jpg", b"<?php system($_GET['c']); ?>" + b" " * 200, "image/jpeg")},
        )

        assert response.status_code == 415
