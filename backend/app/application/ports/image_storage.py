from datetime import timedelta
from typing import Protocol


class ImageStorage(Protocol):
    """Private object storage for evidence images.

    The bucket is never public. Reading an image always goes through a short-lived
    presigned URL minted for a caller who has already been shown to be entitled to it.
    """

    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def get(self, key: str) -> bytes:
        """Read an object back. Callers must already have established entitlement."""
        ...

    def presigned_url(self, key: str, expires_in: timedelta) -> str:
        """A URL that works for a few minutes and then stops. Callers must check
        entitlement BEFORE asking for one — the URL itself is the permission."""
        ...


class ImageSanitizer(Protocol):
    def strip_metadata(self, data: bytes, kind: str) -> bytes:
        """Re-encode the image without any metadata.

        Phone photos and running-app screenshots carry EXIF with GPS coordinates and
        timestamps: storing them as-is would publish where a member lives and runs.
        """
        ...
