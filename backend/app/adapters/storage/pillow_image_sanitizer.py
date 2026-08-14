"""Strip every trace of metadata from an image before it is stored.

A running-app screenshot or a phone photo carries EXIF: GPS coordinates, the exact
timestamp, the device. Storing that would mean the club's bucket quietly records where
each member lives and which streets they run on — a location leak that no amount of
access control later can undo.

The image is rebuilt pixel-by-pixel into a fresh object rather than saved with EXIF
removed, because "save without exif" leaves other metadata blocks (XMP, IPTC, ICC
comments) in place depending on the format.
"""

from __future__ import annotations

import io

from PIL import Image

from app.domain.errors import InvalidImage

# Pillow decodes an enormous image into memory before we can react; this cap turns a
# decompression bomb into a rejection instead of an outage.
Image.MAX_IMAGE_PIXELS = 50_000_000


class PillowImageSanitizer:
    def strip_metadata(self, data: bytes, kind: str) -> bytes:
        try:
            with Image.open(io.BytesIO(data)) as source:
                source.load()
                # Convert to a plain pixel mode FIRST. A palette ("P") image's colours
                # live in the palette, not in the pixel bytes, so rebuilding from
                # tobytes() without converting would keep the indices and lose the
                # colours — the photo would come out wrong.
                converted = source.convert(_target_mode(source, kind))
                # Rebuilt from raw pixels into a brand-new image: the replacement has no
                # `info` dict at all, so nothing can survive by being in a metadata block
                # we didn't think to clear.
                clean = Image.frombytes(converted.mode, converted.size, converted.tobytes())

                out = io.BytesIO()
                clean.save(out, format=kind.upper())
                return out.getvalue()
        except InvalidImage:
            raise
        except Exception as e:
            # A file that passed the magic-byte check but cannot be decoded is either
            # corrupt or crafted. Either way it is not stored.
            raise InvalidImage("image could not be processed") from e


def _target_mode(image: Image.Image, kind: str) -> str:
    """RGBA when the image has transparency worth keeping, RGB otherwise.

    JPEG has no alpha channel at all, so it is always RGB — asking Pillow to save RGBA
    as JPEG raises rather than silently flattening.
    """
    if kind.lower() in ("jpeg", "jpg"):
        return "RGB"
    has_alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    return "RGBA" if has_alpha else "RGB"
