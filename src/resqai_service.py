"""
resqai_service.py

The single, clean public entry point Phase 3 exposes:

    analyze_emergency_report(report_id, raw_text, ...) -> UnifiedResQAIResult

A future API layer (Phase 4) should only ever need to call this one
function. It does not need to know about regex extraction rules, model
file paths, feature-mapping internals, or resource-ranking details --
all of that stays inside orchestrator.py and the modules it coordinates.

Also provides a CLI demo:

    python -m src.resqai_service
"""

from __future__ import annotations

import logging
from typing import List, Optional

from .orchestrator import UnifiedResQAIResult, run_unified_analysis
from .extraction.base import BaseReportExtractor
from .resource_engine import Resource
from .severity_predictor import SeverityPredictor

logger = logging.getLogger(__name__)


def analyze_emergency_report(
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
    """Analyze one emergency report end-to-end.

    Raises schemas.ReportValidationError if raw_text/report_id are
    invalid. `extractor` and `severity_predictor` are optional
    injection points (e.g. for tests, or a future LLM-based extractor)
    -- omit both for normal use. `resource_catalog` is an optional
    pre-loaded demo catalog (used by the Phase 4 API to avoid re-reading the
    CSV per request); omit it and the catalog is loaded per call as before.
    """
    return run_unified_analysis(
        report_id, raw_text, latitude, longitude, timestamp, source,
        extractor, severity_predictor, resource_catalog,
    )


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------

_DEMO_SCENARIOS = [
    (
        "svc-demo-1-minor-collision",
        "A car hit a parked vehicle in a parking lot. No injuries were reported.",
        None, None, None,
    ),
    (
        "svc-demo-2-severe-collision",
        "Two cars collided at a highway intersection during heavy rain. "
        "Four people appear injured. One person may be unconscious. "
        "Traffic is completely blocked.",
        39.10, -94.58, None,
    ),
    (
        "svc-demo-3-fire-trapped",
        "A building is on fire and people may be trapped inside. Heavy smoke is visible.",
        39.12, -94.60, None,
    ),
    (
        "svc-demo-4-hazmat",
        "A tanker truck overturned on the highway and a fuel spill is spreading. "
        "A gas leak is also suspected near the scene.",
        39.03, -94.51, None,
    ),
    (
        "svc-demo-5-missing-location",
        "A truck rolled over on the road. The driver appears trapped.",
        None, None, None,
    ),
    (
        # Phase 3.5: exercises the newly-unlocked pedestrian/speeding/
        # hit-and-run/vehicle-age mappings. A timestamp is supplied so
        # ml_adapter.py can compute avg_vehicle_age_years (it deliberately
        # never falls back to the wall-clock "now" -- see ml_adapter.py).
        "svc-demo-6-pedestrian-speeding-hitrun",
        "Two vehicles crashed on a wet highway at an intersection. "
        "A pedestrian was struck. The driver was reportedly speeding "
        "and fled the scene. One vehicle was a 2018 model.",
        39.10, -94.58, "2026-06-15T14:30:00",
    ),
]


def _print_result(result: UnifiedResQAIResult) -> None:
    print("=" * 88)
    print(f"REPORT ID: {result.report_id}")

    print("\nRAW REPORT")
    print(f'  "{result.incident.raw_text}"')

    print("\nSTRUCTURED INCIDENT")
    print(f"  incident_type: {result.incident.incident_type.value}"
          f"{' (' + result.incident.incident_subtype + ')' if result.incident.incident_subtype else ''}")
    for span in result.incident.extraction_evidence:
        print(f"    {span.field:<22}: {span.value}  [{span.certainty.value}]")

    print("\nRISK INDICATORS")
    if not result.risk_indicators:
        print("  (none identified)")
    for ind in result.risk_indicators:
        print(f"  - {ind.name} [{ind.category.value}, {ind.certainty.value}]: {ind.explanation}")

    print("\nML FEATURE MAPPING")
    mapped = [m for m in result.ml_feature_mappings if m.mapped]
    if not mapped:
        print("  (no Phase 1 features could be mapped from this report)")
    for m in mapped:
        print(f"  {m.feature_name:<24} = {m.value!r:<22} [{m.mapping_type}, {m.certainty.value}]")

    print("\nPREDICTION READINESS")
    print(f"  Model A (phase1_historical_model): {result.prediction_readiness.status.value}"
          f"  mapped={len(result.prediction_readiness.mapped_features)}"
          f"  missing={len(result.prediction_readiness.missing_features)}"
          f"  unsupported={len(result.prediction_readiness.unsupported_features)}")
    if result.report_compatible_readiness is not None:
        print(f"  Model B (report_compatible_model):  {result.report_compatible_readiness.status.value}"
              f"  mapped={len(result.report_compatible_readiness.mapped_features)}"
              f" ({result.report_compatible_readiness.mapped_features})")

    print("\nML PREDICTION")
    print(f"  prediction_source: {result.ml_prediction.prediction_source or 'none'}")
    if result.prediction_note:
        print(f"  prediction_note: {result.prediction_note}")
    if result.ml_prediction.available:
        print(f"  predicted_severity: {result.ml_prediction.predicted_label} (class {result.ml_prediction.predicted_class})")
        print(f"  model: {result.ml_prediction.model_name} (version {result.ml_prediction.model_version})")
        print(f"  features_used: {result.ml_prediction.features_used}")
        if result.ml_prediction.probabilities:
            probs = ", ".join(f"{k}={v:.2f}" for k, v in result.ml_prediction.probabilities.items())
            print(f"  probabilities: {probs}")
    else:
        print("  prediction_available: false")
        for w in result.ml_prediction.warnings:
            print(f"  reason: {w}")

    print("\nOPERATIONAL PRIORITY")
    print(f"  priority: {result.priority_decision.priority.value}   risk_level: {result.priority_decision.risk_level.value}")
    categories = ", ".join(c.value for c in result.priority_decision.recommended_response_categories) or "(none)"
    print(f"  recommended_response_categories: {categories}")

    print("\nRESOURCE RECOMMENDATIONS")
    print(f"  location_available: {result.location_assessment.available}"
          f"{'' if result.location_assessment.available else f' ({result.location_assessment.reason})'}")
    any_resources = False
    for search in result.resource_recommendations:
        for rec in search.resources:
            any_resources = True
            dist = f"{rec.distance_km:.1f} km" if rec.distance_km is not None else "distance n/a"
            print(f"  - [{search.category}] {rec.resource_id} ({rec.resource_name}), {dist} -- {rec.reason}")
    if not any_resources:
        print("  (no demo resources matched)")

    print("\nEXPLANATION")
    print("  risk_reasons:")
    for r in result.explanation.risk_reasons:
        print(f"    - {r}")
    print("  ml_reasons:")
    for r in result.explanation.ml_reasons:
        print(f"    - {r}")
    print("  resource_reasons:")
    for r in result.explanation.resource_reasons:
        print(f"    - {r}")

    if result.disagreement_warning:
        print("\nMODEL/RULE DISAGREEMENT")
        print(f"  {result.disagreement_warning}")

    print("\nWARNINGS")
    if not result.warnings:
        print("  (none)")
    for w in result.warnings:
        print(f"  - {w}")

    print("\nHUMAN OVERSIGHT")
    print(f"  human_oversight_required: {result.human_oversight_required}")
    print("  ResQAI is a decision-support prototype. It does not dispatch real emergency")
    print("  services, does not perform medical diagnosis, and does not replace a trained")
    print("  human dispatcher's judgement. All demo resources above are SIMULATED.")
    print()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    print("ResQAI Phase 3 -- Unified Analysis demo\n")
    print("NOTE: resource recommendations below use a SYNTHETIC demo catalog")
    print("(data/resources/demo_resources.csv) -- not real emergency-service data.\n")
    for report_id, raw_text, lat, lon, timestamp in _DEMO_SCENARIOS:
        result = analyze_emergency_report(report_id, raw_text, latitude=lat, longitude=lon, timestamp=timestamp)
        _print_result(result)


if __name__ == "__main__":
    main()
