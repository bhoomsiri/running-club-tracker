"""Rules about the evidence image itself.

Deliberately stdlib-only, so the decision "is this an acceptable image?" is a pure
function with no Pillow, no boto3, and no framework anywhere near it — and can be tested
against real bytes.

The check is on the CONTENT, not the filename. An extension is a claim the uploader
makes; magic bytes are what the file actually is. Accepting `evil.php` renamed to
`photo.jpg` is how upload endpoints become remote code execution.
"""

from __future__ import annotations

from enum import StrEnum

from app.domain.errors import InvalidImage

MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB — a phone screenshot is far below this
MIN_IMAGE_BYTES = 100  # anything smaller cannot be a real image


class ImageKind(StrEnum):
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"

    @property
    def content_type(self) -> str:
        return f"image/{self.value}"


def detect_image_kind(data: bytes) -> ImageKind:
    """Identify the image from its magic bytes, or reject it.

    Only jpeg/png/webp are allowed — the three formats a member's phone actually
    produces. Everything else, including formats that can carry active content like
    SVG, is refused.
    """
    if len(data) < MIN_IMAGE_BYTES:
        raise InvalidImage("file is too small to be an image")
    if len(data) > MAX_IMAGE_BYTES:
        raise InvalidImage(f"file exceeds the {MAX_IMAGE_BYTES // (1024 * 1024)} MB limit")

    if data[:3] == b"\xff\xd8\xff":
        return ImageKind.JPEG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ImageKind.PNG
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ImageKind.WEBP

    raise InvalidImage("unsupported image type: only jpeg, png and webp are accepted")


def evidence_key(member_id: str, digest: str, kind: ImageKind) -> str:
    """Where the object lives in the bucket.

    Includes the member id so objects are easy to scope and purge per member, and the
    content hash so the same image is the same object. Never the original filename —
    that is attacker-controlled text.
    """
    return f"runs/{member_id}/{digest}.{kind.value}"


def is_owned_by(key: str, member_id: str) -> bool:
    """Does this object key belong to this member?

    The member id is baked into the key, so ownership is checkable without a database
    round trip — and a caller passing somebody else's key gets nowhere.
    """
    return key.startswith(f"runs/{member_id}/")


def digest_from_key(key: str) -> str:
    """The content hash the key was built from.

    Taken from the key rather than accepted from the client: the hash decides duplicate
    detection, so letting a caller send their own would let them dodge it.
    """
    try:
        filename = key.rsplit("/", 1)[1]
        digest = filename.rsplit(".", 1)[0]
    except IndexError:
        raise InvalidImage("malformed evidence key") from None
    if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
        raise InvalidImage("malformed evidence key")
    return digest
