"""
orchestrator.py

The Phase 3 coordination layer. Combines Phase 2 (report parsing, risk
indicators, decision rules), Phase 1 (via ml_adapter + severity_predictor),
location_engine, and resource_engine into one `UnifiedResQAIResult` --
without duplicating any of those components' internal logic.

Design principle (Phase 3 core architectural requirement): this module
is coordination ONLY. It calls each component's public function/class
once, in order, and assembles their outputs. It contains no regex, no
risk rules, no decision-weight constants, no feature-mapping logic, no
distance math, and no resource-ranking logic of its own -- all of that
stays owned by the module that already implements it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .decision_engine import make_decision
from .extraction.base import BaseReportExtractor
from .location_engine import LocationAssessment, assess_incident_location
from .ml_adapter import AdapterResult, FeatureMapping, PredictionReadiness, ReadinessStatus, adapt_incident_to_ml_features
from .report_model_adapter import adapt_incident_to_report_compatible_features
from .report_parser import parse_report
from .resource_engine import Resource, ResourceSearchResult, find_resources_for_categories
from .schemas import DecisionResult, IncidentReport, RiskIndicator
from .severity_predictor import SeverityPredictor, SeverityPrediction

REPORT_COMPATIBLE_MODEL_PATH = Path("models/report_compatible_random_forest.joblib")
REPORT_COMPATIBLE_METADATA_PATH = Path("artifacts/report_compatible_feature_metadata.json")

# Step 14 routing explanations -- shown verbatim in UnifiedResQAIResult.prediction_note.
_NOTE_USED_REPORT_COMPATIBLE_MODEL = (
    "Original Phase 1 model required unavailable numeric features; a separately "
    "trained report-compatible model was used with only features supported by "
    "the emergency-report extraction layer."
)
_NOTE_NO_MODEL_AVAILABLE = (
    "Neither the original Phase 1 model nor the report-compatible model had "
    "enough report-observable information to produce a severity prediction."
)

logger = logging.getLogger(__name__)

# Ordinal bands used ONLY to detect a disagreement worth flagging to a
# human reviewer (Phase 3L) -- never to let one component silently
# override the other. MAX_SEV classes 0-1 ("no apparent"/"possible
# injury") are treated as the LOW/MODERATE band; 3-4 ("suspected
# serious"/"fatal") as the HIGH/CRITICAL band; class 2 is treated as a
# middle ground that does not, by itself, count as disagreeing with
# either rule-based band.
_ML_LOW_SEVERITY_CLASSES = {0, 1}
_ML_HIGH_SEVERITY_CLASSES = {3, 4}
_RULE_LOW_RISK_LEVELS = {"low", "moderate"}
_RULE_HIGH_RISK_LEVELS = {"high", "critical"}


@dataclass
class ExplanationBundle:
    report_facts: List[str] = field(default_factory=list)
    risk_reasons: List[str] = field(default_factory=list)
    ml_reasons: List[str] = field(default_factory=list)
    resource_reasons: List[str] = field(default_factory=list)


@dataclass
class AuditRecord:
    """Internal analysis record (Phase 3M). Deliberately excludes raw/normalized
    report text -- see docs/PHASE3_INTEGRATION.md, "Privacy considerations".
    """

    report_id: str
    incident_type: str
    extraction_evidence_count: int
    mapped_ml_features: List[str]
    missing_ml_features: List[str]
    unsupported_ml_features: List[str]
    ml_prediction_available: bool
    ml_predicted_class: Optional[int]
    ml_prediction_source: str
    risk_indicator_names: List[str]
    priority: str
    selected_resource_ids: List[str]
    warning_count: int


@dataclass
class UnifiedResQAIResult:
    report_id: str
    incident: IncidentReport
    risk_indicators: List[RiskIndicator]
    priority_decision: DecisionResult
    ml_prediction: SeverityPrediction
    # Model A (Phase 1 historical model) mapping/readiness -- always
    # computed, since routing always tries Model A first (see
    # _route_ml_prediction). Kept under these original field names for
    # backward compatibility with Phase 3 code/tests.
    ml_feature_mappings: List[FeatureMapping]
    prediction_readiness: PredictionReadiness
    location_assessment: LocationAssessment
    resource_recommendations: List[ResourceSearchResult]
    explanation: ExplanationBundle
    audit: AuditRecord
    warnings: List[str] = field(default_factory=list)
    disagreement_warning: Optional[str] = None
    # Model B (report-compatible model) mapping/readiness -- only computed
    # (non-None) when Model A's readiness was UNAVAILABLE and routing fell
    # through to Model B. See ml_prediction.prediction_source for which
    # model's output (if either) is in `ml_prediction` above.
    report_compatible_feature_mappings: Optional[List[FeatureMapping]] = None
    report_compatible_readiness: Optional[PredictionReadiness] = None
    prediction_note: Optional[str] = None
    human_oversight_required: bool = True  # always True -- ResQAI is a decision-support prototype, never autonomous


_default_predictor: Optional[SeverityPredictor] = None


def _get_default_predictor() -> SeverityPredictor:
    """A single, lazily-created, reused SeverityPredictor for MODEL A, the
    original Phase 1 historical model (Phase 3R: avoid re-loading the
    ~84MB model artifact on every call).
    """
    global _default_predictor
    if _default_predictor is None:
        _default_predictor = SeverityPredictor(source_label="phase1_historical_model")
    return _default_predictor


_default_report_compatible_predictor: Optional[SeverityPredictor] = None


def _get_default_report_compatible_predictor() -> SeverityPredictor:
    """Lazily-created, reused SeverityPredictor for MODEL B (Phase 3.5's
    report-compatible model -- see train_report_compatible_model.py).
    Reuses the SAME SeverityPredictor class as Model A; only the artifact
    path, feature metadata path, and source_label differ.
    """
    global _default_report_compatible_predictor
    if _default_report_compatible_predictor is None:
        _default_report_compatible_predictor = SeverityPredictor(
            model_path=REPORT_COMPATIBLE_MODEL_PATH,
            feature_metadata_path=REPORT_COMPATIBLE_METADATA_PATH,
            source_label="report_compatible_model",
        )
    return _default_report_compatible_predictor


def get_default_predictors() -> Dict[str, SeverityPredictor]:
    """Public accessor for the two process-wide predictors, keyed by their
    `prediction_source` label. Added in Phase 4 so an application layer (the
    FastAPI backend) can warm the models at startup and report their status
    without reaching into this module's private helpers. Returns the SAME
    singletons run_unified_analysis uses, so nothing is loaded twice.
    """
    return {
        "phase1_historical_model": _get_default_predictor(),
        "report_compatible_model": _get_default_report_compatible_predictor(),
    }


def _route_ml_prediction(
    incident: IncidentReport, phase1_predictor: SeverityPredictor, report_predictor: SeverityPredictor,
):
    """Step 14 routing: try Model A first; fall back to Model B only when
    Model A is genuinely UNAVAILABLE (never because Model A's requirements
    were weakened -- see ml_adapter.py, unchanged by this function).

    Returns (ml_result, model_a_adapter_result, model_b_adapter_result_or_None, prediction_note_or_None).
    """
    model_a_result = adapt_incident_to_ml_features(incident)
    if model_a_result.feature_row is not None:
        ml_result = phase1_predictor.predict(model_a_result.feature_row)
        return ml_result, model_a_result, None, None

    model_b_result = adapt_incident_to_report_compatible_features(incident)
    if model_b_result.feature_row is not None:
        ml_result = report_predictor.predict(model_b_result.feature_row)
        return ml_result, model_a_result, model_b_result, _NOTE_USED_REPORT_COMPATIBLE_MODEL

    ml_result = SeverityPrediction(
        available=False, prediction_source="none", warnings=[_NOTE_NO_MODEL_AVAILABLE]
    )
    return ml_result, model_a_result, model_b_result, _NOTE_NO_MODEL_AVAILABLE


def _detect_disagreement(ml_result: SeverityPrediction, decision: DecisionResult) -> Optional[str]:
    """Flag (never resolve) a mismatch between the ML prediction and the
    rule-based risk_level. Both remain visible in the result either way.
    """
    if not ml_result.available or ml_result.predicted_class is None:
        return None
    risk_level = decision.risk_level.value
    if ml_result.predicted_class in _ML_LOW_SEVERITY_CLASSES and risk_level in _RULE_HIGH_RISK_LEVELS:
        return (
            f"Model prediction ('{ml_result.predicted_label}') and rule-based operational risk "
            f"(risk_level='{risk_level}') differ; human review is required."
        )
    if ml_result.predicted_class in _ML_HIGH_SEVERITY_CLASSES and risk_level in _RULE_LOW_RISK_LEVELS:
        return (
            f"Model prediction ('{ml_result.predicted_label}') and rule-based operational risk "
            f"(risk_level='{risk_level}') differ; human review is required."
        )
    return None


def _build_explanation(incident: IncidentReport, decision: DecisionResult, ml_result: SeverityPrediction,
                        resource_results: List[ResourceSearchResult], prediction_note: Optional[str] = None
                        ) -> ExplanationBundle:
    ml_reasons: List[str]
    if ml_result.available:
        source_label = {
            "phase1_historical_model": "Phase 1 historical model",
            "report_compatible_model": "report-compatible model",
        }.get(ml_result.prediction_source, ml_result.prediction_source or "model")
        ml_reasons = [f"{source_label} predicted '{ml_result.predicted_label}' (class {ml_result.predicted_class})."]
        ml_reasons.extend(ml_result.warnings)
    else:
        ml_reasons = list(ml_result.warnings) or [
            "No severity prediction was generated because the report does not provide "
            "enough compatible features for either trained model."
        ]
    if prediction_note and prediction_note not in ml_reasons:
        ml_reasons.append(prediction_note)

    resource_reasons: List[str] = []
    for result in resource_results:
        if result.resource_available:
            resource_reasons.extend(rec.reason for rec in result.resources)
        elif result.reason:
            resource_reasons.append(f"[{result.category}] {result.reason}")

    return ExplanationBundle(
        report_facts=[incident.raw_text],
        risk_reasons=[ind.explanation for ind in incident.risk_indicators],
        ml_reasons=ml_reasons,
        resource_reasons=resource_reasons,
    )


def _build_audit(incident: IncidentReport, decision: DecisionResult, adapter_result: AdapterResult,
                  ml_result: SeverityPrediction, resource_results: List[ResourceSearchResult],
                  warnings: List[str]) -> AuditRecord:
    selected_ids = [rec.resource_id for result in resource_results for rec in result.resources]
    return AuditRecord(
        report_id=incident.report_id,
        incident_type=incident.incident_type.value,
        extraction_evidence_count=len(incident.extraction_evidence),
        mapped_ml_features=adapter_result.readiness.mapped_features,
        missing_ml_features=adapter_result.readiness.missing_features,
        unsupported_ml_features=adapter_result.readiness.unsupported_features,
        ml_prediction_available=ml_result.available,
        ml_predicted_class=ml_result.predicted_class,
        ml_prediction_source=ml_result.prediction_source or "none",
        risk_indicator_names=[ind.name for ind in incident.risk_indicators],
        priority=decision.priority.value,
        selected_resource_ids=selected_ids,
        warning_count=len(warnings),
    )


def run_unified_analysis(
    report_id: str,
    raw_text: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timestamp: Optional[str] = None,
    source: Optional[str] = None,
    extractor: Optional[BaseReportExtractor] = None,
    severity_predictor: Optional[SeverityPredictor] = None,
    resource_catalog: Optional[List[Resource]] = None,
) -> UnifiedResQAIResult:
    """Run the full ResQAI Phase 3 analysis pipeline on one report.

    `resource_catalog` is an optional, already-loaded demo catalog (Phase 4:
    lets a long-running server load the CSV once instead of per call). When
    omitted, resource_engine loads it itself, exactly as before.

    Coordinates, in order: Phase 2 parsing (which already runs the risk
    engine and decision engine internally -- see report_parser.py),
    the Phase 1 feature adapter + model wrapper, the location engine,
    and the resource engine. Raises schemas.ReportValidationError if
    the input itself is invalid (propagated from parse_report).
    """
    logger.info("Running unified ResQAI analysis for report_id=%s", report_id)

    incident, decision = parse_report(report_id, raw_text, latitude, longitude, timestamp, source, extractor)

    phase1_predictor = severity_predictor or _get_default_predictor()
    report_predictor = _get_default_report_compatible_predictor()
    ml_result, model_a_result, model_b_result, prediction_note = _route_ml_prediction(
        incident, phase1_predictor, report_predictor
    )

    location_assessment = assess_incident_location(incident.latitude, incident.longitude)
    category_values = [c.value for c in decision.recommended_response_categories]
    resource_results = find_resources_for_categories(
        category_values, location_assessment.coordinates, resource_catalog
    )

    disagreement = _detect_disagreement(ml_result, decision)

    warnings: List[str] = []
    warnings.extend(model_a_result.readiness.warnings)
    if model_b_result is not None:
        warnings.extend(model_b_result.readiness.warnings)
    warnings.extend(w for w in ml_result.warnings if ml_result.available)  # non-available case already explained in ml_reasons
    if location_assessment.reason and not location_assessment.available:
        warnings.append(f"Location: {location_assessment.reason}")
    for result in resource_results:
        if not result.resource_available and result.reason:
            warnings.append(f"Resources [{result.category}]: {result.reason}")
    if disagreement:
        warnings.append(disagreement)

    explanation = _build_explanation(incident, decision, ml_result, resource_results, prediction_note)
    audit = _build_audit(incident, decision, model_a_result, ml_result, resource_results, warnings)

    return UnifiedResQAIResult(
        report_id=report_id,
        incident=incident,
        risk_indicators=incident.risk_indicators,
        priority_decision=decision,
        ml_prediction=ml_result,
        ml_feature_mappings=model_a_result.mappings,
        prediction_readiness=model_a_result.readiness,
        report_compatible_feature_mappings=(model_b_result.mappings if model_b_result else None),
        report_compatible_readiness=(model_b_result.readiness if model_b_result else None),
        prediction_note=prediction_note,
        location_assessment=location_assessment,
        resource_recommendations=resource_results,
        explanation=explanation,
        audit=audit,
        warnings=warnings,
        disagreement_warning=disagreement,
        human_oversight_required=True,
    )
