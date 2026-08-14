"""EXIF stripping, proved on an image that really carries GPS.

If this ever regresses, the club's bucket starts recording where each member lives.
"""

from __future__ import annotations

import io

import piexif
import pytest
from PIL import Image

from app.adapters.storage.pillow_image_sanitizer import PillowImageSanitizer
from app.domain.errors import InvalidImage


def jpeg_with_gps() -> bytes:
    """A JPEG carrying GPS coordinates and a timestamp, like a phone photo."""
    image = Image.new("RGB", (64, 48), color=(120, 200, 90))
    exif = {
        "0th": {piexif.ImageIFD.Make: b"TestPhone", piexif.ImageIFD.Model: b"Pixel"},
        "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2026:06:01 07:30:00"},
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: ((13, 1), (45, 1), (0, 1)),  # Bangkok
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: ((100, 1), (31, 1), (0, 1)),
        },
        "1st": {},
        "thumbnail": None,
    }
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=piexif.dump(exif))
    return out.getvalue()


def test_the_fixture_really_does_carry_gps() -> None:
    """Otherwise the test below would pass for the wrong reason."""
    exif = piexif.load(jpeg_with_gps())

    assert exif["GPS"], "fixture is not carrying GPS — the strip test would be vacuous"


def test_gps_and_timestamps_are_gone_after_stripping() -> None:
    scrubbed = PillowImageSanitizer().strip_metadata(jpeg_with_gps(), "jpeg")

    exif = piexif.load(scrubbed)
    assert exif["GPS"] == {}
    assert exif["0th"] == {}
    assert exif["Exif"] == {}


def test_the_picture_itself_survives() -> None:
    scrubbed = PillowImageSanitizer().strip_metadata(jpeg_with_gps(), "jpeg")

    with Image.open(io.BytesIO(scrubbed)) as image:
        assert image.size == (64, 48)
        # JPEG is lossy, so the colour is close rather than identical — the point is
        # that the photo is still the photo, not that it is bit-identical.
        pixel = image.getpixel((0, 0))
        assert isinstance(pixel, tuple)
        assert all(abs(a - b) <= 4 for a, b in zip(pixel, (120, 200, 90), strict=True))


def test_png_metadata_is_dropped_too() -> None:
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("Comment", "somchai@example.com ran here")
    original = io.BytesIO()
    Image.new("RGB", (32, 32)).save(original, format="PNG", pnginfo=info)

    scrubbed = PillowImageSanitizer().strip_metadata(original.getvalue(), "png")

    with Image.open(io.BytesIO(scrubbed)) as image:
        assert image.info.get("Comment") is None
    assert b"somchai@example.com" not in scrubbed


def test_stripping_is_deterministic_so_duplicate_detection_works() -> None:
    """The hash of the scrubbed bytes is the image's identity — the same input has to
    produce the same output every time."""
    sanitizer = PillowImageSanitizer()
    source = jpeg_with_gps()

    assert sanitizer.strip_metadata(source, "jpeg") == sanitizer.strip_metadata(source, "jpeg")


def test_a_file_that_cannot_be_decoded_is_refused() -> None:
    with pytest.raises(InvalidImage):
        PillowImageSanitizer().strip_metadata(b"\xff\xd8\xff" + b"garbage" * 40, "jpeg")


def test_a_palette_png_keeps_its_colours() -> None:
    """A "P" image stores colour indices, not colours. Rebuilding from raw bytes without
    converting first would keep the indices and lose the palette — the photo would come
    back in the wrong colours."""
    original = Image.new("RGB", (16, 16), color=(200, 30, 60)).convert(
        "P", palette=Image.Palette.ADAPTIVE
    )
    buffer = io.BytesIO()
    original.save(buffer, format="PNG")

    scrubbed = PillowImageSanitizer().strip_metadata(buffer.getvalue(), "png")

    with Image.open(io.BytesIO(scrubbed)) as image:
        pixel = image.convert("RGB").getpixel((0, 0))
    assert isinstance(pixel, tuple)
    assert all(abs(a - b) <= 4 for a, b in zip(pixel, (200, 30, 60), strict=True))


def test_a_transparent_png_keeps_its_transparency() -> None:
    original = io.BytesIO()
    Image.new("RGBA", (16, 16), color=(0, 0, 0, 0)).save(original, format="PNG")

    scrubbed = PillowImageSanitizer().strip_metadata(original.getvalue(), "png")

    with Image.open(io.BytesIO(scrubbed)) as image:
        assert image.mode == "RGBA"
        assert image.getpixel((0, 0)) == (0, 0, 0, 0)


def test_a_greyscale_jpeg_still_saves() -> None:
    """JPEG has no alpha channel, so the rebuild must land on RGB whatever came in."""
    original = io.BytesIO()
    Image.new("L", (16, 16), color=128).save(original, format="JPEG")

    scrubbed = PillowImageSanitizer().strip_metadata(original.getvalue(), "jpeg")

    with Image.open(io.BytesIO(scrubbed)) as image:
        assert image.size == (16, 16)


def webp_with_exif() -> bytes:
    """A WEBP carrying an EXIF block with GPS, like a phone photo saved as webp."""
    exif = piexif.dump(
        {
            "0th": {piexif.ImageIFD.Make: b"TestPhone"},
            "Exif": {}, "1st": {}, "thumbnail": None,
            "GPS": {
                piexif.GPSIFD.GPSLatitudeRef: b"N",
                piexif.GPSIFD.GPSLatitude: ((13, 1), (45, 1), (0, 1)),
            },
        }
    )
    out = io.BytesIO()
    Image.new("RGB", (32, 32), color=(15, 90, 210)).save(out, format="WEBP", exif=exif)
    return out.getvalue()


def test_the_webp_fixture_really_carries_exif() -> None:
    with Image.open(io.BytesIO(webp_with_exif())) as image:
        assert image.info.get("exif"), "fixture has no EXIF — the strip test would be vacuous"


def test_webp_metadata_is_stripped_too() -> None:
    scrubbed = PillowImageSanitizer().strip_metadata(webp_with_exif(), "webp")

    with Image.open(io.BytesIO(scrubbed)) as image:
        assert not image.info.get("exif")
        assert image.size == (32, 32)
    assert b"TestPhone" not in scrubbed
