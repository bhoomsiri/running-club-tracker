"""The origin lock that keeps the raw Cloud Run URL from being a way around Cloudflare.

None of these touch the database: the guard answers from middleware, before routing and
before any dependency is resolved. That is the point — a request at the bare origin must
cost as little as possible.
"""

from __future__ import annotations

import hmac
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.origin_guard import ORIGIN_SECRET_HEADER
from app.config import Settings
from app.main import create_app

SECRET = "an-origin-secret-nobody-can-guess"


def build_client(secret: str) -> Iterator[TestClient]:
    settings = Settings(
        database_url="unused-nothing-here-reaches-the-database",
        frontend_url="https://club.example.com",
        # Shaped like the real thing so the auth dependency can be constructed — the
        # tests below use "401 rather than 403" to mean "got past the guard", and that
        # needs a request to be able to reach the auth dependency and be refused there.
        # No network is touched: a request with no Authorization header is 401 before
        # any JWKS fetch.
        clerk_issuer="https://clerk.example.com",
        clerk_jwks_url="https://clerk.example.com/.well-known/jwks.json",
        cf_origin_secret=secret,
        rate_limit_enabled=False,
    )
    app = create_app(settings)
    # create_app uses these settings for the middleware, but the dependencies read
    # get_settings() — the process-wide one built from the environment. Without this
    # override the auth dependency is constructed from whatever env the test run has,
    # and an empty CLERK_JWKS_URL raises before the 401 these tests are looking for.
    app.dependency_overrides[deps.get_settings_dep] = lambda: settings
    with TestClient(app) as client:
        yield client


@pytest.fixture
def guarded() -> Iterator[TestClient]:
    """Cloudflare in front: the secret is configured, so the guard is on."""
    yield from build_client(SECRET)


@pytest.fixture
def unguarded() -> Iterator[TestClient]:
    """No Cloudflare — local, CI, or a club running without it for now."""
    yield from build_client("")


def test_a_request_without_the_header_is_refused(guarded: TestClient) -> None:
    """This is someone who found the *.run.app URL and called it directly."""
    response = guarded.get("/me/summary")

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}


def test_the_wrong_secret_is_refused(guarded: TestClient) -> None:
    response = guarded.get("/me/summary", headers={ORIGIN_SECRET_HEADER: "not-it"})

    assert response.status_code == 403


def test_a_prefix_of_the_secret_is_refused(guarded: TestClient) -> None:
    """Guessing byte by byte must not get any closer than guessing nothing."""
    response = guarded.get("/me/summary", headers={ORIGIN_SECRET_HEADER: SECRET[:-1]})

    assert response.status_code == 403


def test_the_refusal_says_nothing_about_the_secret(guarded: TestClient) -> None:
    response = guarded.get("/me/summary")

    body = response.text
    assert SECRET not in body
    assert ORIGIN_SECRET_HEADER.lower() not in body.lower()


def test_the_right_secret_passes_through(guarded: TestClient) -> None:
    """Checked on a GUARDED path, not an exempt one.

    /healthz answers 200 whatever the header says, so asserting 200 there would pass
    against a guard that refused everything. 401 is the proof: past the middleware,
    refused by the auth dependency for a different reason entirely.
    """
    response = guarded.get("/me/summary", headers={ORIGIN_SECRET_HEADER: SECRET})

    assert response.status_code == 401


def test_the_header_name_is_matched_case_insensitively(guarded: TestClient) -> None:
    """Whatever casing Cloudflare's transform rule ends up sending."""
    response = guarded.get("/me/summary", headers={"cf-origin-secret": SECRET})

    assert response.status_code == 401


def test_healthz_answers_without_the_header(guarded: TestClient) -> None:
    """Cloud Run's probe reaches the container directly and can never carry it. If this
    regresses, every deploy fails its health check."""
    assert guarded.get("/healthz").status_code == 200


def test_livez_answers_without_the_header(guarded: TestClient) -> None:
    """The externally reachable half of the pair: Google's frontend reserves /healthz on
    *.run.app and never forwards it, so an uptime monitor watching the origin has only
    this one — and it must not need the shared secret to use it."""
    response = guarded.get("/livez")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_livez_says_nothing_beyond_ok(guarded: TestClient) -> None:
    """It answers unauthenticated to the whole internet, so it must stay a constant —
    no version, no config, nothing about what is behind it."""
    assert guarded.get("/livez").json() == {"status": "ok"}


def test_livez_and_healthz_answer_identically(unguarded: TestClient) -> None:
    assert unguarded.get("/livez").json() == unguarded.get("/healthz").json()


def test_the_webhook_endpoint_is_not_exempt(guarded: TestClient) -> None:
    """Clerk's webhooks arrive through the club's domain like everything else, so they
    carry the header too — and this is the one public POST in the API."""
    response = guarded.post("/webhooks/clerk", content=b"{}")

    assert response.status_code == 403


def test_a_non_ascii_header_is_refused_rather_than_crashing(guarded: TestClient) -> None:
    """`hmac.compare_digest` raises TypeError on non-ASCII str, which would turn a guess
    anybody can make into a 500 at the one place that must only ever say 403.

    Sent as raw bytes because that is the only way it can arrive: HTTP headers are bytes
    on the wire, Starlette decodes them latin-1, and no client will encode a str like
    this for you.
    """
    response = guarded.get("/me/summary", headers={ORIGIN_SECRET_HEADER: b"caf\xe9"})

    assert response.status_code == 403


class TestRotation:
    """Several accepted secrets at once, so the value can be changed without a window
    where every request is refused.

    There is no instant at which Cloudflare and Cloud Run both change. Overlapping the
    old and new values is what removes the gap: accept both, move Cloudflare, drop the
    old one.
    """

    OLD, NEW = "the-secret-being-retired", "the-secret-taking-over"

    def rotating(self, configured: str) -> Iterator[TestClient]:
        yield from build_client(configured)

    def test_both_values_are_accepted_during_the_overlap(self) -> None:
        """401, not 200: a guarded path, so passing the guard is what is being measured.
        An exempt path would answer 200 even to a guard that refused everything."""
        for secret in (self.OLD, self.NEW):
            with next(self.rotating(f"{self.OLD},{self.NEW}")) as client:
                response = client.get(
                    "/me/summary", headers={ORIGIN_SECRET_HEADER: secret}
                )

            assert response.status_code == 401, secret

    def test_a_third_value_is_still_refused(self) -> None:
        """Widening the guard must not weaken it."""
        with next(self.rotating(f"{self.OLD},{self.NEW}")) as client:
            response = client.get(
                "/me/summary", headers={ORIGIN_SECRET_HEADER: "neither-of-them"}
            )

        assert response.status_code == 403

    def test_the_old_value_stops_working_once_it_is_removed(self) -> None:
        """The end of the rotation: step three actually retires it."""
        with next(self.rotating(self.NEW)) as client:
            refused = client.get("/me/summary", headers={ORIGIN_SECRET_HEADER: self.OLD})
            accepted = client.get("/me/summary", headers={ORIGIN_SECRET_HEADER: self.NEW})

        assert refused.status_code == 403
        assert accepted.status_code == 401

    def test_spaces_around_the_values_are_ignored(self) -> None:
        """These are pasted into a console field, where a space either side is
        invisible and would otherwise refuse every request."""
        with next(self.rotating(f"  {self.OLD} , {self.NEW}  ")) as client:
            response = client.get("/me/summary", headers={ORIGIN_SECRET_HEADER: self.NEW})

        assert response.status_code == 401

    def test_a_blank_between_commas_is_not_an_accepted_secret(self) -> None:
        """What a half-finished edit looks like. If the empty string were kept, a
        request with no header at all would match it and walk straight through."""
        with next(self.rotating(f"{self.OLD},,{self.NEW}")) as client:
            no_header = client.get("/me/summary")
            empty_header = client.get("/me/summary", headers={ORIGIN_SECRET_HEADER: ""})

        assert no_header.status_code == 403
        assert empty_header.status_code == 403

    def test_every_secret_is_compared_even_after_one_matches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The timing property, asserted rather than assumed.

        A loop that stopped at the first match would return sooner for a caller hitting
        the first secret than the second, which leaks which one they hit and roughly how
        many are configured. Counting the comparisons is the observable form of "does not
        short-circuit" — the wall-clock difference is too small to assert on directly.
        """
        calls: list[bytes] = []
        # Captured BEFORE the patch. `app.api.origin_guard.hmac` is the stdlib module
        # itself, so patching that attribute replaces it everywhere — including inside
        # this function, which would then call itself.
        real = hmac.compare_digest

        def counting(a: bytes, b: bytes) -> bool:
            calls.append(b)
            return bool(real(a, b))

        monkeypatch.setattr("app.api.origin_guard.hmac.compare_digest", counting)

        with next(self.rotating(f"{self.OLD},{self.NEW}")) as client:
            # The FIRST secret matches, so an early exit would show up as one call.
            # A guarded path, because an exempt one returns before comparing anything.
            client.get("/me/summary", headers={ORIGIN_SECRET_HEADER: self.OLD})

        assert calls == [self.OLD.encode(), self.NEW.encode()]

    def test_a_setting_with_no_usable_value_fails_at_startup(self) -> None:
        """Rather than installing a guard that can accept nothing and refusing the whole
        API until somebody works out why."""
        with pytest.raises(ValueError, match="no usable value"):
            next(build_client(" , "))


def test_with_no_secret_configured_the_guard_is_off(unguarded: TestClient) -> None:
    """Local development and CI must not need a Cloudflare header to call the API."""
    assert unguarded.get("/healthz").status_code == 200


def test_with_no_secret_configured_a_stray_header_changes_nothing(
    unguarded: TestClient,
) -> None:
    response = unguarded.get("/healthz", headers={ORIGIN_SECRET_HEADER: "anything"})

    assert response.status_code == 200
