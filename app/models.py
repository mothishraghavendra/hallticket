"""
Pydantic request / response models for the Hall-Ticket Generator API.

These models mirror the data structure that main.py / index.json expect,
so the API layer can validate and forward data without any transformation.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# =========================================================
# SUB-MODELS
# =========================================================

class StudentModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, examples=["K Mothish Raghavendra"])
    father_name: str = Field(..., min_length=1, max_length=120, examples=["K Padmanabha Naidu"])
    gender: Literal["Male", "Female"] = Field(..., examples=["Male", "Female"])
    hall_ticket: str = Field(
        ...,
        min_length=1,
        max_length=10,
        examples=["24005A0512"],
        description="Exactly 10 characters; one character per box.",
    )
    type: str = Field(..., examples=["Regular"], description="Regular or Supplementary")

    @field_validator("name", "father_name", mode="before")
    @classmethod
    def title_case_names(cls, value: str) -> str:
        return value.strip().title() if isinstance(value, str) else value

    @field_validator("hall_ticket")
    @classmethod
    def validate_hall_ticket_length(cls, v: str) -> str:
        if len(v) > 10:
            raise ValueError("hall_ticket must not exceed 10 characters.")
        return v


class AcademicModel(BaseModel):
    branch: str = Field(..., min_length=1, max_length=100, examples=["Computer Science and Engineering"])
    year: str = Field(..., min_length=1, max_length=10, examples=["IV"])
    semester: str = Field(..., min_length=1, max_length=5, examples=["I"])


class ExaminationModel(BaseModel):
    month_year: str = Field(..., min_length=1, max_length=30, examples=["October 2026"])


class SubjectModel(BaseModel):
    number: int = Field(..., ge=1, examples=[1])
    name: str = Field(..., min_length=1, max_length=120, examples=["Deep Learning"])

    @field_validator("name", mode="before")
    @classmethod
    def title_case_name(cls, value: str) -> str:
        return value.strip().title() if isinstance(value, str) else value


class CertificateModel(BaseModel):
    name: str = Field(..., min_length=1, max_length=120, examples=["K Mothish Raghavendra"])
    date: str = Field(..., min_length=1, max_length=20, examples=["2026-2027"])

    @field_validator("name", mode="before")
    @classmethod
    def title_case_name(cls, value: str) -> str:
        return value.strip().title() if isinstance(value, str) else value


# =========================================================
# ROOT REQUEST MODEL
# =========================================================

class HallTicketRequest(BaseModel):
    """
    Complete request payload that the /generate endpoint accepts.

    The structure is identical to index.json so existing data can be
    sent as-is with the addition of a photo upload (multipart/form-data).
    """

    student: StudentModel
    academic: AcademicModel
    examination: ExaminationModel
    subjects: List[SubjectModel] = Field(
        ...,
        min_length=1,
        max_length=7,
        description="Between 1 and 7 subjects.",
    )
    certificate: CertificateModel

    model_config = {
        "json_schema_extra": {
            "example": {
                "student": {
                    "name": "K Mothish Raghavendra",
                    "father_name": "K Padmanabha Naidu",
                    "gender": "Male",
                    "hall_ticket": "24005A0512",
                    "type": "Regular",
                },
                "academic": {
                    "branch": "Computer Science and Engineering",
                    "year": "IV",
                    "semester": "I",
                },
                "examination": {"month_year": "October 2026"},
                "subjects": [
                    {"number": 1, "name": "Deep Learning"},
                    {"number": 2, "name": "Management Science"},
                ],
                "certificate": {
                    "name": "K Mothish Raghavendra",
                    "date": "2026-2027",
                },
            }
        }
    }


# =========================================================
# RESPONSE MODELS
# =========================================================

class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str = "ok"
    message: Optional[str] = None
