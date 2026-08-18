"""Profile, screening and the onboarding gate, over HTTP against a real database."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.persistence import models
from app.domain.screening import QUESTION_KEYS
from tests.integration.conftest import BOSS_CLERK_ID

pytestmark = pytest.mark.integration

ALICE = "user_alice"

SCREENED_ON = "2026-08-01"

PROFILE = {
    "full_name_th": "สมชาย ใจดี",
    "birth_date": "1990-05-20",
    "sex": "male",
    "position": "พยาบาลวิชาชีพชำนาญการ",
    "department": "กลุ่มงานการพยาบาล",
    "shirt_size": "2XL",
    "phone": "081-234-5678",
    "emergency_contact_name": "สมหญิง ใจดี",
    "emergency_contact_phone": "0898765432",
}


@pytest.fixture
def boss(session_factory: sessionmaker[Session]) -> None:
    """The superuser is seeded rather than provisioned just in time, because JIT makes
    an ordinary member — the role only ever comes from the verified webhook or the
    bootstrap setting."""
    with session_factory() as session:
        session.add(
            models.Member(
                id=uuid4(),
                clerk_user_id=BOSS_CLERK_ID,
                display_name="Boss",
                role="superuser",
            )
        )
        session.commit()


def auth(clerk_user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {clerk_user_id}"}


def answers(**overrides: bool) -> dict[str, bool]:
    complete = dict.fromkeys(QUESTION_KEYS, False)
    complete.update(overrides)
    return complete


class TestProfile:
    def test_a_new_member_has_an_empty_profile(self, client: TestClient) -> None:
        body = client.get("/me/profile", headers=auth(ALICE)).json()

        assert body["complete"] is False
        assert body["full_name_th"] is None

    def test_it_can_be_filled_in_and_read_back(self, client: TestClient) -> None:
        response = client.patch("/me/profile", headers=auth(ALICE), json=PROFILE)

        assert response.status_code == 200
        assert response.json()["complete"] is True
        # Normalised on the way in, so one number has one form in the database.
        assert response.json()["phone"] == "0812345678"
        assert client.get("/me/profile", headers=auth(ALICE)).json()["full_name_th"] == (
            "สมชาย ใจดี"
        )

    def test_the_shirt_size_round_trips(self, client: TestClient) -> None:
        """It is read straight off this response when the shirts are ordered, so it has
        to come back exactly as it went in — "2XL", not "XL2" or the enum's name."""
        response = client.patch("/me/profile", headers=auth(ALICE), json=PROFILE)

        assert response.json()["shirt_size"] == "2XL"
        assert client.get("/me/profile", headers=auth(ALICE)).json()["shirt_size"] == "2XL"

    def test_a_size_outside_the_list_is_refused(self, client: TestClient) -> None:
        """The set is closed on purpose: the club prints one run of shirts, and a size
        nobody stocks is discovered at the printer rather than here."""
        response = client.patch(
            "/me/profile", headers=auth(ALICE), json={**PROFILE, "shirt_size": "XXL"}
        )

        assert response.status_code == 422

    def test_a_bad_value_is_422_and_changes_nothing(self, client: TestClient) -> None:
        client.patch("/me/profile", headers=auth(ALICE), json=PROFILE)

        response = client.patch(
            "/me/profile", headers=auth(ALICE), json={**PROFILE, "phone": "999"}
        )

        assert response.status_code == 422
        assert client.get("/me/profile", headers=auth(ALICE)).json()["phone"] == (
            "0812345678"
        )

    def test_a_member_cannot_promote_themselves_through_it(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        """`role` is written by the verified webhook or the bootstrap setting only. The
        DTO has no such field, and an extra key in the body is ignored rather than
        applied."""
        client.patch(
            "/me/profile", headers=auth(ALICE), json={**PROFILE, "role": "superuser"}
        )

        with session_factory() as session:
            alice = (
                session.query(models.Member).filter_by(clerk_user_id=ALICE).one()
            )
        assert alice.role == "member"

    def test_the_profile_is_the_callers_own(self, client: TestClient) -> None:
        """There is no member_id on the route or in the body, so one member's request
        cannot reach another's row."""
        client.patch("/me/profile", headers=auth(ALICE), json=PROFILE)

        other = client.get("/me/profile", headers=auth("user_somchai")).json()

        assert other["full_name_th"] is None

    def test_the_admin_member_list_does_not_carry_the_sensitive_fields(
        self, client: TestClient, boss: None
    ) -> None:
        """sex and the emergency contact are held for safety, not for browsing. Until
        there is an audited admin path for them, no admin endpoint may return them —
        this is the test that stops one appearing by accident."""
        client.patch("/me/profile", headers=auth(ALICE), json=PROFILE)

        listed = client.get("/admin/members", headers=auth(BOSS_CLERK_ID)).json()

        assert listed, "the boss should see members"
        for member in listed:
            assert "sex" not in member
            assert "emergency_contact_name" not in member
            assert "emergency_contact_phone" not in member
            assert "phone" not in member
            assert "birth_date" not in member

        # The other side of the same line: a job title and a unit are ordinary personal
        # data, so they are here on purpose. Pinning it means a later change that moves
        # them into the sensitive class has to come past this test.
        alice = next(m for m in listed if m["name"] == "สมชาย ใจดี")
        assert alice["department"] == "กลุ่มงานการพยาบาล"
        assert alice["position"] == "พยาบาลวิชาชีพชำนาญการ"


class TestScreening:
    def grant(self, client: TestClient) -> None:
        assert client.post("/consent", headers=auth(ALICE)).status_code == 201

    def test_an_unscreened_member_gets_null(self, client: TestClient) -> None:
        assert client.get("/screening", headers=auth(ALICE)).json() is None

    def test_it_needs_consent(self, client: TestClient) -> None:
        """Sensitive personal data: without a lawful basis the club may not hold it,
        whatever the client does."""
        response = client.post(
            "/screening",
            headers=auth(ALICE),
            json={
                "answers": answers(),
                "risk_acknowledged": True,
                "screened_on": SCREENED_ON,
            },
        )

        assert response.status_code == 403

    def test_with_consent_it_saves_and_reads_back(self, client: TestClient) -> None:
        self.grant(client)

        response = client.post(
            "/screening",
            headers=auth(ALICE),
            json={
                "answers": answers(diabetes=True),
                "risk_acknowledged": True,
                "screened_on": SCREENED_ON,
            },
        )

        assert response.status_code == 200
        assert response.json()["needs_medical_advice"] is True
        assert client.get("/screening", headers=auth(ALICE)).json()["version"] == (
            "parq-plus-th-v1"
        )

    def test_an_incomplete_answer_set_is_422(self, client: TestClient) -> None:
        self.grant(client)
        partial = answers()
        del partial["heart_condition"]

        response = client.post(
            "/screening",
            headers=auth(ALICE),
            json={
                "answers": partial,
                "risk_acknowledged": True,
                "screened_on": SCREENED_ON,
            },
        )

        assert response.status_code == 422

    def test_answering_again_replaces_the_one_record(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        self.grant(client)
        body = {
            "answers": answers(),
            "risk_acknowledged": True,
            "screened_on": SCREENED_ON,
        }
        client.post("/screening", headers=auth(ALICE), json=body)

        client.post(
            "/screening",
            headers=auth(ALICE),
            json={**body, "answers": answers(asthma_or_lung_disease=True)},
        )

        with session_factory() as session:
            assert session.query(models.Screening).count() == 1
        assert (
            client.get("/screening", headers=auth(ALICE)).json()["needs_medical_advice"]
            is True
        )

    def test_one_member_never_sees_anothers_screening(self, client: TestClient) -> None:
        self.grant(client)
        client.post(
            "/screening",
            headers=auth(ALICE),
            json={
                "answers": answers(),
                "risk_acknowledged": True,
                "screened_on": SCREENED_ON,
            },
        )

        assert client.get("/screening", headers=auth("user_somchai")).json() is None


class TestOnboardingStatus:
    def test_a_new_member_is_missing_all_four_steps(self, client: TestClient) -> None:
        body = client.get("/me/onboarding", headers=auth(ALICE)).json()

        assert body["complete"] is False
        assert body["missing"] == ["consent", "profile", "screening", "baseline"]

    def test_each_step_drops_off_as_it_is_done(self, client: TestClient) -> None:
        client.post("/consent", headers=auth(ALICE))
        assert "consent" not in _missing(client)

        client.patch("/me/profile", headers=auth(ALICE), json=PROFILE)
        assert "profile" not in _missing(client)

        client.post(
            "/screening",
            headers=auth(ALICE),
            json={
                "answers": answers(),
                "risk_acknowledged": True,
                "screened_on": SCREENED_ON,
            },
        )
        assert _missing(client) == ["baseline"]

    def test_the_superuser_is_exempt(self, client: TestClient, boss: None) -> None:
        """A fresh deployment has to be reachable by whoever is there to configure it."""
        body = client.get("/me/onboarding", headers=auth(BOSS_CLERK_ID)).json()

        assert body["complete"] is True
        assert body["missing"] == []

    def test_it_needs_a_token(self, client: TestClient) -> None:
        assert client.get("/me/onboarding").status_code == 401


def _missing(client: TestClient) -> list[str]:
    body: dict[str, list[str]] = client.get("/me/onboarding", headers=auth(ALICE)).json()
    return body["missing"]
