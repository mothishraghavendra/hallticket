"""
Background removal service.

Wraps the synchronous rembg.remove() call inside an asyncio thread-pool
executor so it never blocks the FastAPI event loop.

Design decisions
----------------
* rembg initialises one lightweight u2netp ONNX session at module import so
    every request reuses the warm model — O(1) amortised model loading.
* The function accepts raw bytes → returns raw bytes (PNG with alpha).
  This keeps the service I/O-agnostic (no file-system coupling).
* asyncio.get_event_loop().run_in_executor() is used rather than
  asyncio.to_thread() for Python 3.8 compatibility; both are O(1).
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO

import rembg
from PIL import Image, ImageOps

_MAX_IMAGE_EDGE = 2048
_MAX_IMAGE_PIXELS = 40_000_000


class ImageDimensionsError(ValueError):
    """Raised when an upload exceeds the supported decoded image size."""

# =========================================================
# WARM UP: load ONNX model once at startup (not per request)
# =========================================================
# rembg.new_session() downloads / caches the model the very first time.
# After that it is O(1) — just loads from local cache.
_BG_MODEL_NAME = "u2netp"
_BG_SESSION = rembg.new_session(_BG_MODEL_NAME)

# Dedicated single-thread executor to avoid blocking the main pool with
# the CPU-bound ONNX inference.  One thread is enough because GPU/CPU
# inference is already multi-threaded internally by ONNX Runtime.
_BG_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="bg_remover")


# =========================================================
# PUBLIC ASYNC API
# =========================================================

async def remove_background(image_bytes: bytes) -> bytes:
    """
    Asynchronously remove the background from raw image bytes.

    Parameters
    ----------
    image_bytes : bytes
        Raw bytes of the original photo (JPEG / PNG / WebP …).

    Returns
    -------
    bytes
        PNG bytes with background replaced by alpha transparency.

    Complexity
    ----------
    Time  : O(W × H) — dominated by ONNX inference on the image pixels.
    Space : O(W × H) — one input tensor + one output tensor in memory.
    """
    loop = asyncio.get_event_loop()

    # Run the blocking ONNX inference in the dedicated executor thread.
    output_bytes: bytes = await loop.run_in_executor(
        _BG_EXECUTOR,
        _sync_remove,
        image_bytes,
    )
    return output_bytes


# =========================================================
# PRIVATE SYNC HELPER (runs inside thread pool)
# =========================================================

def _sync_remove(image_bytes: bytes) -> bytes:
    """
    Synchronous wrapper around rembg.remove().

    Reuses the pre-warmed _BG_SESSION so the ONNX model is loaded
    exactly once for the lifetime of the process.
    """
    prepared_bytes = _prepare_image(image_bytes)
    return rembg.remove(prepared_bytes, session=_BG_SESSION)


def _prepare_image(image_bytes: bytes) -> bytes:
    """Bound inference cost for large photos while leaving ordinary uploads intact."""
    with Image.open(BytesIO(image_bytes)) as image:
        width, height = image.size
        if width * height > _MAX_IMAGE_PIXELS:
            raise ImageDimensionsError("Image dimensions are too large to process safely.")

        orientation = image.getexif().get(274, 1)
        if max(width, height) <= _MAX_IMAGE_EDGE and orientation == 1:
            return image_bytes

        image = ImageOps.exif_transpose(image)
        image.thumbnail((_MAX_IMAGE_EDGE, _MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
        output = BytesIO()
        if image.mode in ("RGBA", "LA") or "transparency" in image.info:
            image.convert("RGBA").save(output, format="PNG")
        else:
            image.convert("RGB").save(output, format="JPEG", quality=90)
        return output.getvalue()
