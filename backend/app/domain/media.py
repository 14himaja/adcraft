from dataclasses import dataclass
from io import BytesIO

from PIL import Image, UnidentifiedImageError

from app.domain.rules import (
    IMAGE_FORMATS,
    IMAGE_MAX_BYTES,
    IMAGE_MIN_WIDTH,
    IMAGE_RATIO_MAX,
    IMAGE_RATIO_MIN,
)


class ImageRejected(ValueError):
    pass


@dataclass(frozen=True)
class ImageInfo:
    width: int
    height: int
    format: str


def check_instagram_image(data: bytes) -> ImageInfo:
    if len(data) > IMAGE_MAX_BYTES:
        raise ImageRejected(f"Image is larger than {IMAGE_MAX_BYTES // (1024 * 1024)} MB")
    try:
        with Image.open(BytesIO(data)) as img:
            width, height, fmt = img.width, img.height, img.format
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageRejected("File is not a valid image") from exc
    if fmt not in IMAGE_FORMATS:
        raise ImageRejected("Image must be JPEG or PNG")
    if width < IMAGE_MIN_WIDTH:
        raise ImageRejected(f"Image must be at least {IMAGE_MIN_WIDTH} px wide (1080 px recommended)")
    if not IMAGE_RATIO_MIN <= width / height <= IMAGE_RATIO_MAX:
        raise ImageRejected(
            "Image aspect ratio must be between 4:5 (portrait) and 1.91:1 (landscape); "
            "1:1 or 4:5 is recommended"
        )
    return ImageInfo(width, height, fmt)
