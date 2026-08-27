"""Safe in-memory image validation and backend payload helpers."""

from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from config import (
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_SIZE_MB,
    PASSPORT_PHOTO_MAX_DIMENSION,
    PASSPORT_PHOTO_TARGET_MB,
    PERSONAL_PHOTO_MAX_DIMENSION,
    PERSONAL_PHOTO_TARGET_MB,
)


ALLOWED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
}


def _rgb_image(image: Image.Image) -> Image.Image:
    """Apply phone orientation and flatten transparency on a white background."""

    image = ImageOps.exif_transpose(image)
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image.convert("RGB")


def _compress_for_drive(
    data: bytes,
    target_mb: float,
    max_dimension: int,
) -> tuple[bytes, int, int]:
    """Return a readable, sanitized JPEG small enough for reliable uploads."""

    target_bytes = int(target_mb * 1024 * 1024)
    with Image.open(io.BytesIO(data)) as source:
        image = _rgb_image(source)
        image.thumbnail(
            (max_dimension, max_dimension),
            Image.Resampling.LANCZOS,
        )

    quality_steps = (88, 84, 80, 76, 72, 68)
    encoded = b""
    for quality in quality_steps:
        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
            subsampling=0,
        )
        encoded = buffer.getvalue()
        if len(encoded) <= target_bytes:
            break

    # Very detailed scans may still be large.  Reduce dimensions gradually,
    # never below 1200 px on the longest edge so passport text stays readable.
    while len(encoded) > target_bytes and max(image.size) > 1200:
        scale = max(1200 / max(image.size), 0.88)
        next_size = (
            max(1, int(image.width * scale)),
            max(1, int(image.height * scale)),
        )
        image = image.resize(next_size, Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        image.save(
            buffer,
            format="JPEG",
            quality=72,
            optimize=True,
            progressive=True,
            subsampling=0,
        )
        encoded = buffer.getvalue()

    if len(encoded) > target_bytes:
        raise ValueError(
            "The image could not be compressed safely. Please upload a clearer, smaller photo."
        )
    return encoded, image.width, image.height


def validate_uploaded_image(
    uploaded_file: Any,
    image_kind: str = "passport_photo",
) -> dict[str, Any]:
    """Validate a Streamlit upload and return safe, reusable image bytes."""

    if uploaded_file is None:
        raise ValueError("No image was selected.")

    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    data = uploaded_file.read()
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    max_bytes = MAX_IMAGE_SIZE_MB * 1024 * 1024
    if not data:
        raise ValueError("The selected image is empty.")
    if len(data) > max_bytes:
        raise ValueError(f"The image must be {MAX_IMAGE_SIZE_MB} MB or smaller.")

    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = (image.format or "").upper()
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("The file is not a valid JPG, JPEG or PNG image.") from exc

    if image_format not in ALLOWED_FORMATS:
        raise ValueError("Only JPG, JPEG and PNG images are allowed.")
    if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("The image dimensions are too large or invalid.")

    if image_kind == "personal_photo":
        target_mb = PERSONAL_PHOTO_TARGET_MB
        max_dimension = PERSONAL_PHOTO_MAX_DIMENSION
    else:
        target_mb = PASSPORT_PHOTO_TARGET_MB
        max_dimension = PASSPORT_PHOTO_MAX_DIMENSION
    processed, processed_width, processed_height = _compress_for_drive(
        data,
        target_mb,
        max_dimension,
    )
    try:
        with Image.open(io.BytesIO(processed)) as verified:
            verified.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("The image could not be prepared for upload.") from exc

    return {
        "data": processed,
        "mime_type": "image/jpeg",
        "extension": "jpg",
        "size_bytes": len(processed),
        "original_size_bytes": len(data),
        "width": processed_width,
        "height": processed_height,
    }


def to_backend_image(image: dict[str, Any] | None) -> dict[str, Any] | None:
    if not image:
        return None
    return {
        "base64": base64.b64encode(image["data"]).decode("ascii"),
        "mime_type": image["mime_type"],
        "extension": image["extension"],
    }
