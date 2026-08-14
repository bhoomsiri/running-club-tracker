"""Upload filtering, tested against real bytes rather than filenames."""

from __future__ import annotations

import pytest

from app.domain.errors import InvalidImage
from app.domain.evidence import (
    MAX_IMAGE_BYTES,
    ImageKind,
    detect_image_kind,
    digest_from_key,
    evidence_key,
    is_owned_by,
)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 200
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 200
DIGEST = "a" * 64


class TestDetection:
    @pytest.mark.parametrize(
        ("data", "expected"),
        [(JPEG, ImageKind.JPEG), (PNG, ImageKind.PNG), (WEBP, ImageKind.WEBP)],
    )
    def test_the_three_accepted_formats(self, data: bytes, expected: ImageKind) -> None:
        assert detect_image_kind(data) is expected

    def test_a_php_script_renamed_to_jpg_is_still_refused(self) -> None:
        """The filename is a claim; the bytes are the truth."""
        with pytest.raises(InvalidImage):
            detect_image_kind(b"<?php system($_GET['c']); ?>" + b" " * 200)

    def test_svg_is_refused_even_though_it_is_an_image(self) -> None:
        # SVG can carry script — it is not in the whitelist.
        with pytest.raises(InvalidImage):
            detect_image_kind(b"<svg xmlns='http://www.w3.org/2000/svg'>" + b" " * 200)

    def test_a_gif_is_refused(self) -> None:
        with pytest.raises(InvalidImage):
            detect_image_kind(b"GIF89a" + b"\x00" * 200)

    def test_an_oversized_file_is_refused(self) -> None:
        with pytest.raises(InvalidImage, match="limit"):
            detect_image_kind(JPEG + b"\x00" * MAX_IMAGE_BYTES)

    def test_a_file_at_the_limit_is_accepted(self) -> None:
        at_limit = JPEG + b"\x00" * (MAX_IMAGE_BYTES - len(JPEG))

        assert detect_image_kind(at_limit) is ImageKind.JPEG

    def test_an_empty_file_is_refused(self) -> None:
        with pytest.raises(InvalidImage):
            detect_image_kind(b"")

    def test_a_jpeg_header_alone_is_too_small_to_be_real(self) -> None:
        with pytest.raises(InvalidImage):
            detect_image_kind(b"\xff\xd8\xff")

    def test_content_types_are_the_whitelisted_three(self) -> None:
        assert {k.content_type for k in ImageKind} == {
            "image/jpeg",
            "image/png",
            "image/webp",
        }


class TestKeys:
    def test_the_key_contains_the_member_and_the_hash_not_the_filename(self) -> None:
        key = evidence_key("member-1", DIGEST, ImageKind.JPEG)

        assert key == f"runs/member-1/{DIGEST}.jpeg"

    def test_ownership_is_readable_from_the_key(self) -> None:
        key = evidence_key("member-1", DIGEST, ImageKind.PNG)

        assert is_owned_by(key, "member-1") is True
        assert is_owned_by(key, "member-2") is False

    def test_a_key_pointing_at_another_member_is_not_owned(self) -> None:
        assert is_owned_by(f"runs/victim/{DIGEST}.jpeg", "attacker") is False

    def test_traversal_style_keys_are_not_owned(self) -> None:
        assert is_owned_by(f"../runs/victim/{DIGEST}.jpeg", "attacker") is False

    def test_the_digest_comes_back_out_of_the_key(self) -> None:
        assert digest_from_key(f"runs/m/{DIGEST}.jpeg") == DIGEST

    @pytest.mark.parametrize(
        "bad",
        ["runs/m/short.jpeg", "runs/m/.jpeg", "nonsense", f"runs/m/{'z' * 64}.jpeg"],
    )
    def test_a_malformed_key_yields_no_digest(self, bad: str) -> None:
        with pytest.raises(InvalidImage):
            digest_from_key(bad)
