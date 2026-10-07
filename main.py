import json
import os
import pymupdf

from PIL import Image, ImageOps
from io import BytesIO


# =========================================================
# CONFIGURATION
# =========================================================

INPUT_PDF = "template.pdf"

OUTPUT_PDF = "output/updated_hallticket.pdf"

JSON_FILE = "index.json"

IMAGE_PATH = "imgs/profile_no_bg.png"


# =========================================================
# PHOTO ZOOM CONFIGURATION
# =========================================================
#
# You can control the photograph size from here.
#
# ZOOM_OUT:
#     Makes the person/photo appear smaller.
#
#     Example:
#         0.05 = small zoom out
#         0.08 = moderate zoom out
#         0.12 = more zoom out
#
#
# ZOOM_IN:
#     Makes the person/photo appear larger.
#
#     Example:
#         0.05 = small zoom in
#         0.10 = moderate zoom in
#         0.15 = more zoom in
#
#
# IMPORTANT:
#
# Keep ONE of these as 0.0 at a time.
#
# For example:
#
#     ZOOM_OUT = 0.08
#     ZOOM_IN  = 0.00
#
# means slightly zoom OUT.
#
#
# Or:
#
#     ZOOM_OUT = 0.00
#     ZOOM_IN  = 0.08
#
# means slightly zoom IN.
# =========================================================

ZOOM_OUT = 0.08

ZOOM_IN = 0.00


# =========================================================
# IMAGE BACKGROUND
# =========================================================
#
# True:
#     Added padding will be white.
#
# False:
#     Added padding will remain transparent.
#
# For a hall-ticket photograph, WHITE is recommended.
# =========================================================

WHITE_BACKGROUND = True


# =========================================================
# LOAD JSON
# =========================================================

def load_data(path):
    """
    Load form data from index.json.
    """

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(file)


# =========================================================
# COMMON TEXT INSERT FUNCTION
# =========================================================

def insert_text(
    page,
    text,
    x,
    y,
    fontsize=12
):
    """
    Insert text into the PDF.

    If x or y is None, nothing is inserted.
    """

    # -----------------------------------------------------
    # Skip unmeasured coordinates
    # -----------------------------------------------------

    if x is None or y is None:
        return


    # -----------------------------------------------------
    # Insert text
    # -----------------------------------------------------

    page.insert_text(
        (x, y),
        str(text),
        fontsize=fontsize,
        fontname="helv",
        color=(0, 0, 0)
    )


# =========================================================
# HALL TICKET INSERT FUNCTION
# =========================================================

def insert_hall_ticket(
    page,
    hall_ticket,
    positions,
    fontsize=12
):
    """
    Insert hall-ticket number character by character.

    Example:

        24005A0512

    Each character has its own coordinate.
    """

    # -----------------------------------------------------
    # Validate positions
    # -----------------------------------------------------

    if len(hall_ticket) > len(positions):

        raise ValueError(
            f"Hall ticket has {len(hall_ticket)} characters, "
            f"but only {len(positions)} positions were provided."
        )


    # -----------------------------------------------------
    # Insert characters
    # -----------------------------------------------------

    for character, (x, y) in zip(
        hall_ticket,
        positions
    ):

        # Skip unmeasured positions
        if x is None or y is None:
            continue


        insert_text(
            page,
            character,
            x,
            y,
            fontsize
        )


# =========================================================
# PREPARE PHOTO
# =========================================================

def prepare_photo(
    image_path,
    target_width,
    target_height
):
    """
    Prepare the photograph for insertion.

    Features:

        - Maintains aspect ratio
        - Supports zoom OUT
        - Supports zoom IN
        - Never stretches the image
        - Crops excess area
        - Produces exact target dimensions
    """

    # =====================================================
    # OPEN IMAGE
    # =====================================================

    image = Image.open(
        image_path
    )


    # =====================================================
    # CONVERT TO RGBA
    # =====================================================

    if image.mode != "RGBA":

        image = image.convert(
            "RGBA"
        )


    # =====================================================
    # VALIDATE ZOOM VALUES
    # =====================================================

    if ZOOM_OUT < 0:

        raise ValueError(
            "ZOOM_OUT cannot be negative."
        )


    if ZOOM_IN < 0:

        raise ValueError(
            "ZOOM_IN cannot be negative."
        )


    if ZOOM_OUT > 0 and ZOOM_IN > 0:

        raise ValueError(
            "Use either ZOOM_OUT or ZOOM_IN, "
            "not both at the same time."
        )


    # =====================================================
    # ZOOM OUT
    # =====================================================
    #
    # We add padding around the original image.
    #
    # Example:
    #
    # Original:
    #
    #     ┌───────────┐
    #     │   PHOTO   │
    #     └───────────┘
    #
    # After zoom out:
    #
    #     ┌─────────────────┐
    #     │                 │
    #     │     PHOTO       │
    #     │                 │
    #     └─────────────────┘
    #
    # When this is fitted into the PDF box, the person
    # appears smaller.
    # =====================================================

    if ZOOM_OUT > 0:

        original_width, original_height = image.size


        pad_x = int(
            original_width * ZOOM_OUT
        )

        pad_y = int(
            original_height * ZOOM_OUT
        )


        if WHITE_BACKGROUND:

            padding_color = (
                255,
                255,
                255,
                255
            )

        else:

            padding_color = (
                255,
                255,
                255,
                0
            )


        image = ImageOps.expand(
            image,
            border=(
                pad_x,
                pad_y,
                pad_x,
                pad_y
            ),
            fill=padding_color
        )


    # =====================================================
    # ZOOM IN
    # =====================================================
    #
    # For zoom IN we crop the outer portion of the image
    # before fitting it into the PDF box.
    #
    # Example:
    #
    # Original:
    #
    #     ┌─────────────────┐
    #     │                 │
    #     │      PHOTO      │
    #     │                 │
    #     └─────────────────┘
    #
    # Zoom IN:
    #
    #          ┌─────────┐
    #          │  PHOTO  │
    #          └─────────┘
    #
    # =====================================================

    if ZOOM_IN > 0:

        width, height = image.size


        crop_x = int(
            width * ZOOM_IN
        )

        crop_y = int(
            height * ZOOM_IN
        )


        # -------------------------------------------------
        # Make sure crop does not destroy the image
        # -------------------------------------------------

        left = crop_x

        top = crop_y

        right = width - crop_x

        bottom = height - crop_y


        if right <= left:

            raise ValueError(
                "ZOOM_IN is too large horizontally."
            )


        if bottom <= top:

            raise ValueError(
                "ZOOM_IN is too large vertically."
            )


        image = image.crop(
            (
                left,
                top,
                right,
                bottom
            )
        )


    # =====================================================
    # FIT IMAGE INTO TARGET BOX
    # =====================================================
    #
    # ImageOps.fit:
    #
    #     - preserves aspect ratio
    #     - crops excess area
    #     - never stretches
    #     - produces exact target dimensions
    # =====================================================

    image = ImageOps.fit(
        image,
        (
            target_width,
            target_height
        ),
        method=Image.Resampling.LANCZOS,

        # Keep the image horizontally centered.
        #
        # Vertical 0.35 means slightly favor the upper
        # part of the image.
        #
        # This is useful for passport-style photographs
        # because it gives slightly more importance to
        # the face/head.
        centering=(
            0.5,
            0.35
        )
    )


    # =====================================================
    # RETURN FINAL IMAGE
    # =====================================================

    return image


# =========================================================
# IMAGE INSERT FUNCTION
# =========================================================

def insert_image(
    page,
    image_path,
    top_left,
    bottom_right
):
    """
    Insert photograph exactly inside a PDF box.

    The image is:

        - scaled
        - cropped
        - aspect-ratio preserved
        - never stretched
        - optionally zoomed in/out
    """

    # =====================================================
    # CHECK IMAGE
    # =====================================================

    if not os.path.exists(image_path):

        raise FileNotFoundError(
            f"Image file not found:\n{image_path}"
        )


    # =====================================================
    # GET COORDINATES
    # =====================================================

    x0, y0 = top_left

    x1, y1 = bottom_right


    # =====================================================
    # CHECK COORDINATES
    # =====================================================

    if x0 is None or y0 is None:

        return


    if x1 is None or y1 is None:

        return


    # =====================================================
    # CREATE PDF RECTANGLE
    # =====================================================

    rect = pymupdf.Rect(
        x0,
        y0,
        x1,
        y1
    )


    # =====================================================
    # IMAGE RESOLUTION
    # =====================================================

    SCALE = 4


    target_width = max(
        1,
        int(rect.width * SCALE)
    )


    target_height = max(
        1,
        int(rect.height * SCALE)
    )


    # =====================================================
    # PREPARE IMAGE
    # =====================================================

    fitted_image = prepare_photo(
        image_path,
        target_width,
        target_height
    )


    # =====================================================
    # CREATE MEMORY BUFFER
    # =====================================================

    image_buffer = BytesIO()


    # =====================================================
    # SAVE IMAGE AS PNG
    # =====================================================

    fitted_image.save(
        image_buffer,
        format="PNG"
    )


    image_buffer.seek(0)


    # =====================================================
    # INSERT IMAGE
    # =====================================================

    page.insert_image(
        rect,
        stream=image_buffer.getvalue()
    )


# =========================================================
# PAGE 1
# =========================================================

def fill_page_1(
    page,
    data
):

    student = data["student"]

    academic = data["academic"]

    examination = data["examination"]

    subjects = data["subjects"]


    # =====================================================
    # PAGE 1 COORDINATES
    # =====================================================

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


    # =====================================================
    # PAGE 1 HALL TICKET
    # =====================================================

    HALL_TICKET_POSITIONS = [

        (233, 275),
        (260, 275),
        (290, 275),
        (320, 275),
        (350, 275),
        (380, 275),
        (410, 275),
        (440, 275),
        (470, 275),
        (500, 275),

    ]


    # =====================================================
    # PAGE 1 SUBJECTS
    # =====================================================

    SUBJECT_POSITIONS = [

        (100, 480.1),
        (100, 510.0),
        (100, 535.5),
        (100, 565.5),
        (100, 593.4),
        (100, 623.2),
        (350.0, 480.7),

    ]


    # =====================================================
    # BRANCH
    # =====================================================

    insert_text(
        page,
        academic["branch"],
        BRANCH_X,
        BRANCH_Y,
        fontsize=13
    )


    # =====================================================
    # YEAR
    # =====================================================

    insert_text(
        page,
        academic["year"],
        YEAR_X,
        YEAR_Y,
        fontsize=13
    )


    # =====================================================
    # MONTH / YEAR
    # =====================================================

    insert_text(
        page,
        examination["month_year"],
        MONTH_YEAR_X,
        MONTH_YEAR_Y,
        fontsize=12
    )


    # =====================================================
    # HALL TICKET
    # =====================================================

    insert_hall_ticket(
        page,
        student["hall_ticket"],
        HALL_TICKET_POSITIONS,
        fontsize=12
    )


    # =====================================================
    # STUDENT NAME
    # =====================================================

    insert_text(
        page,
        student["name"],
        STUDENT_NAME_X,
        STUDENT_NAME_Y,
        fontsize=12
    )


    # =====================================================
    # FATHER NAME
    # =====================================================

    insert_text(
        page,
        student["father_name"],
        FATHER_NAME_X,
        FATHER_NAME_Y,
        fontsize=12
    )


    # =====================================================
    # SUBJECTS
    # =====================================================

    for subject, (x, y) in zip(
        subjects,
        SUBJECT_POSITIONS
    ):

        subject_text = (
            f'{subject["number"]}) {subject["name"]}'
        )


        insert_text(
            page,
            subject_text,
            x,
            y,
            fontsize=10
        )


# =========================================================
# PAGE 2
# =========================================================

def fill_page_2(
    page,
    data
):

    certificate = data["certificate"]


    # =====================================================
    # COORDINATES
    # =====================================================

    CERTIFICATE_NAME_X = 260.6
    CERTIFICATE_NAME_Y = 100.3

    CERTIFICATE_DATE_X = 215.7
    CERTIFICATE_DATE_Y = 123.9


    # =====================================================
    # NAME
    # =====================================================

    insert_text(
        page,
        certificate["name"],
        CERTIFICATE_NAME_X,
        CERTIFICATE_NAME_Y,
        fontsize=12
    )


    # =====================================================
    # DATE
    # =====================================================

    insert_text(
        page,
        certificate["date"],
        CERTIFICATE_DATE_X,
        CERTIFICATE_DATE_Y,
        fontsize=12
    )


# =========================================================
# PAGE 3
#
# TOP    = DUPLICATE
#
# BOTTOM = ORIGINAL
# =========================================================

def fill_page_3(
    page,
    data
):

    student = data["student"]

    academic = data["academic"]

    examination = data["examination"]

    subjects = data["subjects"]


    # =====================================================
    # =====================================================
    # DUPLICATE HALL TICKET
    # =====================================================
    # =====================================================


    # =====================================================
    # DUPLICATE HALL TICKET NUMBER
    # =====================================================

    DUPLICATE_HALL_TICKET_POSITIONS = [

        (365, 95),
        (385, 95),
        (405, 95),
        (425, 95),
        (443, 95),
        (461, 95),
        (483, 95),
        (500, 95),
        (520, 95),
        (540, 95),

    ]


    # =====================================================
    # DUPLICATE STUDENT NAME
    # =====================================================

    DUPLICATE_STUDENT_NAME_X = 270.0
    DUPLICATE_STUDENT_NAME_Y = 120.4


    # =====================================================
    # DUPLICATE FATHER NAME
    # =====================================================

    DUPLICATE_FATHER_NAME_X = 270.0
    DUPLICATE_FATHER_NAME_Y = 140.0


    # =====================================================
    # DUPLICATE MONTH / YEAR
    # =====================================================

    DUPLICATE_MONTH_YEAR_X = 270.0
    DUPLICATE_MONTH_YEAR_Y = 155.9


    # =====================================================
    # DUPLICATE EXAM TYPE
    # =====================================================

    DUPLICATE_EXAM_TYPE_X = 270.0
    DUPLICATE_EXAM_TYPE_Y = 172.6


    # =====================================================
    # DUPLICATE YEAR
    # =====================================================

    DUPLICATE_YEAR_X = 522.3
    DUPLICATE_YEAR_Y = 74


    # =====================================================
    # DUPLICATE SEMESTER
    # =====================================================

    DUPLICATE_SEMESTER_X = 558.4
    DUPLICATE_SEMESTER_Y = 74


    # =====================================================
    # DUPLICATE SUBJECTS
    # =====================================================

    DUPLICATE_SUBJECT_POSITIONS = [

        (100, 225),
        (100, 243),
        (100, 263),
        (100, 283),
        (100, 300),
        (100, 320),
        (335, 225),

    ]


    # =====================================================
    # DUPLICATE PHOTO BOX
    # =====================================================

    DUPLICATE_PHOTO_TOP_LEFT = (

        487.55,
        106.90

    )


    DUPLICATE_PHOTO_BOTTOM_RIGHT = (

        577.70,
        201.35

    )


    # =====================================================
    # =====================================================
    # ORIGINAL HALL TICKET
    # =====================================================
    # =====================================================


    # =====================================================
    # ORIGINAL HALL TICKET NUMBER
    # =====================================================

    ORIGINAL_HALL_TICKET_POSITIONS = [

        (365, 486),
        (385, 486),
        (405, 486),
        (425, 486),
        (443, 486),
        (461, 486),
        (483, 486),
        (500, 486),
        (520, 486),
        (540, 486),

    ]


    # =====================================================
    # ORIGINAL STUDENT NAME
    # =====================================================

    ORIGINAL_STUDENT_NAME_X = 270.0
    ORIGINAL_STUDENT_NAME_Y = 510


    # =====================================================
    # ORIGINAL FATHER NAME
    # =====================================================

    ORIGINAL_FATHER_NAME_X = 270.0
    ORIGINAL_FATHER_NAME_Y = 530


    # =====================================================
    # ORIGINAL MONTH / YEAR
    # =====================================================

    ORIGINAL_MONTH_YEAR_X = 270.0
    ORIGINAL_MONTH_YEAR_Y = 547


    # =====================================================
    # ORIGINAL EXAM TYPE
    # =====================================================

    ORIGINAL_EXAM_TYPE_X = 270.0
    ORIGINAL_EXAM_TYPE_Y = 563


    # =====================================================
    # ORIGINAL YEAR
    # =====================================================

    ORIGINAL_YEAR_X = 522.3
    ORIGINAL_YEAR_Y = 465


    # =====================================================
    # ORIGINAL SEMESTER
    # =====================================================

    ORIGINAL_SEMESTER_X = 558.4
    ORIGINAL_SEMESTER_Y = 465


    # =====================================================
    # ORIGINAL SUBJECTS
    # =====================================================

    ORIGINAL_SUBJECT_POSITIONS = [

        (100, 620),
        (100, 640),
        (100, 660),
        (100, 680),
        (100, 700),
        (100, 720),
        (335, 620),

    ]


    # =====================================================
    # ORIGINAL PHOTO BOX
    # =====================================================

    ORIGINAL_PHOTO_TOP_LEFT = (

        497.35,
        503.05

    )


    ORIGINAL_PHOTO_BOTTOM_RIGHT = (

        587.50,
        597.50

    )


    # =====================================================
    # =====================================================
    # INSERT DUPLICATE
    # =====================================================
    # =====================================================


    # -----------------------------------------------------
    # Hall Ticket
    # -----------------------------------------------------

    insert_hall_ticket(
        page,
        student["hall_ticket"],
        DUPLICATE_HALL_TICKET_POSITIONS,
        fontsize=12
    )


    # -----------------------------------------------------
    # Student Name
    # -----------------------------------------------------

    insert_text(
        page,
        student["name"],
        DUPLICATE_STUDENT_NAME_X,
        DUPLICATE_STUDENT_NAME_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Father Name
    # -----------------------------------------------------

    insert_text(
        page,
        student["father_name"],
        DUPLICATE_FATHER_NAME_X,
        DUPLICATE_FATHER_NAME_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Month / Year
    # -----------------------------------------------------

    insert_text(
        page,
        examination["month_year"],
        DUPLICATE_MONTH_YEAR_X,
        DUPLICATE_MONTH_YEAR_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Regular / Supplementary
    # -----------------------------------------------------

    insert_text(
        page,
        student["type"],
        DUPLICATE_EXAM_TYPE_X,
        DUPLICATE_EXAM_TYPE_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Year
    # -----------------------------------------------------

    insert_text(
        page,
        academic["year"],
        DUPLICATE_YEAR_X,
        DUPLICATE_YEAR_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Semester
    # -----------------------------------------------------

    insert_text(
        page,
        academic["semester"],
        DUPLICATE_SEMESTER_X,
        DUPLICATE_SEMESTER_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Subjects
    # -----------------------------------------------------

    for subject, (x, y) in zip(
        subjects,
        DUPLICATE_SUBJECT_POSITIONS
    ):

        insert_text(
            page,
            subject["name"],
            x,
            y,
            fontsize=11
        )


    # -----------------------------------------------------
    # Photograph
    # -----------------------------------------------------

    insert_image(
        page,
        IMAGE_PATH,
        DUPLICATE_PHOTO_TOP_LEFT,
        DUPLICATE_PHOTO_BOTTOM_RIGHT
    )


    # =====================================================
    # =====================================================
    # INSERT ORIGINAL
    # =====================================================
    # =====================================================


    # -----------------------------------------------------
    # Hall Ticket
    # -----------------------------------------------------

    insert_hall_ticket(
        page,
        student["hall_ticket"],
        ORIGINAL_HALL_TICKET_POSITIONS,
        fontsize=12
    )


    # -----------------------------------------------------
    # Student Name
    # -----------------------------------------------------

    insert_text(
        page,
        student["name"],
        ORIGINAL_STUDENT_NAME_X,
        ORIGINAL_STUDENT_NAME_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Father Name
    # -----------------------------------------------------

    insert_text(
        page,
        student["father_name"],
        ORIGINAL_FATHER_NAME_X,
        ORIGINAL_FATHER_NAME_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Month / Year
    # -----------------------------------------------------

    insert_text(
        page,
        examination["month_year"],
        ORIGINAL_MONTH_YEAR_X,
        ORIGINAL_MONTH_YEAR_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Regular / Supplementary
    # -----------------------------------------------------

    insert_text(
        page,
        student["type"],
        ORIGINAL_EXAM_TYPE_X,
        ORIGINAL_EXAM_TYPE_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Year
    # -----------------------------------------------------

    insert_text(
        page,
        academic["year"],
        ORIGINAL_YEAR_X,
        ORIGINAL_YEAR_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Semester
    # -----------------------------------------------------

    insert_text(
        page,
        academic["semester"],
        ORIGINAL_SEMESTER_X,
        ORIGINAL_SEMESTER_Y,
        fontsize=12
    )


    # -----------------------------------------------------
    # Subjects
    # -----------------------------------------------------

    for subject, (x, y) in zip(
        subjects,
        ORIGINAL_SUBJECT_POSITIONS
    ):

        insert_text(
            page,
            subject["name"],
            x,
            y,
            fontsize=11
        )


    # -----------------------------------------------------
    # Photograph
    # -----------------------------------------------------

    insert_image(
        page,
        IMAGE_PATH,
        ORIGINAL_PHOTO_TOP_LEFT,
        ORIGINAL_PHOTO_BOTTOM_RIGHT
    )


# =========================================================
# PAGE 4
# =========================================================

def fill_page_4(
    page,
    data
):

    # Page 4 contains instructions.
    #
    # No student-specific information is inserted.

    pass


# =========================================================
# GENERATE PDF
# =========================================================

def generate_pdf(data):

    # =====================================================
    # CREATE OUTPUT DIRECTORY
    # =====================================================

    output_directory = os.path.dirname(
        OUTPUT_PDF
    )


    os.makedirs(
        output_directory,
        exist_ok=True
    )


    # =====================================================
    # CHECK IMAGE
    # =====================================================

    if not os.path.exists(IMAGE_PATH):

        raise FileNotFoundError(
            f"Profile image not found:\n{IMAGE_PATH}"
        )


    # =====================================================
    # OPEN PDF
    # =====================================================

    doc = pymupdf.open(
        INPUT_PDF
    )


    print(
        f"Total pages: {len(doc)}"
    )


    # =====================================================
    # PAGE 1
    # =====================================================

    print(
        "Filling Page 1..."
    )

    fill_page_1(
        doc[0],
        data
    )


    # =====================================================
    # PAGE 2
    # =====================================================

    print(
        "Filling Page 2..."
    )

    fill_page_2(
        doc[1],
        data
    )


    # =====================================================
    # PAGE 3
    # =====================================================

    print(
        "Filling Page 3..."
    )

    fill_page_3(
        doc[2],
        data
    )


    # =====================================================
    # PAGE 4
    # =====================================================

    print(
        "Page 4 unchanged."
    )

    fill_page_4(
        doc[3],
        data
    )


    # =====================================================
    # SAVE PDF
    # =====================================================

    doc.save(
        OUTPUT_PDF
    )


    # =====================================================
    # CLOSE PDF
    # =====================================================

    doc.close()


    # =====================================================
    # SUCCESS
    # =====================================================

    print()
    print("========================================")
    print("PDF GENERATED SUCCESSFULLY")
    print("========================================")
    print(
        f"Output: {OUTPUT_PDF}"
    )
    print("========================================")
    print()


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    # =====================================================
    # LOAD JSON
    # =====================================================

    data = load_data(
        JSON_FILE
    )


    # =====================================================
    # GENERATE PDF
    # =====================================================

    generate_pdf(
        data
    )