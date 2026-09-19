"""
report_parser.py

Orchestrates the full Phase 2 pipeline:

    raw input -> validate -> normalize -> extract -> risk indicators
              -> decision engine -> (IncidentReport, DecisionResult)

This module contains the wiring only -- validation lives in
schemas.py, normalization in normalization.py, extraction in
extraction/, risk rules in risk_engine.py, and decision rules in
decision_engine.py. Keeping this file thin means each stage stays
independently testable (see tests/test_report_parser.py).

Run the CLI demo with:

    python -m src.report_parser
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from .decision_engine import make_decision
from .extraction.base import BaseReportExtractor
from .extraction.deterministic import DeterministicReportExtractor
from .normalization import normalize_text
from .risk_engine import evaluate_risk_indicators
from .schemas import (
    Certainty,
    ConfidenceLevel,
    DecisionResult,
    IncidentReport,
    IncidentType,
    validate_report_input,
)
from .utils.pii import redact_pii

logger = logging.getLogger(__name__)

# A single, stateless, reusable default extractor instance. Callers can
# pass their own (e.g. a future LLM-based one) via parse_report(extractor=...).
_DEFAULT_EXTRACTOR = DeterministicReportExtractor()


def _compute_overall_confidence(report: IncidentReport) -> ConfidenceLevel:
    """Heuristic, interpretable confidence CATEGORY for the whole extraction.

    This is a rule-of-thumb summary ("how much did we find, and how
    sure were we"), not a calibrated statistical probability -- see
    docs/REPORT_INTELLIGENCE.md, "Confidence", for the documented
    limitation this method must not be read past.
    """
    if not report.extraction_evidence:
        return ConfidenceLevel.LOW
    confirmed_count = sum(
        1 for span in report.extraction_evidence if span.certainty == Certainty.CONFIRMED
    )
    if report.incident_type != IncidentType.UNKNOWN and confirmed_count >= 3:
        return ConfidenceLevel.HIGH
    return ConfidenceLevel.MEDIUM


def parse_report(
    report_id: str,
    raw_text: str,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    timestamp: Optional[str] = None,
    source: Optional[str] = None,
    extractor: Optional[BaseReportExtractor] = None,
) -> Tuple[IncidentReport, DecisionResult]:
    """Run the full pipeline on one report and return (IncidentReport, DecisionResult).

    Raises schemas.ReportValidationError if the input fails validation.
    Deterministic: identical arguments always produce identical results
    (the default extractor uses no randomness and no network access).
    """
    logger.info("Validating report_id=%s", report_id)
    report_input = validate_report_input(report_id, raw_text, latitude, longitude, timestamp, source)

    logger.debug("Normalizing report_id=%s (text redacted): %s", report_id, redact_pii(report_input.raw_text))
    normalized_text = normalize_text(report_input.raw_text)

    active_extractor = extractor if extractor is not None else _DEFAULT_EXTRACTOR
    logger.info("Extracting structured incident for report_id=%s using %s", report_id, type(active_extractor).__name__)
    incident_report = active_extractor.extract(report_input, normalized_text)

    logger.info("Evaluating risk indicators for report_id=%s", report_id)
    incident_report.risk_indicators = evaluate_risk_indicators(incident_report)
    incident_report.overall_extraction_confidence = _compute_overall_confidence(incident_report)

    logger.info("Running decision engine for report_id=%s", report_id)
    decision = make_decision(incident_report, incident_report.risk_indicators)

    return incident_report, decision


# ---------------------------------------------------------------------------
# CLI demo -- human-readable, facts-vs-interpretation-separated output.
# ---------------------------------------------------------------------------

_EXAMPLE_REPORTS: List[Tuple[str, str]] = [
    (
        "demo-1-serious-collision",
        "Two cars collided near the highway intersection during heavy rain. "
        "Four people appear injured. One person may be unconscious. "
        "Traffic is completely blocked.",
    ),
    (
        "demo-2-minor-collision-no-injury",
        "A car hit a parked vehicle in a parking lot. No injuries were reported.",
    ),
    (
        "demo-3-fire-with-trapped-people",
        "A building is on fire and people may be trapped inside. Heavy smoke is visible.",
    ),
    (
        "demo-4-hazmat",
        "A tanker truck overturned on the highway and a fuel spill is spreading. "
        "A gas leak is also suspected near the scene.",
    ),
    (
        "demo-5-weather-road-blockage",
        "Heavy snow has made the road icy near the bridge and traffic is backed up.",
    ),
    (
        "demo-6-ambiguous",
        "I don't know what happened, but there is smoke.",
    ),
]


def _format_field(name: str, ef) -> str:  # ef: ExtractedField, kept untyped to avoid import cycle noise
    if not ef.is_present:
        return f"  {name:<22}: (not mentioned)"
    evidence = f' -- "{ef.evidence}"' if ef.evidence else ""
    return f"  {name:<22}: {ef.value}  [{ef.certainty.value}]{evidence}"


def _print_report(report_id: str, raw_text: str) -> None:
    incident_report, decision = parse_report(report_id, raw_text)

    print("=" * 88)
    print(f"REPORT ID: {report_id}")
    print("\nA. REPORT FACTS (raw, as submitted):")
    print(f'  "{raw_text}"')

    print("\nB. EXTRACTED INFORMATION (structured, with evidence & certainty):")
    print(f"  incident_type          : {incident_report.incident_type.value}"
          f"{' (subtype: ' + incident_report.incident_subtype + ')' if incident_report.incident_subtype else ''}")
    print(f"  overall_confidence     : {incident_report.overall_extraction_confidence.value}")
    for span in incident_report.extraction_evidence:
        evidence = f' -- "{span.evidence}"' if span.evidence else ""
        print(f"    {span.field:<24}: {span.value}  [{span.certainty.value}]{evidence}")

    print("\nC. RISK INDICATORS (rule-based operational signals, not medical triage):")
    if not incident_report.risk_indicators:
        print("    (none identified)")
    for ind in incident_report.risk_indicators:
        print(f"    - {ind.name} [{ind.category.value}, {ind.certainty.value}]: {ind.explanation}")

    print("\nD. RECOMMENDATION (project-defined prototype rules, human review required):")
    print(f"    priority               : {decision.priority.value}")
    print(f"    risk_level             : {decision.risk_level.value}")
    categories = ", ".join(c.value for c in decision.recommended_response_categories) or "(none)"
    print(f"    recommended_categories : {categories}")
    print("    explanation:")
    for reason in decision.reasons:
        print(f"      - {reason}")
    print(f"    disclaimer: {decision.disclaimer}")
    print()


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    print("ResQAI Phase 2 -- Emergency Report Intelligence demo\n")
    for report_id, raw_text in _EXAMPLE_REPORTS:
        _print_report(report_id, raw_text)


if __name__ == "__main__":
    main()
