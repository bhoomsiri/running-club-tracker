"""In-memory stand-ins for object storage, metadata stripping, and the AI extractor."""

from __future__ import annotations

from datetime import timedelta

from app.application.ports.run_extractor import RunDraft
from app.domain.errors import EvidenceNotFound


class FakeImageStorage:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.signed: list[tuple[str, timedelta]] = []

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def get(self, key: str) -> bytes:
        try:
            return self.objects[key][0]
        except KeyError:
            raise EvidenceNotFound(key) from None

    def presigned_url(self, key: str, expires_in: timedelta) -> str:
        # Recorded so tests can assert WHICH keys were signed — that is the image IDOR
        # check: a URL must never be minted for a key the caller isn't entitled to.
        self.signed.append((key, expires_in))
        return f"https://storage.test/{key}?expires={int(expires_in.total_seconds())}"


class PassthroughSanitizer:
    """Metadata stripping has its own tests against real EXIF; use-case tests only care
    that the sanitizer is invoked before storing."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def strip_metadata(self, data: bytes, kind: str) -> bytes:
        self.calls.append(kind)
        return b"scrubbed:" + data


class FakeRunExtractor:
    def __init__(self, draft: RunDraft | None = None) -> None:
        self.draft = draft or RunDraft()
        self.calls = 0

    def extract(self, image: bytes, kind: str) -> RunDraft:
        self.calls += 1
        return self.draft
