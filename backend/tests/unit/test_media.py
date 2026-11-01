from io import BytesIO

import pytest
from PIL import Image

from app.domain.media import ImageRejected, check_instagram_image
from app.domain.rules import IMAGE_MAX_BYTES


def image_bytes(width: int, height: int, fmt: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, fmt)
    return buffer.getvalue()


def test_square_image_is_accepted():
    info = check_instagram_image(image_bytes(1080, 1080))
    assert (info.width, info.height, info.format) == (1080, 1080, "PNG")


def test_portrait_4_5_jpeg_is_accepted():
    assert check_instagram_image(image_bytes(1080, 1350, "JPEG")).format == "JPEG"


def test_landscape_1_91_is_accepted():
    check_instagram_image(image_bytes(1146, 600))


def test_story_shaped_image_is_rejected():
    with pytest.raises(ImageRejected, match="aspect ratio"):
        check_instagram_image(image_bytes(1080, 1920))


def test_narrow_image_is_rejected():
    with pytest.raises(ImageRejected, match="600"):
        check_instagram_image(image_bytes(500, 500))


def test_gif_is_rejected():
    with pytest.raises(ImageRejected, match="JPEG or PNG"):
        check_instagram_image(image_bytes(800, 800, "GIF"))


def test_non_image_is_rejected():
    with pytest.raises(ImageRejected, match="not a valid image"):
        check_instagram_image(b"hello")


def test_oversized_file_is_rejected_before_decoding():
    with pytest.raises(ImageRejected, match="larger than"):
        check_instagram_image(b"x" * (IMAGE_MAX_BYTES + 1))
