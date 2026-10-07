"""
PDF generation service (Optimized for low latency, zero disk I/O, and minimal memory).

Re-uses ALL logic from the original main.py verbatim — every coordinate,
every font-size, every character grid position — while achieving:
  1. 100% In-Memory Processing: No temporary files created on disk.
  2. Template In-Memory Caching: template.pdf bytes cached in RAM once.
  3. Single Image Resampling: Prepared once for duplicate & original boxes,
     avoiding redundant LANCZOS filtering and PNG re-compression.
  4. Deflate Stream Compression: Produces smaller, optimized PDF bytes directly.
  5. Strict Coordinate Preservation: No PDF layout coordinate is changed.

Complexity
----------
Time  : O(W × H) for single photo resampling + O(N_pages) for PDF text placement.
Space : O(W × H) for single in-memory RGBA image buffer.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from typing import Union

import pymupdf
from PIL import Image, ImageOps

# =========================================================
# PROJECT ROOT & IN-MEMORY TEMPLATE CACHE
# =========================================================
_ROOT = Path(__file__).resolve().parents[2]   # …/ticket_gen/
_TEMPLATE_PDF_PATH = _ROOT / "template.pdf"

# Pre-cache the template PDF in memory for instant reuse
with open(_TEMPLATE_PDF_PATH, "rb") as _f:
    _TEMPLATE_PDF_BYTES = _f.read()

# Dedicated thread pool executor for CPU-bound PyMuPDF operations
_PDF_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pdf_gen")

# =========================================================
# ZOOM / BACKGROUND CONSTANTS (unchanged from main.py)
# =========================================================
ZOOM_OUT = 0.08
ZOOM_IN = 0.00
WHITE_BACKGROUND = True


# =========================================================
# PUBLIC ASYNC ENTRY POINT
# =========================================================

async def generate_pdf_bytes(data: dict, photo_bytes: bytes) -> bytes:
    """
    Asynchronously generate the hall-ticket PDF.

    Parameters
    ----------
    data : dict
        Validated student/academic/… data (matches index.json structure).
    photo_bytes : bytes
        Background-removed PNG bytes of the student photo.

    Returns
    -------
    bytes
        Complete PDF as raw bytes ready to stream to the client.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _PDF_EXECUTOR,
        _sync_generate,
        data,
        photo_bytes,
    )


# =========================================================
# SYNCHRONOUS IN-MEMORY IMPLEMENTATION
# =========================================================

def _sync_generate(data: dict, photo_bytes: bytes) -> bytes:
    """
    Synchronous PDF generation — runs inside the dedicated thread pool.
    Operates completely in-memory with zero temporary disk files.
    """
    doc = pymupdf.open(stream=_TEMPLATE_PDF_BYTES, filetype="pdf")

    fill_page_1(doc[0], data)
    fill_page_2(doc[1], data)
    fill_page_3(doc[2], data, photo_bytes)
    fill_page_4(doc[3], data)

    # Deflate compressed in-memory PDF output (reduces payload by ~50% and speeds up downloads)
    pdf_bytes = doc.tobytes(deflate=True, garbage=3)
    doc.close()

    return pdf_bytes


# =========================================================
# =========================================================
# PAGE FILL FUNCTIONS — COORDINATES UNCHANGED FROM main.py
# =========================================================
# =========================================================

# ---------------------------------------------------------
# COMMON HELPERS
# ---------------------------------------------------------

def insert_text(page, text, x, y, fontsize=12):
    """Insert text into the PDF. Skips if coordinates are None."""
    if x is None or y is None or text is None:
        return
    page.insert_text(
        (x, y),
        str(text),
        fontsize=fontsize,
        fontname="helv",
        color=(0, 0, 0),
    )


def insert_hall_ticket(page, hall_ticket, positions, fontsize=12):
    """
    Insert hall-ticket number character by character.
    Each character maps to its own (x, y) coordinate.
    """
    if len(hall_ticket) > len(positions):
        raise ValueError(
            f"Hall ticket has {len(hall_ticket)} characters, "
            f"but only {len(positions)} positions were provided."
        )
    for character, (x, y) in zip(hall_ticket, positions):
        if x is None or y is None:
            continue
        insert_text(page, character, x, y, fontsize)


def prepare_photo(image_input: Union[str, bytes, BytesIO], target_width: int, target_height: int) -> Image.Image:
    """
    Prepare photograph for insertion.

    Maintains aspect ratio, supports ZOOM_OUT / ZOOM_IN, crops excess,
    produces exact target dimensions. Logic is identical to main.py.
    """
    if isinstance(image_input, bytes):
        image = Image.open(BytesIO(image_input))
    elif isinstance(image_input, BytesIO):
        image_input.seek(0)
        image = Image.open(image_input)
    else:
        image = Image.open(image_input)

    if image.mode != "RGBA":
        image = image.convert("RGBA")

    # Validate zoom values
    if ZOOM_OUT < 0:
        raise ValueError("ZOOM_OUT cannot be negative.")
    if ZOOM_IN < 0:
        raise ValueError("ZOOM_IN cannot be negative.")
    if ZOOM_OUT > 0 and ZOOM_IN > 0:
        raise ValueError("Use either ZOOM_OUT or ZOOM_IN, not both at the same time.")

    # ZOOM OUT — add padding
    if ZOOM_OUT > 0:
        original_width, original_height = image.size
        pad_x = int(original_width * ZOOM_OUT)
        pad_y = int(original_height * ZOOM_OUT)
        padding_color = (255, 255, 255, 255) if WHITE_BACKGROUND else (255, 255, 255, 0)
        image = ImageOps.expand(
            image,
            border=(pad_x, pad_y, pad_x, pad_y),
            fill=padding_color,
        )

    # ZOOM IN — crop outer portion
    if ZOOM_IN > 0:
        width, height = image.size
        crop_x = int(width * ZOOM_IN)
        crop_y = int(height * ZOOM_IN)
        left, top = crop_x, crop_y
        right, bottom = width - crop_x, height - crop_y
        if right <= left:
            raise ValueError("ZOOM_IN is too large horizontally.")
        if bottom <= top:
            raise ValueError("ZOOM_IN is too large vertically.")
        image = image.crop((left, top, right, bottom))

    # Fit into target box — aspect-ratio preserved, exact dimensions
    return ImageOps.fit(
        image,
        (target_width, target_height),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.35),  # Slightly favor top (face/head)
    )


# ---------------------------------------------------------
# PAGE 1
# ---------------------------------------------------------

def fill_page_1(page, data):
    student = data["student"]
    academic = data["academic"]
    examination = data["examination"]
    subjects = data["subjects"]

    # ---- Coordinates (UNCHANGED) ----
    BRANCH_X = 228.1
    BRANCH_Y = 124.9

    YEAR_X = 501.2
    YEAR_Y = 165.0

    MONTH_YEAR_X = 242
    MONTH_YEAR_Y = 306

    STUDENT_NAME_X = 242
    STUDENT_NAME_Y = 335

    FATHER_NAME_X = 242
    FATHER_NAME_Y = 378

    HALL_TICKET_POSITIONS = [
        (233, 275), (260, 275), (290, 275), (320, 275), (350, 275),
        (380, 275), (410, 275), (440, 275), (470, 275), (500, 275),
    ]

    SUBJECT_POSITIONS = [
        (100, 480.1), (100, 510.0), (100, 535.5),
        (100, 565.5), (100, 593.4), (100, 623.2),
        (350.0, 480.7),
    ]
    # ---- End coordinates ----

    insert_text(page, academic["branch"], BRANCH_X, BRANCH_Y, fontsize=13)
    insert_text(page, academic["semester"], YEAR_X, YEAR_Y, fontsize=13)
    insert_text(page, examination["month_year"], MONTH_YEAR_X, MONTH_YEAR_Y, fontsize=12)
    insert_hall_ticket(page, student["hall_ticket"], HALL_TICKET_POSITIONS, fontsize=12)
    insert_text(page, student["name"], STUDENT_NAME_X, STUDENT_NAME_Y, fontsize=12)
    insert_text(page, student["father_name"], FATHER_NAME_X, FATHER_NAME_Y, fontsize=12)

    for subject, (x, y) in zip(subjects, SUBJECT_POSITIONS):
        subject_text = f'{subject["number"]}) {subject["name"]}'
        insert_text(page, subject_text, x, y, fontsize=10)


# ---------------------------------------------------------
# PAGE 2
# ---------------------------------------------------------

def fill_page_2(page, data):
    certificate = data["certificate"]

    # ---- Coordinates (UNCHANGED) ----
    CERTIFICATE_NAME_X = 260.6
    CERTIFICATE_NAME_Y = 100.3

    CERTIFICATE_DATE_X = 215.7
    CERTIFICATE_DATE_Y = 123.9
    # ---- End coordinates ----

    insert_text(page, certificate["name"], CERTIFICATE_NAME_X, CERTIFICATE_NAME_Y, fontsize=12)
    insert_text(page, certificate["date"], CERTIFICATE_DATE_X, CERTIFICATE_DATE_Y, fontsize=12)


# ---------------------------------------------------------
# PAGE 3  (DUPLICATE top + ORIGINAL bottom)
# ---------------------------------------------------------

def fill_page_3(page, data, photo_source: Union[str, bytes]):
    student = data["student"]
    academic = data["academic"]
    examination = data["examination"]
    subjects = data["subjects"]

    # ---- Coordinates (UNCHANGED) ----

    # Duplicate
    DUPLICATE_HALL_TICKET_POSITIONS = [
        (365, 95), (385, 95), (405, 95), (425, 95), (443, 95),
        (461, 95), (483, 95), (500, 95), (520, 95), (540, 95),
    ]
    DUPLICATE_STUDENT_NAME_X = 270.0
    DUPLICATE_STUDENT_NAME_Y = 120.4
    DUPLICATE_FATHER_NAME_X = 270.0
    DUPLICATE_FATHER_NAME_Y = 140.0
    DUPLICATE_MONTH_YEAR_X = 270.0
    DUPLICATE_MONTH_YEAR_Y = 155.9
    DUPLICATE_EXAM_TYPE_X = 270.0
    DUPLICATE_EXAM_TYPE_Y = 172.6
    DUPLICATE_YEAR_X = 522.3
    DUPLICATE_YEAR_Y = 74
    DUPLICATE_SEMESTER_X = 558.4
    DUPLICATE_SEMESTER_Y = 74
    DUPLICATE_SUBJECT_POSITIONS = [
        (100, 225), (100, 243), (100, 263),
        (100, 283), (100, 300), (100, 320),
        (335, 225),
    ]
    DUPLICATE_PHOTO_TOP_LEFT = (487.55, 106.90)
    DUPLICATE_PHOTO_BOTTOM_RIGHT = (577.70, 201.35)

    # Original
    ORIGINAL_HALL_TICKET_POSITIONS = [
        (365, 486), (385, 486), (405, 486), (425, 486), (443, 486),
        (461, 486), (483, 486), (500, 486), (520, 486), (540, 486),
    ]
    ORIGINAL_STUDENT_NAME_X = 270.0
    ORIGINAL_STUDENT_NAME_Y = 510
    ORIGINAL_FATHER_NAME_X = 270.0
    ORIGINAL_FATHER_NAME_Y = 530
    ORIGINAL_MONTH_YEAR_X = 270.0
    ORIGINAL_MONTH_YEAR_Y = 547
    ORIGINAL_EXAM_TYPE_X = 270.0
    ORIGINAL_EXAM_TYPE_Y = 563
    ORIGINAL_YEAR_X = 522.3
    ORIGINAL_YEAR_Y = 465
    ORIGINAL_SEMESTER_X = 558.4
    ORIGINAL_SEMESTER_Y = 465
    ORIGINAL_SUBJECT_POSITIONS = [
        (100, 620), (100, 640), (100, 660),
        (100, 680), (100, 700), (100, 720),
        (335, 620),
    ]
    ORIGINAL_PHOTO_TOP_LEFT = (497.35, 503.05)
    ORIGINAL_PHOTO_BOTTOM_RIGHT = (587.50, 597.50)

    # ---- End coordinates ----

    # Compute photo rectangles
    rect_dup = pymupdf.Rect(*DUPLICATE_PHOTO_TOP_LEFT, *DUPLICATE_PHOTO_BOTTOM_RIGHT)
    rect_orig = pymupdf.Rect(*ORIGINAL_PHOTO_TOP_LEFT, *ORIGINAL_PHOTO_BOTTOM_RIGHT)

    # High-resolution scale x4 (both boxes have exact width 90.15 and height 94.45)
    SCALE = 4
    target_width = max(1, int(rect_dup.width * SCALE))
    target_height = max(1, int(rect_dup.height * SCALE))

    # Optimization: Prepare fitted image ONCE and reuse stream for both boxes
    fitted_image = prepare_photo(photo_source, target_width, target_height)
    image_buffer = BytesIO()
    fitted_image.save(image_buffer, format="PNG")
    photo_png_bytes = image_buffer.getvalue()

    # --- INSERT DUPLICATE ---
    insert_hall_ticket(page, student["hall_ticket"], DUPLICATE_HALL_TICKET_POSITIONS, fontsize=12)
    insert_text(page, student["name"], DUPLICATE_STUDENT_NAME_X, DUPLICATE_STUDENT_NAME_Y, fontsize=12)
    insert_text(page, student["father_name"], DUPLICATE_FATHER_NAME_X, DUPLICATE_FATHER_NAME_Y, fontsize=12)
    insert_text(page, examination["month_year"], DUPLICATE_MONTH_YEAR_X, DUPLICATE_MONTH_YEAR_Y, fontsize=12)
    insert_text(page, student["type"], DUPLICATE_EXAM_TYPE_X, DUPLICATE_EXAM_TYPE_Y, fontsize=12)
    insert_text(page, academic["year"], DUPLICATE_YEAR_X, DUPLICATE_YEAR_Y, fontsize=12)
    insert_text(page, academic["semester"], DUPLICATE_SEMESTER_X, DUPLICATE_SEMESTER_Y, fontsize=12)

    for subject, (x, y) in zip(subjects, DUPLICATE_SUBJECT_POSITIONS):
        insert_text(page, subject["name"], x, y, fontsize=11)

    page.insert_image(rect_dup, stream=photo_png_bytes)

    # --- INSERT ORIGINAL ---
    insert_hall_ticket(page, student["hall_ticket"], ORIGINAL_HALL_TICKET_POSITIONS, fontsize=12)
    insert_text(page, student["name"], ORIGINAL_STUDENT_NAME_X, ORIGINAL_STUDENT_NAME_Y, fontsize=12)
    insert_text(page, student["father_name"], ORIGINAL_FATHER_NAME_X, ORIGINAL_FATHER_NAME_Y, fontsize=12)
    insert_text(page, examination["month_year"], ORIGINAL_MONTH_YEAR_X, ORIGINAL_MONTH_YEAR_Y, fontsize=12)
    insert_text(page, student["type"], ORIGINAL_EXAM_TYPE_X, ORIGINAL_EXAM_TYPE_Y, fontsize=12)
    insert_text(page, academic["year"], ORIGINAL_YEAR_X, ORIGINAL_YEAR_Y, fontsize=12)
    insert_text(page, academic["semester"], ORIGINAL_SEMESTER_X, ORIGINAL_SEMESTER_Y, fontsize=12)

    for subject, (x, y) in zip(subjects, ORIGINAL_SUBJECT_POSITIONS):
        insert_text(page, subject["name"], x, y, fontsize=11)

    page.insert_image(rect_orig, stream=photo_png_bytes)


# ---------------------------------------------------------
# PAGE 4 (instructions only — nothing to fill)
# ---------------------------------------------------------

def fill_page_4(page, data):
    pass
