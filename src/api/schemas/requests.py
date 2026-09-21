"""
api/schemas/requests.py

Public REST request contract for POST /api/v1/analyze. Deliberately
separate from the internal dataclasses in src/schemas.py so the public
contract can stay stable while the domain model evolves.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ...schemas import MAX_RAW_TEXT_LENGTH  # single source for the text-length limit

MAX_REPORT_ID_LENGTH = 100
MAX_SOURCE_LENGTH = 50
MAX_TIMESTAMP_LENGTH = 64


class AnalyzeRequest(BaseModel):
    """One emergency report to analyze."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "report_id": "demo-001",
                    "raw_text": (
                        "Two vehicles collided at an intersection during heavy rain. "
                        "Four people appear injured. One person may be unconscious. "
                        "Traffic is blocked."
                    ),
                    "latitude": 39.10,
                    "longitude": -94.58,
                    "timestamp": "2026-09-19T10:30:00+05:30",
                    "source": "demo",
                }
            ]
        },
    )

    report_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=MAX_REPORT_ID_LENGTH,
        pattern=r"^[A-Za-z0-9._:\-]+$",
        description="Caller-supplied report identifier. If omitted, the API's request_id is used.",
    )
    raw_text: str = Field(
        min_length=1,
        max_length=MAX_RAW_TEXT_LENGTH,
        description="The free-text emergency report. Surrounding whitespace is trimmed.",
    )
    latitude: Optional[float] = Field(
        default=None, ge=-90.0, le=90.0, allow_inf_nan=False,
        description="Incident latitude in decimal degrees. Provide together with longitude.",
    )
    longitude: Optional[float] = Field(
        default=None, ge=-180.0, le=180.0, allow_inf_nan=False,
        description="Incident longitude in decimal degrees. Provide together with latitude.",
    )
    timestamp: Optional[str] = Field(
        default=None,
        max_length=MAX_TIMESTAMP_LENGTH,
        description="ISO-8601 timestamp of the report/incident, e.g. 2026-09-19T10:30:00+05:30.",
    )
    source: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=MAX_SOURCE_LENGTH,
        pattern=r"^[A-Za-z0-9 ._:\-]+$",
        description="Free-form label for where the report came from (e.g. 'demo').",
    )

    @field_validator("timestamp")
    @classmethod
    def _timestamp_must_be_iso8601(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("timestamp must be a valid ISO-8601 date-time string.") from exc
        return value  # returned unchanged -- validated, never rewritten

    @model_validator(mode="after")
    def _coordinates_come_as_a_pair(self) -> "AnalyzeRequest":
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be provided together, or both omitted.")
        return self
