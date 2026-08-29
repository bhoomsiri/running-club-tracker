"""The submission flow over HTTP: upload -> (extract) -> confirm, and who sees images.

Storage and the extractor are the in-memory fakes here — they have their own tests
against real MinIO and real hostile payloads. What this file exercises is the wiring:
the auth gates, the ownership checks, and the status codes.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import piexif
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from app.api import deps
from app.application.ports.run_extractor import RunDraft
from app.config import Settings
from app.main import create_app
from tests.fakes.fake_storage import FakeImageStorage, FakeRunExtractor
from tests.integration.conftest import StubVerifier

pytestmark = pytest.mark.integration

CAMPAIGN = UUID("11111111-1111-1111-1111-111111111111")


def photo_with_gps() -> bytes:
    image = Image.new("RGB", (48, 48), color=(10, 120, 200))
    exif = {
        "0th": {}, "Exif": {}, "1st": {}, "thumbnail": None,
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((13, 1), (45, 1), (0, 1)),
        },
    }
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=piexif.dump(exif))
    return out.getvalue()


@pytest.fixture
def storage() -> FakeImageStorage:
    return FakeImageStorage()


@pytest.fixture
def extractor() -> FakeRunExtractor:
    return FakeRunExtractor(
        RunDraft(
            distance_km=Decimal("5.25"), duration_seconds=1800,
            run_date=date(2026, 6, 1), confidence=Decimal("0.9"), warnings=[],
        )
    )


@pytest.fixture
def runs_client(
    session_factory: sessionmaker[Session],
    settings: Settings,
    storage: FakeImageStorage,
    extractor: FakeRunExtractor,
) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[deps.get_settings_dep] = lambda: settings
    app.dependency_overrides[deps.get_session_factory_dep] = lambda: session_factory
    app.dependency_overrides[deps.get_token_verifier] = StubVerifier
    app.dependency_overrides[deps.get_image_storage] = lambda: storage
    app.dependency_overrides[deps.get_run_extractor] = lambda: extractor
    with TestClient(app) as client:
        yield client


@pytest.fixture
def people(session_factory: sessionmaker[Session]) -> dict[str, UUID]:
    ids = {"alice": uuid4(), "dao": uuid4(), "admin": uuid4()}
    with session_factory() as session:
        # A run has to belong to an active campaign, so these tests need one.
        session.add(
            models.Campaign(
                id=CAMPAIGN, code="100km", name="100 km", type="cumulative_distance",
                starts_on=date(2026, 1, 1), ends_on=date(2026, 12, 31),
                config={"target_km": 100},
            )
        )
        session.add(
            models.Member(id=ids["alice"], clerk_user_id="user_alice", display_name="Alice")
        )
        session.add(models.Member(id=ids["dao"], clerk_user_id="user_dao", display_name="Dao"))
        session.add(
            models.Member(
                id=ids["admin"], clerk_user_id="user_admin", display_name="Admin", role="admin"
            )
        )
        session.commit()
    return ids


def auth(clerk_user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {clerk_user_id}"}


def upload(client: TestClient, who: str, data: bytes | None = None) -> dict[str, str]:
    response = client.post(
        "/runs/evidence",
        headers=auth(who),
        files={"file": ("run.jpg", data or photo_with_gps(), "image/jpeg")},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


class TestUpload:
    def test_uploading_returns_a_key_and_stores_a_scrubbed_image(
        self, runs_client: TestClient, people: dict[str, UUID], storage: FakeImageStorage
    ) -> None:
        body = upload(runs_client, "user_alice")

        assert body["image_key"].startswith(f"runs/{people['alice']}/")
        stored, content_type = storage.objects[body["image_key"]]
        assert content_type == "image/jpeg"
        # The real sanitizer ran: what was stored no longer carries the GPS block.
        assert piexif.load(stored)["GPS"] == {}

    def test_uploading_needs_a_token(self, runs_client: TestClient) -> None:
        response = runs_client.post(
            "/runs/evidence", files={"file": ("run.jpg", photo_with_gps(), "image/jpeg")}
        )

        assert response.status_code == 401

    def test_a_disguised_file_is_415_however_it_is_labelled(
        self, runs_client: TestClient, people: dict[str, UUID], storage: FakeImageStorage
    ) -> None:
        response = runs_client.post(
            "/runs/evidence",
            headers=auth("user_alice"),
            # Claims to be a JPEG in both the filename and the content type.
            files={"file": ("photo.jpg", b"<?php system($_GET['c']); ?>" + b" " * 200,
                            "image/jpeg")},
        )

        assert response.status_code == 415
        assert storage.objects == {}

    def test_an_oversized_upload_is_refused(
        self, runs_client: TestClient, people: dict[str, UUID], storage: FakeImageStorage
    ) -> None:
        too_big = b"\xff\xd8\xff\xe0" + b"\x00" * (10 * 1024 * 1024 + 1)

        response = runs_client.post(
            "/runs/evidence",
            headers=auth("user_alice"),
            files={"file": ("big.jpg", too_big, "image/jpeg")},
        )

        assert response.status_code == 415
        assert storage.objects == {}


class TestExtract:
    def test_extracting_returns_a_draft_and_saves_nothing(
        self, runs_client: TestClient, people: dict[str, UUID],
        session_factory: sessionmaker[Session],
    ) -> None:
        key = upload(runs_client, "user_alice")["image_key"]

        response = runs_client.post(
            "/runs/extract", headers=auth("user_alice"), json={"image_key": key}
        )

        assert response.status_code == 200
        assert response.json()["draft"]["distance_km"] == "5.25"
        assert response.json()["confidence"] == "0.9"
        with session_factory() as session:
            assert session.query(models.RunEntry).count() == 0  # nothing committed

    def test_extracting_from_someone_elses_image_is_403(
        self, runs_client: TestClient, people: dict[str, UUID], extractor: FakeRunExtractor
    ) -> None:
        alice_key = upload(runs_client, "user_alice")["image_key"]

        response = runs_client.post(
            "/runs/extract", headers=auth("user_dao"), json={"image_key": alice_key}
        )

        assert response.status_code == 403
        assert extractor.calls == 0  # the club is not billed for it either


class TestSubmit:
    def submit(self, client: TestClient, who: str, key: str, **overrides: object) -> object:
        body = {
            "distance_km": "5.25",
            "duration_seconds": 1800,
            "run_date": "2026-06-01",
            "image_key": key,
            "source": "app_screenshot",
        }
        body.update(overrides)
        return client.post("/runs", headers=auth(who), json=body)

    def test_a_confirmed_run_is_saved(
        self, runs_client: TestClient, people: dict[str, UUID]
    ) -> None:
        key = upload(runs_client, "user_alice")["image_key"]

        response = self.submit(runs_client, "user_alice", key)

        assert response.status_code == 201  # type: ignore[attr-defined]
        body = response.json()  # type: ignore[attr-defined]
        assert body["distance_km"] == "5.250"
        assert body["review_status"] == "ok"
        assert "evidence_key" not in body  # images are reached only via presigned URLs

    def test_the_optional_counts_survive_the_round_trip(
        self,
        runs_client: TestClient,
        people: dict[str, UUID],
        session_factory: sessionmaker[Session],
    ) -> None:
        """The router builds its command with `**body.model_dump()`, so these two reach
        the use case only by being on the request model. Nothing else asserts that, and
        the submit form has no way of telling whether they arrived."""
        key = upload(runs_client, "user_alice")["image_key"]

        response = self.submit(runs_client, "user_alice", key, calories_burned=420, steps=7200)

        assert response.status_code == 201  # type: ignore[attr-defined]
        with session_factory() as session:
            run = session.query(models.RunEntry).one()
            assert run.calories_burned == 420
            assert run.steps == 7200

    def test_leaving_the_counts_out_stores_nothing_rather_than_zero(
        self,
        runs_client: TestClient,
        people: dict[str, UUID],
        session_factory: sessionmaker[Session],
    ) -> None:
        """A member who skips the boxes has not burned no calories — they have not said.
        A 0 here would be a number on their dashboard they never gave (golden rule #4)."""
        key = upload(runs_client, "user_alice")["image_key"]

        self.submit(runs_client, "user_alice", key)

        with session_factory() as session:
            run = session.query(models.RunEntry).one()
            assert run.calories_burned is None
            assert run.steps is None

    @pytest.mark.parametrize(
        "field,value",
        [
            ("calories_burned", 0),
            ("calories_burned", 10_000),
            ("steps", 0),
            ("steps", 200_000),
            ("steps", -1),
        ],
    )
    def test_a_count_outside_the_bounds_is_refused(
        self, runs_client: TestClient, people: dict[str, UUID], field: str, value: int
    ) -> None:
        """The same exclusive bounds the CHECK constraints hold, rejected at the edge so
        the form's own message and the API's answer cannot disagree about what is valid."""
        key = upload(runs_client, "user_alice")["image_key"]

        response = self.submit(runs_client, "user_alice", key, **{field: value})

        assert response.status_code == 422  # type: ignore[attr-defined]

    def test_submitting_the_same_image_twice_is_409(
        self, runs_client: TestClient, people: dict[str, UUID]
    ) -> None:
        key = upload(runs_client, "user_alice")["image_key"]
        self.submit(runs_client, "user_alice", key)

        second = self.submit(runs_client, "user_alice", key)

        assert second.status_code == 409  # type: ignore[attr-defined]

    def test_attaching_someone_elses_upload_is_403(
        self, runs_client: TestClient, people: dict[str, UUID]
    ) -> None:
        alice_key = upload(runs_client, "user_alice")["image_key"]

        response = self.submit(runs_client, "user_dao", alice_key)

        assert response.status_code == 403  # type: ignore[attr-defined]

    def test_an_impossible_distance_is_422_whatever_the_ai_said(
        self, runs_client: TestClient, people: dict[str, UUID]
    ) -> None:
        key = upload(runs_client, "user_alice")["image_key"]

        response = self.submit(runs_client, "user_alice", key, distance_km="500")

        assert response.status_code == 422  # type: ignore[attr-defined]

    def test_the_same_photo_from_another_member_is_flagged_for_review(
        self, runs_client: TestClient, people: dict[str, UUID]
    ) -> None:
        photo = photo_with_gps()
        alice_key = upload(runs_client, "user_alice", photo)["image_key"]
        self.submit(runs_client, "user_alice", alice_key)
        dao_key = upload(runs_client, "user_dao", photo)["image_key"]

        response = self.submit(runs_client, "user_dao", dao_key)

        assert response.status_code == 201  # type: ignore[attr-defined]
        # Recorded, not refused — a human decides.
        assert response.json()["review_status"] == "flagged"  # type: ignore[attr-defined]


class TestEvidenceAccess:
    def test_a_member_sees_their_own_runs_with_short_lived_urls(
        self, runs_client: TestClient, people: dict[str, UUID], storage: FakeImageStorage
    ) -> None:
        key = upload(runs_client, "user_alice")["image_key"]
        TestSubmit().submit(runs_client, "user_alice", key)

        response = runs_client.get("/me/runs", headers=auth("user_alice"))

        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["evidence_url"].startswith("https://storage.test/")
        assert storage.signed[-1][1].total_seconds() == 300

    def test_another_members_runs_never_appear(
        self, runs_client: TestClient, people: dict[str, UUID], storage: FakeImageStorage
    ) -> None:
        alice_key = upload(runs_client, "user_alice")["image_key"]
        TestSubmit().submit(runs_client, "user_alice", alice_key)

        response = runs_client.get("/me/runs", headers=auth("user_dao"))

        assert response.json() == []
        # No URL was minted for Alice's image on Dao's behalf.
        assert all(str(people["alice"]) not in key for key, _ in storage.signed)

    def test_an_admin_may_see_a_members_runs(
        self, runs_client: TestClient, people: dict[str, UUID]
    ) -> None:
        key = upload(runs_client, "user_alice")["image_key"]
        TestSubmit().submit(runs_client, "user_alice", key)

        response = runs_client.get(
            f"/admin/members/{people['alice']}/runs", headers=auth("user_admin")
        )

        assert response.status_code == 200
        assert len(response.json()) == 1

    def test_an_ordinary_member_may_not_read_another_members_runs(
        self, runs_client: TestClient, people: dict[str, UUID], storage: FakeImageStorage
    ) -> None:
        key = upload(runs_client, "user_alice")["image_key"]
        TestSubmit().submit(runs_client, "user_alice", key)
        signed_before = len(storage.signed)

        response = runs_client.get(
            f"/admin/members/{people['alice']}/runs", headers=auth("user_dao")
        )

        assert response.status_code == 403
        assert len(storage.signed) == signed_before  # refused before any URL was minted
