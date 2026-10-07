"""
FastAPI application — Hall Ticket Generator API.

Endpoints
---------
GET  /                           HTML form (Jinja2 template, Carbon Design System)
GET  /health                     Health check (JSON)
POST /generate                   Generate hall-ticket PDF (multipart)

Flow
----
  1. User fills the responsive Carbon HTML form at GET / (desktop or mobile).
  2. JavaScript serialises fields → FormData { data: JSON string, photo: File }.
  3. POST /generate:
     - Validates input via Pydantic.
     - Asynchronously removes background using ONNX model in thread pool.
     - Asynchronously fills template.pdf completely in memory.
     - Streams deflated PDF bytes back with CORS and content headers.

Optimizations
-------------
* CORS enabled for any network origin or IP address (e.g. mobile access via Wi-Fi).
* ONNX session pre-warmed on server startup for fast first-request response.
* In-memory template caching & zero temporary files on disk.
* Deflate compression for reduced mobile bandwidth.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

from app.models import ErrorResponse, HallTicketRequest, HealthResponse
from app.services import bg_remover, pdf_generator

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("ticket_gen")


# =========================================================
# LIFESPAN — warm up the ONNX model before the first request
# =========================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Runs on startup: runs a tiny dummy image through rembg so the ONNX
    runtime graph and thread pools are fully compiled and warm before
    any user request arrives.
    """
    logger.info("Warming up rembg ONNX session …")
    try:
        dummy_buf = BytesIO()
        Image.new("RGB", (32, 32), color="white").save(dummy_buf, format="PNG")
        await bg_remover.remove_background(dummy_buf.getvalue())
        logger.info("rembg ONNX session warmed up successfully.")
    except Exception as exc:
        logger.warning("Non-fatal warning during model warm-up: %s", exc)

    yield

    logger.info("Shutting down Hall Ticket Generator service.")


# =========================================================
# APP CONFIGURATION
# =========================================================
app = FastAPI(
    title="Hall Ticket Generator API",
    description=(
        "Upload a student photo and fill in student details to generate "
        "a hall-ticket PDF with background removed from the photo."
    ),
    version="1.1.0",
    lifespan=lifespan,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)

# =========================================================
# CORS MIDDLEWARE
# Supports desktop, mobile via LAN IP address, or mobile web apps
# =========================================================
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r".*",            # Matches any IP address (e.g. http://192.168.x.x:port) or origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "X-Filename"],
)

# =========================================================
# STATIC FILES & TEMPLATES
# =========================================================
_BASE = Path(__file__).resolve().parent.parent   # …/ticket_gen/

app.mount(
    "/static",
    StaticFiles(directory=str(_BASE / "static")),
    name="static",
)

templates = Jinja2Templates(directory=str(_BASE / "templates"))


# =========================================================
# ENDPOINTS
# =========================================================

# ---------------------------------------------------------
# GET / — HTML form
# ---------------------------------------------------------

@app.get(
    "/",
    response_class=HTMLResponse,
    summary="Hall Ticket Form",
    tags=["UI"],
    include_in_schema=False,
)
async def index(request: Request) -> HTMLResponse:
    """
    Serve the responsive IBM Carbon Design System HTML form.
    """
    return templates.TemplateResponse(
        request=request,
        name="index.html",
    )


# ---------------------------------------------------------
# GET /health — Health Check
# ---------------------------------------------------------

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Utility"],
)
async def health() -> HealthResponse:
    """Returns 200 OK when the service is up."""
    return HealthResponse(status="ok", message="Hall Ticket Generator is running.")


# ---------------------------------------------------------
# POST /generate — Generate Hall Ticket PDF
# ---------------------------------------------------------

@app.post(
    "/generate",
    summary="Generate Hall Ticket PDF",
    tags=["Hall Ticket"],
    response_class=Response,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Generated hall-ticket PDF.",
        }
    },
)
async def generate_hall_ticket(
    data: str = Form(
        ...,
        description="JSON string matching the HallTicketRequest schema.",
    ),
    photo: UploadFile = File(
        ...,
        description="Student photograph (JPEG / PNG / WebP). Max 10 MB.",
    ),
) -> Response:
    """
    **Generate a hall-ticket PDF in async steps:**

    1. **Validate** the `data` JSON form field against the Pydantic schema.
    2. **Validate & Read** uploaded photo bytes (verified via PIL magic bytes).
    3. **Remove background** asynchronously via ONNX model in thread pool.
    4. **Generate PDF** asynchronously in-memory using PyMuPDF.
    5. **Stream deflated PDF** with appropriate download and CORS headers.
    """

    # ----------------------------------------------------------
    # 1. Parse & validate JSON payload
    # ----------------------------------------------------------
    try:
        raw = json.loads(data)
        request_data = HallTicketRequest.model_validate(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in 'data' field: {exc}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )

    # ----------------------------------------------------------
    # 2. Read & validate uploaded photo
    # ----------------------------------------------------------
    MAX_PHOTO_BYTES = 10 * 1024 * 1024  # 10 MB
    photo_bytes = await photo.read()

    if len(photo_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Photo file is empty. Please upload a valid image.",
        )

    if len(photo_bytes) > MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Photo exceeds the 10 MB size limit.",
        )

    # Verify image integrity via PIL (handles quirky mobile browser content-type headers)
    try:
        with Image.open(BytesIO(photo_bytes)) as test_img:
            test_img.verify()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a valid or readable image. Accepted formats: JPEG, PNG, WebP.",
        )

    logger.info(
        "Request received | student=%s | hall_ticket=%s | photo_size=%d bytes",
        request_data.student.name,
        request_data.student.hall_ticket,
        len(photo_bytes),
    )

    # ----------------------------------------------------------
    # 3. Remove background — async, awaited fully
    # ----------------------------------------------------------
    logger.info("Removing background …")
    try:
        no_bg_bytes: bytes = await bg_remover.remove_background(photo_bytes)
    except bg_remover.ImageDimensionsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("Background removal failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Background removal failed: {exc}",
        )
    logger.info("Background removed successfully (%d bytes PNG).", len(no_bg_bytes))

    # ----------------------------------------------------------
    # 4. Generate PDF — async, 100% in-memory
    # ----------------------------------------------------------
    logger.info("Generating PDF …")
    try:
        pdf_bytes: bytes = await pdf_generator.generate_pdf_bytes(
            data=request_data.model_dump(),
            photo_bytes=no_bg_bytes,
        )
    except Exception as exc:
        logger.exception("PDF generation failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {exc}",
        )

    logger.info(
        "PDF generated successfully | size=%d bytes | student=%s",
        len(pdf_bytes),
        request_data.student.name,
    )

    # ----------------------------------------------------------
    # 5. Stream PDF back to client
    # ----------------------------------------------------------
    filename = f"hallticket_{request_data.student.hall_ticket}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
            "X-Filename": filename,
        },
    )
