"""
decision_engine.py

Phase 2 decision engine: a small, transparent, rule-based scoring
system that turns an IncidentReport + its RiskIndicators into a
DecisionResult (priority, risk level, recommended response
CATEGORIES, and human-readable reasons).

============================== IMPORTANT ==================================
This is a PROTOTYPE, project-defined rule set. The weights, thresholds,
and category mappings below were chosen by the ResQAI project to produce
a plausible, explainable ORDERING of reports -- they are NOT sourced from,
or validated against, any real emergency-dispatch triage standard (e.g.
NFPA, EMS priority dispatch systems). See docs/REPORT_INTELLIGENCE.md,
"Safety limitations", before using this for anything beyond a prototype
demonstration. DecisionResult.disclaimer restates this on every result.
=============================================================================

Every number here is a named constant with a one-line rationale comment
next to it, per the project's "no unexplained magic numbers" rule, and
the whole rule set is configurable via the module-level constants below
(no hidden logic elsewhere).
"""

from __future__ import annotations

from typing import Dict, List

from .schemas import Certainty, DecisionResult, IncidentReport, IncidentType, Priority, ResponseCategory, RiskIndicator, RiskLevel

# ---------------------------------------------------------------------------
# Rule 1: priority score = sum of (indicator base weight * certainty multiplier)
# ---------------------------------------------------------------------------

# Base weight per risk-indicator NAME (see risk_engine.py for how each is
# derived). Higher = contributes more to urgency. Relative ordering (e.g.
# possible_fatality > active_fire > road_blockage) reflects the project's
# judgement that indicators about a person's immediate survival should
# dominate indicators about traffic/operational disruption -- it is a
# design choice, not a derived or validated figure.
INDICATOR_BASE_WEIGHT: Dict[str, int] = {
    "possible_fatality": 100,          # highest: a life may already be lost
    "explosion_indicator": 90,         # active, rapidly escalating physical danger
    "possible_unconscious_person": 80,  # immediate life-safety concern
    "active_fire": 75,                 # escalating physical danger
    "hazardous_material": 70,          # danger can spread / affect responders too
    "possible_trapped_people": 70,     # immediate life-safety concern, extrication needed
    "infrastructure_damage": 45,       # scene safety / secondary collapse risk
    "multiple_injured_people": 45,     # more people needing care than a single-injury case
    "multiple_vehicle_collision": 25,  # operationally more complex than a single vehicle
    "road_blockage": 20,               # operational impact, not life-safety by itself
    "smoke_detected": 20,              # possible early-stage fire, unconfirmed
    "severe_weather": 15,              # affects response time/safety, not the incident itself
}

# A hedged ("possible"/"uncertain") indicator contributes LESS than a
# confirmed one -- required by the spec ("uncertain indicators should
# contribute less strongly than confirmed indicators"). CONFIRMED always
# contributes its full base weight.
CERTAINTY_MULTIPLIER: Dict[Certainty, float] = {
    Certainty.CONFIRMED: 1.0,
    Certainty.POSSIBLE: 0.7,
    Certainty.UNCERTAIN: 0.4,
    Certainty.NOT_MENTIONED: 0.0,
}

# Score thresholds -> Priority/RiskLevel. Chosen so that a single confirmed
# critical indicator (e.g. possible_fatality alone, weight 100) already
# reaches P0, while operational-only indicators (e.g. road_blockage alone,
# weight 20) stay at the lowest priority band.
_P0_THRESHOLD = 90   # >= one confirmed critical indicator
_P1_THRESHOLD = 55   # a confirmed high-severity indicator, or several moderate ones
_P2_THRESHOLD = 20   # at least one clearly operational indicator


def _score_indicators(indicators: List[RiskIndicator]) -> float:
    return sum(
        INDICATOR_BASE_WEIGHT.get(ind.name, 0) * CERTAINTY_MULTIPLIER.get(ind.certainty, 0.0)
        for ind in indicators
    )


def _priority_and_risk_level(score: float) -> tuple[Priority, RiskLevel]:
    if score >= _P0_THRESHOLD:
        return Priority.P0, RiskLevel.CRITICAL
    if score >= _P1_THRESHOLD:
        return Priority.P1, RiskLevel.HIGH
    if score >= _P2_THRESHOLD:
        return Priority.P2, RiskLevel.MODERATE
    return Priority.P3, RiskLevel.LOW


# ---------------------------------------------------------------------------
# Rule 2: recommended response categories
# ---------------------------------------------------------------------------

def _recommend_categories(report: IncidentReport, indicators: List[RiskIndicator]) -> List[ResponseCategory]:
    names = {ind.name for ind in indicators}
    categories: List[ResponseCategory] = []

    # Ambulance: any indicator pointing at a person needing medical attention.
    if names & {
        "possible_fatality", "possible_unconscious_person", "possible_trapped_people",
        "multiple_injured_people",
    } or report.people.injured_people.value:
        categories.append(ResponseCategory.AMBULANCE)

    # Fire response: active fire, explosion, or a vehicle/building fire flag.
    if (
        names & {"active_fire", "explosion_indicator"}
        or report.fire.building_fire.value is True
        or report.vehicles.vehicle_fire.value is True
    ):
        categories.append(ResponseCategory.FIRE_RESPONSE)

    # Police response: a vehicle collision occurred, or the road/traffic is
    # blocked (traffic control / scene management is a police function).
    if report.incident_type == IncidentType.VEHICLE_COLLISION or "road_blockage" in names:
        categories.append(ResponseCategory.POLICE_RESPONSE)

    # Traffic management: any road/lane/traffic blockage indicator.
    if "road_blockage" in names:
        categories.append(ResponseCategory.TRAFFIC_MANAGEMENT)

    # Hazardous material response: the dedicated hazmat indicator.
    if "hazardous_material" in names:
        categories.append(ResponseCategory.HAZARDOUS_MATERIAL_RESPONSE)

    # Evacuation consideration: explosion, spreading/building fire, or the
    # report explicitly mentions evacuation.
    if (
        "explosion_indicator" in names
        or report.fire.spreading_fire.value is True
        or report.fire.building_fire.value is True
        or report.emergency_services.evacuation_mentioned.value is True
    ):
        categories.append(ResponseCategory.EVACUATION_CONSIDERATION)

    return categories


def _build_reasons(indicators: List[RiskIndicator], categories: List[ResponseCategory]) -> List[str]:
    """Human-readable reasons, one per risk indicator that fired.

    Kept as a direct list of indicator explanations (rather than a
    prose paragraph) so each reason can be traced back to exactly one
    rule and one piece of evidence -- see EXPLANATION design in
    docs/REPORT_INTELLIGENCE.md.
    """
    if not indicators:
        return ["No operational risk indicators were identified from the report text."]
    return [f"{ind.explanation} (certainty: {ind.certainty.value})" for ind in indicators]


def make_decision(report: IncidentReport, indicators: List[RiskIndicator]) -> DecisionResult:
    """Combine risk indicators into a priority, risk level, and response recommendation.

    Pure function of (report, indicators) -> DecisionResult: same
    inputs always produce the same output (required for determinism).
    """
    score = _score_indicators(indicators)
    priority, risk_level = _priority_and_risk_level(score)
    categories = _recommend_categories(report, indicators)
    reasons = _build_reasons(indicators, categories)

    return DecisionResult(
        priority=priority,
        risk_level=risk_level,
        recommended_response_categories=categories,
        reasons=reasons,
    )
