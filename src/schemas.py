"""
schemas.py

Central, typed data model for Phase 2 (Emergency Report Intelligence).

Everything downstream of raw text -- normalization, extraction, risk
indicators, decision rules -- reads and writes these types, so this
module has no dependencies on any other Phase 2 module. It uses
stdlib `dataclasses` (not Pydantic) to avoid adding a new third-party
dependency for something the standard library already does well; the
validation this project needs (non-empty text, length limits, simple
type checks) does not require a schema-validation framework.

Design notes
------------
- Every extracted attribute is wrapped in `ExtractedField`, which
  carries not just a value but also *how sure* the extractor was
  (`Certainty`) and *what text supports it* (`evidence`). This is
  what makes the system able to answer "why did you extract this?"
  (requirement: evidence/provenance) and stops uncertain statements
  ("may be unconscious") from silently becoming confirmed facts.
- `Optional`/`None` is used for "not known" everywhere. This project
  deliberately never uses sentinel placeholder values such as -1,
  "unknown", or 999 to mean "missing" -- that hides missingness
  behind a fake value and is a common source of silent bugs.
- Nested dataclasses (PeopleInfo, VehicleInfo, ...) group related
  attributes instead of one 30+ field flat object, matching the
  Phase 2 design brief.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, List, Optional, TypeVar

# ---------------------------------------------------------------------------
# Shared enums
# ---------------------------------------------------------------------------


class Certainty(str, Enum):
    """How confident the extractor is that an attribute's value is correct.

    This is a *rule-based extraction* certainty, not a calibrated
    statistical probability -- see docs/REPORT_INTELLIGENCE.md,
    "Confidence" section, for the documented limitation.
    """

    CONFIRMED = "confirmed"        # stated plainly, no hedging or negation
    POSSIBLE = "possible"          # softly hedged ("may be", "appears to")
    UNCERTAIN = "uncertain"        # strongly hedged ("unclear if", "not sure")
    NOT_MENTIONED = "not_mentioned"  # the report says nothing about this


class IncidentType(str, Enum):
    """Controlled incident taxonomy.

    Deliberately small and flat so new categories can be appended
    without changing any code that consumes this enum (extraction,
    risk rules, and decision rules all switch on the enum value, not
    on a hard-coded position or count).
    """

    VEHICLE_COLLISION = "vehicle_collision"
    FIRE = "fire"
    MEDICAL_EMERGENCY = "medical_emergency"
    HAZARDOUS_MATERIAL = "hazardous_material"
    NATURAL_DISASTER = "natural_disaster"
    STRUCTURAL_INCIDENT = "structural_incident"
    ROAD_OBSTRUCTION = "road_obstruction"
    OTHER = "other"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    """Coarse, interpretable stand-in for a calibrated confidence score."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Priority(str, Enum):
    """Project-defined prototype priority levels.

    These are NOT validated emergency-service dispatch standards --
    see the disclaimer carried on every DecisionResult.
    """

    P0 = "P0"  # highest
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"  # lowest


class RiskLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"


class ResponseCategory(str, Enum):
    """Recommended response CATEGORIES -- not autonomous dispatch commands."""

    AMBULANCE = "ambulance"
    FIRE_RESPONSE = "fire_response"
    POLICE_RESPONSE = "police_response"
    TRAFFIC_MANAGEMENT = "traffic_management"
    HAZARDOUS_MATERIAL_RESPONSE = "hazardous_material_response"
    EVACUATION_CONSIDERATION = "evacuation_consideration"


# ---------------------------------------------------------------------------
# Evidence / provenance
# ---------------------------------------------------------------------------

T = TypeVar("T")


@dataclass
class ExtractedField(Generic[T]):
    """A single extracted attribute, with certainty and supporting evidence.

    `value is None` and `certainty == NOT_MENTIONED` together mean
    "the report said nothing about this" -- never fabricated.
    """

    value: Optional[T] = None
    certainty: Certainty = Certainty.NOT_MENTIONED
    evidence: Optional[str] = None

    @property
    def is_present(self) -> bool:
        """True if the report actually said something about this field."""
        return self.certainty != Certainty.NOT_MENTIONED

    def to_evidence_span(self, field_name: str) -> Optional["EvidenceSpan"]:
        """Convert to a flat EvidenceSpan for reporting, or None if unmentioned."""
        if not self.is_present:
            return None
        return EvidenceSpan(
            field=field_name, value=self.value, certainty=self.certainty, evidence=self.evidence
        )


@dataclass
class EvidenceSpan:
    """A flattened (field, value, certainty, evidence) record.

    `IncidentReport.extraction_evidence` is a list of these, giving a
    single place to answer "why did you extract this information?"
    without having to walk every nested sub-model.
    """

    field: str
    value: object
    certainty: Certainty
    evidence: Optional[str]


# ---------------------------------------------------------------------------
# Structured incident sub-models
# ---------------------------------------------------------------------------


@dataclass
class PeopleInfo:
    people_affected: ExtractedField[int] = field(default_factory=ExtractedField)
    injuries_present: ExtractedField[bool] = field(default_factory=ExtractedField)
    injured_people: ExtractedField[int] = field(default_factory=ExtractedField)
    seriously_injured: ExtractedField[int] = field(default_factory=ExtractedField)
    unconscious_person: ExtractedField[bool] = field(default_factory=ExtractedField)
    trapped_person: ExtractedField[bool] = field(default_factory=ExtractedField)
    missing_person: ExtractedField[bool] = field(default_factory=ExtractedField)
    possible_fatality: ExtractedField[bool] = field(default_factory=ExtractedField)
    child_mentioned: ExtractedField[bool] = field(default_factory=ExtractedField)
    elderly_mentioned: ExtractedField[bool] = field(default_factory=ExtractedField)
    # Added in Phase 3.5 to unlock the Phase 1 PEDS feature (see ml_adapter.py).
    # A pedestrian is a person, so this lives here rather than in a new
    # top-level schema group -- kept minimal per the Phase 3.5 scope.
    pedestrian_involved: ExtractedField[bool] = field(default_factory=ExtractedField)
    pedestrian_count: ExtractedField[int] = field(default_factory=ExtractedField)


@dataclass
class VehicleInfo:
    vehicle_count: ExtractedField[int] = field(default_factory=ExtractedField)
    vehicle_types: ExtractedField[List[str]] = field(default_factory=ExtractedField)
    collision: ExtractedField[bool] = field(default_factory=ExtractedField)
    rollover: ExtractedField[bool] = field(default_factory=ExtractedField)
    # Added in Phase 3.5 to unlock Phase 1's any_speeding_involved,
    # any_hit_run_involved, and avg_vehicle_age_years features.
    speeding: ExtractedField[bool] = field(default_factory=ExtractedField)
    hit_and_run: ExtractedField[bool] = field(default_factory=ExtractedField)
    # The raw stated model year (e.g. 2018), not an age -- ml_adapter.py
    # computes age from this using the report's timestamp as reference
    # year, since Phase 2 stays text-focused and does not itself reason
    # about "how old is that" relative to today.
    vehicle_model_year: ExtractedField[int] = field(default_factory=ExtractedField)
    vehicle_fire: ExtractedField[bool] = field(default_factory=ExtractedField)


@dataclass
class FireInfo:
    fire_present: ExtractedField[bool] = field(default_factory=ExtractedField)
    smoke_present: ExtractedField[bool] = field(default_factory=ExtractedField)
    explosion: ExtractedField[bool] = field(default_factory=ExtractedField)
    spreading_fire: ExtractedField[bool] = field(default_factory=ExtractedField)
    building_fire: ExtractedField[bool] = field(default_factory=ExtractedField)


@dataclass
class HazmatInfo:
    chemical_spill: ExtractedField[bool] = field(default_factory=ExtractedField)
    fuel_spill: ExtractedField[bool] = field(default_factory=ExtractedField)
    gas_leak: ExtractedField[bool] = field(default_factory=ExtractedField)
    hazardous_material: ExtractedField[bool] = field(default_factory=ExtractedField)
    toxic_substance: ExtractedField[bool] = field(default_factory=ExtractedField)
    unknown_substance: ExtractedField[bool] = field(default_factory=ExtractedField)


@dataclass
class EnvironmentInfo:
    rain: ExtractedField[bool] = field(default_factory=ExtractedField)
    heavy_rain: ExtractedField[bool] = field(default_factory=ExtractedField)
    fog: ExtractedField[bool] = field(default_factory=ExtractedField)
    snow: ExtractedField[bool] = field(default_factory=ExtractedField)
    strong_wind: ExtractedField[bool] = field(default_factory=ExtractedField)
    flood: ExtractedField[bool] = field(default_factory=ExtractedField)
    poor_visibility: ExtractedField[bool] = field(default_factory=ExtractedField)
    wet_road: ExtractedField[bool] = field(default_factory=ExtractedField)
    icy_road: ExtractedField[bool] = field(default_factory=ExtractedField)
    smoke_reducing_visibility: ExtractedField[bool] = field(default_factory=ExtractedField)


@dataclass
class LocationContext:
    highway: ExtractedField[bool] = field(default_factory=ExtractedField)
    intersection: ExtractedField[bool] = field(default_factory=ExtractedField)
    bridge: ExtractedField[bool] = field(default_factory=ExtractedField)
    tunnel: ExtractedField[bool] = field(default_factory=ExtractedField)
    railway_crossing: ExtractedField[bool] = field(default_factory=ExtractedField)


@dataclass
class TrafficInfo:
    road_blockage: ExtractedField[bool] = field(default_factory=ExtractedField)
    traffic_blockage: ExtractedField[bool] = field(default_factory=ExtractedField)
    lane_blockage: ExtractedField[bool] = field(default_factory=ExtractedField)
    structural_damage: ExtractedField[bool] = field(default_factory=ExtractedField)


@dataclass
class EmergencyServicesInfo:
    ambulance_requested: ExtractedField[bool] = field(default_factory=ExtractedField)
    fire_response_requested: ExtractedField[bool] = field(default_factory=ExtractedField)
    police_response_requested: ExtractedField[bool] = field(default_factory=ExtractedField)
    evacuation_mentioned: ExtractedField[bool] = field(default_factory=ExtractedField)


@dataclass
class RiskIndicator:
    """One transparent, rule-based operational risk signal.

    This is explicitly NOT a medical triage judgement -- it flags
    *operational* signals (e.g. "a report of an unconscious person
    exists") for a human dispatcher's attention, nothing more.
    """

    name: str
    category: RiskLevel
    certainty: Certainty
    evidence: Optional[str]
    explanation: str


# ---------------------------------------------------------------------------
# Top-level report input / output
# ---------------------------------------------------------------------------

MAX_RAW_TEXT_LENGTH = 5000


class ReportValidationError(ValueError):
    """Raised when raw report input fails validation."""


@dataclass
class EmergencyReportInput:
    """Raw input accepted from a caller (CLI, future API, etc.).

    Only what is needed for parsing is kept -- no unnecessary
    personal information (e.g. no reporter name/phone field here by
    design; if a future integration needs contact info, it should be
    stored separately from the parsed incident record).
    """

    report_id: str
    raw_text: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: Optional[str] = None
    source: Optional[str] = None


def validate_report_input(
    report_id: Optional[str],
    raw_text: Optional[str],
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timestamp: Optional[str] = None,
    source: Optional[str] = None,
) -> EmergencyReportInput:
    """Validate and normalize raw caller-supplied fields into EmergencyReportInput.

    Raises ReportValidationError with a clear, developer-friendly
    message on any problem, instead of letting a malformed value
    propagate into later pipeline stages.
    """
    if report_id is None or not str(report_id).strip():
        raise ReportValidationError("report_id is required and cannot be empty.")

    if raw_text is None:
        raise ReportValidationError("raw_text is required and cannot be null.")
    if not isinstance(raw_text, str):
        raise ReportValidationError(f"raw_text must be a string, got {type(raw_text).__name__}.")

    trimmed = raw_text.strip()
    if not trimmed:
        raise ReportValidationError("raw_text cannot be empty or whitespace-only.")
    if len(trimmed) > MAX_RAW_TEXT_LENGTH:
        raise ReportValidationError(
            f"raw_text is too long ({len(trimmed)} chars); "
            f"maximum supported length is {MAX_RAW_TEXT_LENGTH} characters."
        )

    for name, coord, low, high in (
        ("latitude", latitude, -90.0, 90.0),
        ("longitude", longitude, -180.0, 180.0),
    ):
        if coord is not None:
            if not isinstance(coord, (int, float)):
                raise ReportValidationError(f"{name} must be numeric if provided.")
            if not (low <= coord <= high):
                raise ReportValidationError(f"{name}={coord} is outside the valid range [{low}, {high}].")

    return EmergencyReportInput(
        report_id=str(report_id).strip(),
        raw_text=trimmed,
        latitude=float(latitude) if latitude is not None else None,
        longitude=float(longitude) if longitude is not None else None,
        timestamp=timestamp,
        source=source,
    )


@dataclass
class IncidentReport:
    """The central structured representation produced by extraction.

    Populated by an extractor (see extraction/base.py), then enriched
    in place with risk_indicators (risk_engine.py) and
    overall_extraction_confidence before being handed to the decision
    engine.
    """

    report_id: str
    raw_text: str
    normalized_text: str

    incident_type: IncidentType
    incident_subtype: Optional[str]

    people: PeopleInfo
    vehicles: VehicleInfo
    fire: FireInfo
    hazmat: HazmatInfo
    environment: EnvironmentInfo
    location_context: LocationContext
    traffic: TrafficInfo
    emergency_services: EmergencyServicesInfo

    extraction_evidence: List[EvidenceSpan] = field(default_factory=list)
    overall_extraction_confidence: ConfidenceLevel = ConfidenceLevel.LOW
    risk_indicators: List[RiskIndicator] = field(default_factory=list)

    timestamp: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class DecisionResult:
    """Output of the Phase 2 rule-based decision engine.

    See docs/REPORT_INTELLIGENCE.md, "Safety limitations", for why
    this is explicitly a prototype, not a validated dispatch protocol.
    """

    priority: Priority
    risk_level: RiskLevel
    recommended_response_categories: List[ResponseCategory]
    reasons: List[str]
    disclaimer: str = (
        "Prototype decision-support output only. Priorities and response "
        "categories are project-defined heuristics, not validated emergency "
        "dispatch standards or medical triage. A qualified human must review "
        "and make all real dispatch decisions."
    )


# Re-exported here so callers of schemas.py have a single import for the
# whitespace-collapsing helper used when building short evidence snippets.
def collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


_SUB_MODEL_FIELD_NAMES = (
    "people", "vehicles", "fire", "hazmat",
    "environment", "location_context", "traffic", "emergency_services",
)


def build_evidence_list(report: IncidentReport) -> List[EvidenceSpan]:
    """Flatten every populated ExtractedField across an IncidentReport's
    sub-models into a single evidence list.

    Works for ANY extractor's output (deterministic or a future
    LLM-based one) since it only relies on the ExtractedField shape,
    not on how the fields were produced. This is the mechanism behind
    "why did you extract this information?" -- see IncidentReport.extraction_evidence.
    """
    evidence: List[EvidenceSpan] = []
    for sub_model_name in _SUB_MODEL_FIELD_NAMES:
        sub_model = getattr(report, sub_model_name)
        for f in dataclasses.fields(sub_model):
            value = getattr(sub_model, f.name)
            if isinstance(value, ExtractedField):
                span = value.to_evidence_span(f.name)
                if span is not None:
                    evidence.append(span)
    return evidence
