"""Accept an evidence image: check it, scrub it, store it.

Order matters and is not negotiable:

  1. **validate** from the magic bytes and the size, before anything touches the file;
  2. **strip metadata**, so no GPS coordinate ever reaches the bucket;
  3. hash the *scrubbed* bytes — that hash is the identity used for duplicate detection,
     so two uploads of the same photo match even if their EXIF differed;
  4. store under a key derived from the member and the hash, never the uploaded filename.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from app.application.ports.image_storage import ImageSanitizer, ImageStorage
from app.domain.evidence import ImageKind, detect_image_kind, evidence_key


@dataclass(frozen=True)
class UploadEvidenceCommand:
    member_id: UUID  # from the verified token
    data: bytes


@dataclass(frozen=True)
class StoredEvidence:
    image_key: str
    sha256: str
    kind: ImageKind


class UploadEvidence:
    def __init__(self, storage: ImageStorage, sanitizer: ImageSanitizer) -> None:
        self._storage = storage
        self._sanitizer = sanitizer

    def execute(self, cmd: UploadEvidenceCommand) -> StoredEvidence:
        kind = detect_image_kind(cmd.data)
        scrubbed = self._sanitizer.strip_metadata(cmd.data, kind.value)

        digest = hashlib.sha256(scrubbed).hexdigest()
        key = evidence_key(str(cmd.member_id), digest, kind)
        self._storage.put(key, scrubbed, kind.content_type)

        return StoredEvidence(image_key=key, sha256=digest, kind=kind)
