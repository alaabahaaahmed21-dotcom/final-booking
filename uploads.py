"""Safe in-memory image validation and backend payload helpers."""

from __future__ import annotations

import base64
import io
from typing import Any

from PIL import Image, UnidentifiedImageError

from config import MAX_IMAGE_PIXELS, MAX_IMAGE_SIZE_MB


ALLOWED_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
}


def validate_uploaded_image(uploaded_file: Any) -> dict[str, Any]:
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

    mime_type, extension = ALLOWED_FORMATS[image_format]
    return {
        "data": data,
        "mime_type": mime_type,
        "extension": extension,
        "size_bytes": len(data),
        "width": width,
        "height": height,
    }


def to_backend_image(image: dict[str, Any] | None) -> dict[str, Any] | None:
    if not image:
        return None
    return {
        "base64": base64.b64encode(image["data"]).decode("ascii"),
        "mime_type": image["mime_type"],
        "extension": image["extension"],
    }
