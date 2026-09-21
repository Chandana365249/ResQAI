"""
api/mapping.py

Pure translation of the internal `UnifiedResQAIResult` (and related
domain dataclasses) into the public API response schemas. Contains no
business logic: it does not extract, score, predict or rank anything --
it only renames, reshapes and JSON-sanitises what the ResQAI core
already produced, and never invents a value the core did not supply.
"""

from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional

from ..ml_adapter import PredictionReadiness
from ..orchestrator import UnifiedResQAIResult
from ..resource_engine import Resource
from ..schemas import _SUB_MODEL_FIELD_NAMES, ExtractedField
from .schemas.requests import AnalyzeRequest
from .schemas.responses import (
    AnalyzeResponse,
    DecisionOut,
    DemoResourceOut,
    EvidenceItem,
    ExplanationOut,
    ExtractedFieldOut,
    IncidentSummary,
    LocationOut,
    MlPredictionOut,
    PredictionReadinessOut,
    ReadinessOut,
    ReportMeta,
    ResourceRecommendationOut,
    ResourcesSection,
    ResourceSearchOut,
    RiskIndicatorOut,
)

RESOURCE_NOTICE = (
    "All resources are SIMULATED demo entries from a synthetic catalog. They are not real "
    "emergency units and carry no live availability. Entries are 'compatible demo resources', "
    "never real dispatches."
)
PROTOTYPE_NOTICE = (
    "ResQAI is a decision-support prototype: it does not dispatch emergency services, does not "
    "provide medical diagnosis or triage, and does not replace a trained human dispatcher."
)


MODEL_FAILURE_NOTICE = (
    "The selected severity model could not produce a prediction (its artifact was unavailable or "
    "inference failed). Technical details were logged server-side and are not exposed by the API."
)


def model_failed(result: UnifiedResQAIResult) -> bool:
    """True when a model was attempted (it has a source label) but produced no prediction.

    In that case the core's warning text may contain filesystem paths or exception
    messages, which the public API must not expose.
    """
    return (not result.ml_prediction.available) and result.ml_prediction.prediction_source not in ("", "none")


def _public_ml_reasons(result: UnifiedResQAIResult) -> List[str]:
    if not model_failed(result):
        return list(result.explanation.ml_reasons)
    technical = set(result.ml_prediction.warnings)
    reasons: List[str] = []
    for reason in result.explanation.ml_reasons:
        public = MODEL_FAILURE_NOTICE if reason in technical else reason
        if public not in reasons:
            reasons.append(public)
    return reasons


def _json_safe(value: object) -> object:
    """Convert an extracted value to a JSON-compatible one (never a repr of a Python object)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _extracted_information(incident) -> Dict[str, Dict[str, ExtractedFieldOut]]:
    """Group only the fields the report actually mentioned by topic (people, vehicles, ...)."""
    grouped: Dict[str, Dict[str, ExtractedFieldOut]] = {}
    for group_name in _SUB_MODEL_FIELD_NAMES:
        sub_model = getattr(incident, group_name)
        present: Dict[str, ExtractedFieldOut] = {}
        for f in dataclasses.fields(sub_model):
            value = getattr(sub_model, f.name)
            if isinstance(value, ExtractedField) and value.is_present:
                present[f.name] = ExtractedFieldOut(value=_json_safe(value.value), certainty=value.certainty.value)
        if present:
            grouped[group_name] = present
    return grouped


def _readiness_out(readiness: PredictionReadiness) -> ReadinessOut:
    return ReadinessOut(
        status=readiness.status.value,
        mapped_features=list(readiness.mapped_features),
        missing_features=list(readiness.missing_features),
        unsupported_features=list(readiness.unsupported_features),
        warnings=list(readiness.warnings),
    )


def _ml_prediction_out(result: UnifiedResQAIResult) -> MlPredictionOut:
    ml = result.ml_prediction
    return MlPredictionOut(
        available=ml.available,
        prediction_source=ml.prediction_source or "none",
        predicted_class=ml.predicted_class,
        predicted_label=ml.predicted_label,
        probabilities=ml.probabilities,
        features_used=list(ml.features_used),
        model_name=ml.model_name,
        model_version=ml.model_version,
        prediction_note=result.prediction_note,
        warnings=[MODEL_FAILURE_NOTICE] if model_failed(result) else list(ml.warnings),
    )


def _resources_section(result: UnifiedResQAIResult) -> ResourcesSection:
    loc = result.location_assessment
    coords = loc.coordinates
    return ResourcesSection(
        notice=RESOURCE_NOTICE,
        location=LocationOut(
            available=loc.available,
            latitude=coords.latitude if coords else None,
            longitude=coords.longitude if coords else None,
            reason=loc.reason,
        ),
        searches=[
            ResourceSearchOut(
                category=search.category,
                resource_available=search.resource_available,
                reason=search.reason,
                recommendations=[
                    ResourceRecommendationOut(
                        resource_id=rec.resource_id, resource_type=rec.resource_type,
                        resource_name=rec.resource_name, distance_km=rec.distance_km,
                        availability=rec.availability, capabilities=list(rec.capabilities),
                        reason=rec.reason, demo_only=rec.demo_only,
                    )
                    for rec in search.resources
                ],
            )
            for search in result.resource_recommendations
        ],
    )


def to_analyze_response(
    result: UnifiedResQAIResult, request: AnalyzeRequest, request_id: str, processing_time_ms: float
) -> AnalyzeResponse:
    """Adapt one internal result into the public AnalyzeResponse."""
    incident = result.incident
    decision = result.priority_decision
    expl = result.explanation
    return AnalyzeResponse(
        request_id=request_id,
        processing_time_ms=processing_time_ms,
        # `source` is API-level request metadata (IncidentReport does not carry it).
        report=ReportMeta(report_id=result.report_id, source=request.source, timestamp=incident.timestamp),
        incident=IncidentSummary(
            incident_type=incident.incident_type.value,
            incident_subtype=incident.incident_subtype,
            overall_extraction_confidence=incident.overall_extraction_confidence.value,
        ),
        extracted_information=_extracted_information(incident),
        evidence=[
            EvidenceItem(field=s.field, value=_json_safe(s.value), certainty=s.certainty.value, evidence=s.evidence)
            for s in incident.extraction_evidence
        ],
        risk_indicators=[
            RiskIndicatorOut(
                name=i.name, level=i.category.value, certainty=i.certainty.value,
                evidence=i.evidence, explanation=i.explanation,
            )
            for i in result.risk_indicators
        ],
        ml_prediction=_ml_prediction_out(result),
        prediction_readiness=PredictionReadinessOut(
            historical_model=_readiness_out(result.prediction_readiness),
            report_compatible_model=(
                _readiness_out(result.report_compatible_readiness)
                if result.report_compatible_readiness is not None else None
            ),
        ),
        decision=DecisionOut(
            priority=decision.priority.value,
            risk_level=decision.risk_level.value,
            recommended_response_categories=[c.value for c in decision.recommended_response_categories],
            reasons=list(decision.reasons),
        ),
        resources=_resources_section(result),
        explanation=ExplanationOut(
            report_facts=list(expl.report_facts), risk_reasons=list(expl.risk_reasons),
            ml_reasons=_public_ml_reasons(result), resource_reasons=list(expl.resource_reasons),
        ),
        model_rule_disagreement=result.disagreement_warning,
        warnings=list(result.warnings),
        human_oversight_required=True,
        disclaimer=f"{decision.disclaimer} {PROTOTYPE_NOTICE}",
    )


def to_demo_resource(resource: Resource) -> DemoResourceOut:
    return DemoResourceOut(
        resource_id=resource.resource_id, resource_type=resource.resource_type,
        resource_name=resource.resource_name, latitude=resource.latitude, longitude=resource.longitude,
        availability_status=resource.availability_status, capacity=resource.capacity,
        capabilities=list(resource.capabilities), demo_only=resource.demo_only,
    )


def filter_resources(
    catalog: List[Resource], resource_type: Optional[str], availability_status: Optional[str]
) -> List[Resource]:
    """Exact (case-insensitive) attribute filters over the already-loaded demo catalog."""
    selected = catalog
    if resource_type:
        selected = [r for r in selected if r.resource_type.lower() == resource_type.lower()]
    if availability_status:
        selected = [r for r in selected if r.availability_status.lower() == availability_status.lower()]
    return selected
