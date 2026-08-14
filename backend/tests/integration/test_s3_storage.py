"""S3ImageStorage against a real MinIO — the same code that runs against R2 in prod.

What matters here is the thing unit tests cannot show: that the bucket really is private,
and that a presigned URL really does expire.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from datetime import timedelta

import boto3
import httpx
import pytest
from botocore.client import Config
from botocore.exceptions import ClientError

from app.adapters.storage.s3_image_storage import S3ImageStorage

pytestmark = pytest.mark.integration

BUCKET = "running-club-test"
KEY = "runs/member-1/" + "a" * 64 + ".jpeg"
IMAGE = b"\xff\xd8\xff\xe0" + b"pretend-jpeg" * 20


@pytest.fixture(scope="session")
def s3_endpoint() -> str:
    endpoint = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
        region_name="auto",
        config=Config(signature_version="s3v4", connect_timeout=2, retries={"max_attempts": 1}),
    )
    try:
        client.list_buckets()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"MinIO is not reachable at {endpoint}: {e}")
    with contextlib.suppress(ClientError):
        client.create_bucket(Bucket=BUCKET)  # already there on a re-run
    return endpoint


@pytest.fixture
def storage(s3_endpoint: str) -> Iterator[S3ImageStorage]:
    yield S3ImageStorage(
        bucket=BUCKET,
        endpoint_url=s3_endpoint,
        access_key=os.environ.get("S3_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("S3_SECRET_KEY", "minioadmin"),
    )


def test_an_object_round_trips(storage: S3ImageStorage) -> None:
    storage.put(KEY, IMAGE, "image/jpeg")

    assert storage.get(KEY) == IMAGE


def test_the_bucket_is_private(storage: S3ImageStorage, s3_endpoint: str) -> None:
    """Fetching the object without a signature must fail. If this ever passes, every
    member's evidence photo is on the open internet."""
    storage.put(KEY, IMAGE, "image/jpeg")

    unsigned = httpx.get(f"{s3_endpoint}/{BUCKET}/{KEY}", timeout=5)

    assert unsigned.status_code in (401, 403)


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
