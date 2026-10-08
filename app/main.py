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
      - Embeds the uploaded photo without background processing.
      - Asynchronously fills template.pdf completely in memory.
      - Streams deflated PDF bytes back with CORS and content headers.

Optimizations
-------------
* CORS enabled for any network origin or IP address (e.g. mobile access via Wi-Fi).
* In-memory template caching & zero temporary files on disk.
* Deflate compression for reduced mobile bandwidth.
"""

from __future__ import annotations

import json
import logging
import time
from uuid import uuid4
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image

from app.models import ErrorResponse, HallTicketRequest, HealthResponse
from app.services import name_registry, pdf_generator

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("ticket_gen")


# =========================================================
# =========================================================
# APP CONFIGURATION
# =========================================================
app = FastAPI(
    title="Hall Ticket Generator API",
    description=(
        "Upload a student photo and fill in student details to generate "
        "a hall-ticket PDF with the uploaded photo unchanged."
    ),
    version="1.1.0",
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


@app.middleware("http")
async def log_http_requests(request: Request, call_next):
    request_id = uuid4().hex
    request.state.request_id = request_id
    started_at = time.perf_counter()
    logger.info(
        "request.started request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "request.failed request_id=%s method=%s path=%s duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            (time.perf_counter() - started_at) * 1000,
        )
        raise

    duration_ms = (time.perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request.completed request_id=%s method=%s path=%s status_code=%d duration_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


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
    request: Request,
    data: str = Form(
        ...,
        description="JSON string matching the HallTicketRequest schema.",
    ),
    photo: UploadFile = File(
        ...,
        description="Student photograph (JPEG / PNG / WebP). Max 4 MB.",
    ),
) -> Response:
    """
    **Generate a hall-ticket PDF in async steps:**

    1. **Validate** the `data` JSON form field against the Pydantic schema.
    2. **Validate & Read** uploaded photo bytes (verified via PIL magic bytes).
    3. **Generate PDF** asynchronously in-memory using PyMuPDF and the uploaded photo.
    4. **Stream deflated PDF** with appropriate download and CORS headers.
    """
    request_id = request.state.request_id

    # ----------------------------------------------------------
    # 1. Parse & validate JSON payload
    # ----------------------------------------------------------
    try:
        raw = json.loads(data)
        request_data = HallTicketRequest.model_validate(raw)
    except json.JSONDecodeError as exc:
        logger.warning("payload.rejected request_id=%s reason=invalid_json", request_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON in 'data' field: {exc}",
        )
    except Exception as exc:
        logger.warning("payload.rejected request_id=%s reason=schema_validation", request_id)
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        )
    logger.info(
        "payload.validated request_id=%s subject_count=%d",
        request_id,
        len(request_data.subjects),
    )

    # ----------------------------------------------------------
    # 2. Read & validate uploaded photo
    # ----------------------------------------------------------
    max_photo_bytes = 4 * 1024 * 1024
    max_request_bytes = int(4.5 * 1024 * 1024)
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > max_request_bytes:
        logger.warning(
            "upload.rejected request_id=%s reason=content_length_limit content_length=%s",
            request_id,
            content_length,
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Upload exceeds the maximum request size.",
        )

    photo_bytes = await photo.read(max_photo_bytes + 1)

    if len(photo_bytes) == 0:
        logger.warning("upload.rejected request_id=%s reason=empty_file", request_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Photo file is empty. Please upload a valid image.",
        )

    if len(photo_bytes) > max_photo_bytes:
        logger.warning(
            "upload.rejected request_id=%s reason=photo_size_limit size_bytes=%d",
            request_id,
            len(photo_bytes),
        )
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Photo exceeds the 4 MB size limit.",
        )

    # Verify image integrity via PIL (handles quirky mobile browser content-type headers)
    try:
        with Image.open(BytesIO(photo_bytes)) as test_img:
            test_img.verify()
    except Exception:
        logger.warning(
            "upload.rejected request_id=%s reason=invalid_image size_bytes=%d",
            request_id,
            len(photo_bytes),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is not a valid or readable image. Accepted formats: JPEG, PNG, WebP.",
        )

    logger.info(
        "generation.accepted request_id=%s photo_size_bytes=%d subject_count=%d",
        request_id,
        len(photo_bytes),
        len(request_data.subjects),
    )

    # ----------------------------------------------------------
    # 3. Generate PDF — async, 100% in-memory
    # ----------------------------------------------------------
    stage_started_at = time.perf_counter()
    logger.info("pdf_generation.started request_id=%s", request_id)
    try:
        pdf_bytes: bytes = await pdf_generator.generate_pdf_bytes(
            data=request_data.model_dump(),
            photo_bytes=photo_bytes,
        )
    except Exception as exc:
        logger.exception("pdf_generation.failed request_id=%s", request_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF generation failed: {exc}",
        )

    logger.info(
        "pdf_generation.completed request_id=%s output_size_bytes=%d duration_ms=%.1f",
        request_id,
        len(pdf_bytes),
        (time.perf_counter() - stage_started_at) * 1000,
    )

    try:
        recorded = await name_registry.record_generated_name(request_data.student.name)
        if recorded:
            logger.info("generation_name.recorded request_id=%s", request_id)
        else:
            logger.info("generation_name.skipped request_id=%s reason=serverless_storage", request_id)
    except Exception:
        logger.exception("generation_name.record_failed request_id=%s", request_id)

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
