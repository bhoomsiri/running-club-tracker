"""Accept a catalogue photo for a reward: check it, scrub it, store it.

The same three steps as an evidence upload, in the same order and for the same reasons —
identify the file from its magic bytes, strip its metadata, then store it under a key
derived from the content hash rather than the uploaded filename.

Two things differ. The object goes to the `rewards/` namespace, so it is never mistaken
for a member's evidence; and only the superuser may put one there, because this writes
to storage the club pays for and the result is shown to every member.

Storing the object does not attach it to anything. The returned key becomes a reward's
`image_key` through CreateReward or UpdateReward, which is where the audit row is
written — one act, one record.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from uuid import UUID

from app.application.ports.image_storage import ImageSanitizer, ImageStorage
from app.application.ports.member_repository import MemberRepository
from app.domain.entities import MemberRole
from app.domain.errors import MemberNotFound, NotAuthorized
from app.domain.evidence import ImageKind, detect_image_kind, reward_image_key


@dataclass(frozen=True)
class UploadRewardImageCommand:
    actor_id: UUID  # from the verified token
    data: bytes


@dataclass(frozen=True)
class StoredRewardImage:
    image_key: str
    kind: ImageKind


class UploadRewardImage:
    def __init__(
        self,
        members: MemberRepository,
        storage: ImageStorage,
        sanitizer: ImageSanitizer,
    ) -> None:
        self._members = members
        self._storage = storage
        self._sanitizer = sanitizer

    def execute(self, cmd: UploadRewardImageCommand) -> StoredRewardImage:
        # Checked here as well as at the router: the router gate is convenience, this is
        # the control.
        actor = self._members.get(cmd.actor_id)
        if actor is None:
            raise MemberNotFound(str(cmd.actor_id))
        if actor.role is not MemberRole.SUPERUSER:
            raise NotAuthorized("superuser only")

        kind = detect_image_kind(cmd.data)
        # A product photo carries EXIF too, and the club's own phone is as likely to
        # geotag as a member's.
        scrubbed = self._sanitizer.strip_metadata(cmd.data, kind.value)

        key = reward_image_key(hashlib.sha256(scrubbed).hexdigest(), kind)
        self._storage.put(key, scrubbed, kind.content_type)

        return StoredRewardImage(image_key=key, kind=kind)
