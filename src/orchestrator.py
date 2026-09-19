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
from typing import List, Optional

from .decision_engine import make_decision
from .extraction.base import BaseReportExtractor
from .location_engine import LocationAssessment, assess_incident_location
from .ml_adapter import AdapterResult, FeatureMapping, PredictionReadiness, ReadinessStatus, adapt_incident_to_ml_features
from .report_parser import parse_report
from .resource_engine import ResourceSearchResult, find_resources_for_categories
from .schemas import DecisionResult, IncidentReport, RiskIndicator
from .severity_predictor import SeverityPredictor, SeverityPrediction

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
    ml_feature_mappings: List[FeatureMapping]
    prediction_readiness: PredictionReadiness
    location_assessment: LocationAssessment
    resource_recommendations: List[ResourceSearchResult]
    explanation: ExplanationBundle
    audit: AuditRecord
    warnings: List[str] = field(default_factory=list)
    disagreement_warning: Optional[str] = None
    human_oversight_required: bool = True  # always True -- ResQAI is a decision-support prototype, never autonomous


_default_predictor: Optional[SeverityPredictor] = None


def _get_default_predictor() -> SeverityPredictor:
    """A single, lazily-created, reused SeverityPredictor (Phase 3R: avoid
    re-loading the ~84MB model artifact on every call).
    """
    global _default_predictor
    if _default_predictor is None:
        _default_predictor = SeverityPredictor()
    return _default_predictor


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
                        resource_results: List[ResourceSearchResult]) -> ExplanationBundle:
    ml_reasons: List[str]
    if ml_result.available:
        ml_reasons = [f"Phase 1 model predicted '{ml_result.predicted_label}' (class {ml_result.predicted_class})."]
        ml_reasons.extend(ml_result.warnings)
    else:
        ml_reasons = list(ml_result.warnings) or [
            "Phase 1 severity prediction was not generated because the report does not "
            "provide enough compatible features for the trained model."
        ]

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
) -> UnifiedResQAIResult:
    """Run the full ResQAI Phase 3 analysis pipeline on one report.

    Coordinates, in order: Phase 2 parsing (which already runs the risk
    engine and decision engine internally -- see report_parser.py),
    the Phase 1 feature adapter + model wrapper, the location engine,
    and the resource engine. Raises schemas.ReportValidationError if
    the input itself is invalid (propagated from parse_report).
    """
    logger.info("Running unified ResQAI analysis for report_id=%s", report_id)

    incident, decision = parse_report(report_id, raw_text, latitude, longitude, timestamp, source, extractor)

    adapter_result = adapt_incident_to_ml_features(incident)
    predictor = severity_predictor or _get_default_predictor()
    if adapter_result.feature_row is not None:
        ml_result = predictor.predict(adapter_result.feature_row)
    else:
        ml_result = SeverityPrediction(
            available=False,
            warnings=[
                "Phase 1 severity prediction was not generated because the report does not "
                "provide enough compatible features for the trained model."
            ],
        )

    location_assessment = assess_incident_location(incident.latitude, incident.longitude)
    category_values = [c.value for c in decision.recommended_response_categories]
    resource_results = find_resources_for_categories(category_values, location_assessment.coordinates)

    disagreement = _detect_disagreement(ml_result, decision)

    warnings: List[str] = []
    warnings.extend(adapter_result.readiness.warnings)
    warnings.extend(w for w in ml_result.warnings if ml_result.available)  # non-available case already explained in ml_reasons
    if location_assessment.reason and not location_assessment.available:
        warnings.append(f"Location: {location_assessment.reason}")
    for result in resource_results:
        if not result.resource_available and result.reason:
            warnings.append(f"Resources [{result.category}]: {result.reason}")
    if disagreement:
        warnings.append(disagreement)

    explanation = _build_explanation(incident, decision, ml_result, resource_results)
    audit = _build_audit(incident, decision, adapter_result, ml_result, resource_results, warnings)

    return UnifiedResQAIResult(
        report_id=report_id,
        incident=incident,
        risk_indicators=incident.risk_indicators,
        priority_decision=decision,
        ml_prediction=ml_result,
        ml_feature_mappings=adapter_result.mappings,
        prediction_readiness=adapter_result.readiness,
        location_assessment=location_assessment,
        resource_recommendations=resource_results,
        explanation=explanation,
        audit=audit,
        warnings=warnings,
        disagreement_warning=disagreement,
        human_oversight_required=True,
    )
