"""S3ImageStorage against a real S3 server — the same code that runs against R2 in prod.

What matters here is the thing unit tests cannot show: that a presigned URL really is
signed, really does expire, and really is tied to its own key. A fake that returns
whatever it is asked for proves none of that, which is why these run against a server.

What this file deliberately does NOT claim is that the production bucket is closed to
unsigned reads. No local stand-in can speak for R2's configuration — see
`test_the_adapter_never_asks_for_a_public_object` and the weekly `bucket-is-private` job
in ci.yml, which asks R2 itself.
"""

from __future__ import annotations

import contextlib
import inspect
import os
import time
from collections.abc import Iterator
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import boto3
import httpx
import pytest
from botocore.client import Config
from botocore.exceptions import ClientError

from app.adapters.storage.s3_image_storage import MAX_URL_TTL_SECONDS, S3ImageStorage

pytestmark = pytest.mark.integration

BUCKET = "running-club-test"
KEY = "runs/member-1/" + "a" * 64 + ".jpeg"
IMAGE = b"\xff\xd8\xff\xe0" + b"pretend-jpeg" * 20


@pytest.fixture(scope="session")
def s3_endpoint() -> str:
    endpoint = os.environ.get("S3_ENDPOINT_URL", "http://localhost:4566")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "test"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "test"),
        region_name="auto",
        config=Config(signature_version="s3v4", connect_timeout=2, retries={"max_attempts": 1}),
    )
    try:
        client.list_buckets()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"the S3 stand-in is not reachable at {endpoint}: {e}")
    with contextlib.suppress(ClientError):
        client.create_bucket(Bucket=BUCKET)  # already there on a re-run
    return endpoint


@pytest.fixture
def storage(s3_endpoint: str) -> Iterator[S3ImageStorage]:
    yield S3ImageStorage(
        bucket=BUCKET,
        endpoint_url=s3_endpoint,
        access_key=os.environ.get("S3_ACCESS_KEY", "test"),
        secret_key=os.environ.get("S3_SECRET_KEY", "test"),
    )


def test_an_object_round_trips(storage: S3ImageStorage) -> None:
    storage.put(KEY, IMAGE, "image/jpeg")

    assert storage.get(KEY) == IMAGE


def test_the_adapter_never_asks_for_a_public_object(s3_endpoint: str) -> None:
    """What this file can honestly promise about privacy, and what it cannot.

    It used to assert that an unsigned GET to the object is refused. That assertion was
    about the BUCKET'S CONFIGURATION, not about this adapter — and it was being made
    against a local stand-in, which is free to answer however it likes. Both MinIO (the
    old one) and LocalStack and s3mock serve unsigned reads; MinIO happened to refuse
    them, so the test passed and looked like coverage. It would have stayed green through
    a production bucket accidentally made public, because it never asked production
    anything.

    The real check now lives in the weekly `bucket-is-private` job in ci.yml, which
    sends an unsigned request to R2 itself and requires 401 or 403.

    What is left here is the part the adapter genuinely controls, asserted against a real
    server: it never requests a public object, and the only URL it can produce is one
    that expires.
    """
    calls: list[dict[str, object]] = []

    class RecordingClient:
        """Passes everything through, keeping a copy of what was asked for."""

        def __init__(self, inner: object) -> None:
            self._inner = inner

        def __getattr__(self, name: str) -> object:
            attr = getattr(self._inner, name)
            if not callable(attr):
                return attr

            def recorded(*args: object, **kwargs: object) -> object:
                calls.append({"op": name, **kwargs})
                return attr(*args, **kwargs)

            return recorded

    real = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "test"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "test"),
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )
    spied = S3ImageStorage(bucket=BUCKET, client=RecordingClient(real))

    spied.put(KEY, IMAGE, "image/jpeg")

    put = next(c for c in calls if c["op"] == "put_object")
    # The object inherits the bucket's policy because nothing here overrides it. An
    # `ACL` of any value would be the adapter opting an object out of that policy.
    assert "ACL" not in put, f"put_object asked for an ACL: {put.get('ACL')!r}"

    # And the one URL-producing method cannot be called without an expiry: there is no
    # overload, no default, and no second method that returns a permanent link.
    url_methods = [
        name
        for name in dir(S3ImageStorage)
        if not name.startswith("_") and "url" in name.lower()
    ]
    assert url_methods == ["presigned_url"], url_methods
    assert "expires_in" in inspect.signature(S3ImageStorage.presigned_url).parameters

    query = parse_qs(urlparse(spied.presigned_url(KEY, timedelta(minutes=5))).query)
    assert "X-Amz-Expires" in query, "a URL with no expiry is a permanent one"
    assert 0 < int(query["X-Amz-Expires"][0]) <= MAX_URL_TTL_SECONDS


def test_a_presigned_url_works_and_returns_the_image(storage: S3ImageStorage) -> None:
    storage.put(KEY, IMAGE, "image/jpeg")

    url = storage.presigned_url(KEY, timedelta(minutes=5))
    response = httpx.get(url, timeout=5)

    assert response.status_code == 200
    assert response.content == IMAGE


def test_a_presigned_url_stops_working_when_it_expires(storage: S3ImageStorage) -> None:
    """A leaked URL has to go stale on its own — that is the whole reason images are
    served this way instead of from a public bucket."""
    storage.put(KEY, IMAGE, "image/jpeg")
    # Signature expiry has one-second granularity, so a 1s window can lapse before the
    # first request even lands. A few seconds keeps the test about expiry, not timing.
    url = storage.presigned_url(KEY, timedelta(seconds=3))

    assert httpx.get(url, timeout=5).status_code == 200

    time.sleep(4)

    assert httpx.get(url, timeout=5).status_code == 403


def test_a_presigned_url_is_only_good_for_its_own_key(storage: S3ImageStorage) -> None:
    """The signature covers the key, so it cannot be edited to point at someone else's
    image."""
    storage.put(KEY, IMAGE, "image/jpeg")
    other_key = "runs/member-2/" + "b" * 64 + ".jpeg"
    storage.put(other_key, b"\xff\xd8\xff\xe0" + b"someone-elses" * 20, "image/jpeg")

    tampered = storage.presigned_url(KEY, timedelta(minutes=5)).replace("member-1", "member-2")
    response = httpx.get(tampered, timeout=5)

    assert response.status_code == 403
