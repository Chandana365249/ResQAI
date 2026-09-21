"""
api/schemas/responses.py

Public REST response contract (snake_case JSON). These models are the
API's own; src/api/mapping.py adapts the internal UnifiedResQAIResult
dataclasses into them so the domain model can change without silently
changing the public contract.

The analysis response keeps the ResQAI separation of concerns visible:
what the report said (explanation.report_facts), what was extracted
(extracted_information + evidence), what the model predicted
(ml_prediction), what rules detected (risk_indicators, decision), what
resources were matched (resources), and what needs a human (warnings,
human_oversight_required).
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, JsonValue

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorDetail(BaseModel):
    field: Optional[str] = Field(default=None, description="Request field the problem relates to, if any.")
    message: str


class ErrorBody(BaseModel):
    code: str = Field(description="Stable machine-readable error code, e.g. INVALID_REPORT.")
    message: str
    request_id: str
    details: Optional[List[ErrorDetail]] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


# ---------------------------------------------------------------------------
# Analysis response
# ---------------------------------------------------------------------------


class ReportMeta(BaseModel):
    report_id: str
    source: Optional[str] = None
    timestamp: Optional[str] = None


class IncidentSummary(BaseModel):
    incident_type: str
    incident_subtype: Optional[str] = None
    overall_extraction_confidence: Literal["high", "medium", "low"] = Field(
        description="Coarse rule-based extraction confidence category -- NOT a calibrated probability."
    )


class ExtractedFieldOut(BaseModel):
    value: JsonValue = None
    certainty: Literal["confirmed", "possible", "uncertain", "not_mentioned"]


class EvidenceItem(BaseModel):
    field: str
    value: JsonValue = None
    certainty: Literal["confirmed", "possible", "uncertain", "not_mentioned"]
    evidence: Optional[str] = Field(default=None, description="The report text snippet that supports this field.")


class RiskIndicatorOut(BaseModel):
    name: str
    level: Literal["critical", "high", "moderate", "low"]
    certainty: Literal["confirmed", "possible", "uncertain", "not_mentioned"]
    evidence: Optional[str] = None
    explanation: str


class MlPredictionOut(BaseModel):
    available: bool = Field(description="False when no legitimate prediction could be made. This is not an API error.")
    prediction_source: Literal["phase1_historical_model", "report_compatible_model", "none"]
    predicted_class: Optional[int] = None
    predicted_label: Optional[str] = None
    probabilities: Optional[Dict[str, float]] = Field(
        default=None,
        description="Model-reported class probabilities. Not a confidence statement about the real incident.",
    )
    features_used: List[str] = Field(default_factory=list)
    model_name: str = ""
    model_version: str = ""
    prediction_note: Optional[str] = Field(default=None, description="Why this model (or no model) was used.")
    warnings: List[str] = Field(default_factory=list)


class ReadinessOut(BaseModel):
    status: Literal["ready", "partial", "unavailable"]
    mapped_features: List[str] = Field(default_factory=list)
    missing_features: List[str] = Field(default_factory=list)
    unsupported_features: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class PredictionReadinessOut(BaseModel):
    historical_model: ReadinessOut = Field(description="Readiness for the original Phase 1 model (always evaluated first).")
    report_compatible_model: Optional[ReadinessOut] = Field(
        default=None, description="Readiness for the fallback model; null if the fallback was not needed."
    )


class DecisionOut(BaseModel):
    priority: Literal["P0", "P1", "P2", "P3"]
    risk_level: Literal["critical", "high", "moderate", "low"]
    recommended_response_categories: List[str]
    reasons: List[str]


class LocationOut(BaseModel):
    available: bool
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    reason: Optional[str] = Field(default=None, description="Why location is unavailable, when it is.")


class ResourceRecommendationOut(BaseModel):
    resource_id: str
    resource_type: str
    resource_name: str
    distance_km: Optional[float] = None
    availability: str
    capabilities: List[str]
    reason: str
    demo_only: bool


class ResourceSearchOut(BaseModel):
    category: str
    resource_available: bool
    reason: Optional[str] = None
    recommendations: List[ResourceRecommendationOut] = Field(default_factory=list)


class ResourcesSection(BaseModel):
    demo_only: Literal[True] = True
    notice: str
    location: LocationOut
    searches: List[ResourceSearchOut]


class ExplanationOut(BaseModel):
    report_facts: List[str]
    risk_reasons: List[str]
    ml_reasons: List[str]
    resource_reasons: List[str]


class AnalyzeResponse(BaseModel):
    request_id: str
    processing_time_ms: float = Field(description="Measured wall-clock time spent analysing this request.")
    report: ReportMeta
    incident: IncidentSummary
    extracted_information: Dict[str, Dict[str, ExtractedFieldOut]] = Field(
        description="Only fields the report actually mentioned, grouped by topic (people, vehicles, fire, ...)."
    )
    evidence: List[EvidenceItem]
    risk_indicators: List[RiskIndicatorOut]
    ml_prediction: MlPredictionOut
    prediction_readiness: PredictionReadinessOut
    decision: DecisionOut
    resources: ResourcesSection
    explanation: ExplanationOut
    model_rule_disagreement: Optional[str] = Field(
        default=None, description="Set when the ML prediction and rule-based risk level disagree. Never auto-resolved."
    )
    warnings: List[str]
    human_oversight_required: Literal[True] = True
    disclaimer: str


# ---------------------------------------------------------------------------
# Health / readiness
# ---------------------------------------------------------------------------


class ComponentHealth(BaseModel):
    status: Literal["ok", "available", "unavailable"]
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded", "unavailable"]
    service: str
    version: str
    environment: str
    components: Dict[str, ComponentHealth]


class ReadinessResponse(BaseModel):
    status: Literal["READY", "NOT_READY"]
    service: str
    version: str
    reasons: List[str] = Field(default_factory=list, description="Why the service is NOT_READY, if it is.")
    components: Dict[str, ComponentHealth]


# ---------------------------------------------------------------------------
# Resources / models
# ---------------------------------------------------------------------------


class DemoResourceOut(BaseModel):
    resource_id: str
    resource_type: str
    resource_name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    availability_status: str
    capacity: Optional[int] = None
    capabilities: List[str]
    demo_only: bool


class ResourceCatalogResponse(BaseModel):
    demo_only: Literal[True] = True
    notice: str
    count: int
    resources: List[DemoResourceOut]


class ModelInfoOut(BaseModel):
    source_id: Literal["phase1_historical_model", "report_compatible_model"]
    display_name: str
    role: str
    description: str
    target: str
    target_labels: Dict[str, str]
    available: bool
    model_type: Optional[str] = None
    feature_count: int
    training_dataset: str
    limitations: List[str]


class ModelsResponse(BaseModel):
    models: List[ModelInfoOut]
    routing: str = Field(description="How the analysis endpoint chooses between the models.")
