"""Clipboard screenshot capture and in-memory multimodal analysis.

Zero disk I/O: the bitmap is read from the Windows clipboard, resized in RAM,
JPEG-encoded into a BytesIO buffer, and sent to the active LLM provider.
"""

from __future__ import annotations

import base64
import io
import sys

DEFAULT_INSTRUCTION = "Explain what is shown in this image"
MAX_IMAGE_DIM = 1920
JPEG_QUALITY = 85
NO_IMAGE_ERROR = (
    "Error: No image found on the clipboard. "
    "Use Win+Shift+S or PrtScn to snip an area first."
)


def _resample_filter(image_mod: object) -> int:
    resampling = getattr(image_mod, "Resampling", None)
    if resampling is not None:
        return int(resampling.LANCZOS)
    return int(getattr(image_mod, "LANCZOS"))


def _normalize_and_encode(img: object) -> str:
    """Convert to RGB JPEG in RAM and return a UTF-8 base64 string."""
    from PIL import Image

    if not isinstance(img, Image.Image):
        raise TypeError("clipboard payload is not a PIL Image")

    working = img
    converted = None
    if img.mode in ("RGBA", "P") or img.mode != "RGB":
        converted = img.convert("RGB")
        working = converted

    if working.width > MAX_IMAGE_DIM or working.height > MAX_IMAGE_DIM:
        working.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM), _resample_filter(Image))

    buffer = io.BytesIO()
    try:
        working.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    finally:
        buffer.close()
        if converted is not None:
            converted.close()


def analyze_screen_snippet(
    instruction: str = DEFAULT_INSTRUCTION,
) -> str:
    """Inspect the screenshot currently on the Windows clipboard via vision."""
    instruction = (instruction or "").strip() or DEFAULT_INSTRUCTION

    if sys.platform != "win32":
        return "Error: Screen snippet analysis is only available on Windows."

    try:
        from PIL import Image, ImageGrab
    except ImportError:
        return "Error: Pillow is not installed. Run: pip install Pillow"

    try:
        img = ImageGrab.grabclipboard()
    except Exception as exc:  # noqa: BLE001
        return f"Failed to read clipboard image: {exc}"

    if img is None or not isinstance(img, Image.Image):
        return NO_IMAGE_ERROR

    try:
        b64_image = _normalize_and_encode(img)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to encode clipboard image: {exc}"
    finally:
        try:
            img.close()
        except Exception:  # noqa: BLE001
            pass

    # Lazy import: registry loads this skill; avoid a circular import with agent.
    from tars.providers import complete_vision_isolated

    try:
        text = complete_vision_isolated(instruction, b64_image)
    except Exception as exc:  # noqa: BLE001
        return f"Failed to analyze screen snippet: {exc}"

    result = (text or "").strip()
    if not result:
        return "Error: Vision model returned an empty analysis."
    return result
