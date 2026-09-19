"""
risk_engine.py

Risk Indicator Engine: turns an already-extracted `IncidentReport`
into a list of `RiskIndicator` objects -- transparent, rule-based
OPERATIONAL signals for a human dispatcher's attention.

This is explicitly NOT medical triage. It does not diagnose, does not
estimate survival odds, and does not replace clinical judgement. It
flags "this report contains language consistent with X" so a human
can prioritize attention, nothing more.

Every rule here is a small, named function: (IncidentReport) ->
Optional[RiskIndicator]. Keeping rules as separate functions (rather
than one large conditional block) makes each one independently
testable and easy to read, add to, or remove.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from .schemas import Certainty, ExtractedField, IncidentReport, IncidentType, RiskIndicator, RiskLevel


def _flag_indicator(
    field_value: ExtractedField,
    name: str,
    confirmed_level: RiskLevel,
    hedged_level: RiskLevel,
    explanation: str,
) -> Optional[RiskIndicator]:
    """Shared helper: build a RiskIndicator from a single boolean ExtractedField."""
    if field_value.value is not True:
        return None
    level = confirmed_level if field_value.certainty == Certainty.CONFIRMED else hedged_level
    return RiskIndicator(
        name=name,
        category=level,
        certainty=field_value.certainty,
        evidence=field_value.evidence,
        explanation=explanation,
    )


def _rule_possible_fatality(report: IncidentReport) -> Optional[RiskIndicator]:
    return _flag_indicator(
        report.people.possible_fatality,
        name="possible_fatality",
        confirmed_level=RiskLevel.CRITICAL,
        hedged_level=RiskLevel.CRITICAL,
        explanation="The report contains language consistent with a possible fatality.",
    )


def _rule_possible_unconscious_person(report: IncidentReport) -> Optional[RiskIndicator]:
    return _flag_indicator(
        report.people.unconscious_person,
        name="possible_unconscious_person",
        confirmed_level=RiskLevel.CRITICAL,
        hedged_level=RiskLevel.HIGH,
        explanation="The report indicates a person may be unconscious.",
    )


def _rule_possible_trapped_people(report: IncidentReport) -> Optional[RiskIndicator]:
    return _flag_indicator(
        report.people.trapped_person,
        name="possible_trapped_people",
        confirmed_level=RiskLevel.CRITICAL,
        hedged_level=RiskLevel.HIGH,
        explanation="The report indicates one or more people may be trapped.",
    )


def _rule_multiple_injured_people(report: IncidentReport) -> Optional[RiskIndicator]:
    injured = report.people.injured_people
    if injured.value is None or injured.value < 2:
        return None
    level = RiskLevel.HIGH if injured.certainty == Certainty.CONFIRMED else RiskLevel.MODERATE
    return RiskIndicator(
        name="multiple_injured_people",
        category=level,
        certainty=injured.certainty,
        evidence=injured.evidence,
        explanation=f"The report states {injured.value} people were injured.",
    )


def _rule_active_fire(report: IncidentReport) -> Optional[RiskIndicator]:
    return _flag_indicator(
        report.fire.fire_present,
        name="active_fire",
        confirmed_level=RiskLevel.CRITICAL,
        hedged_level=RiskLevel.HIGH,
        explanation="The report indicates an active fire.",
    )


def _rule_explosion_indicator(report: IncidentReport) -> Optional[RiskIndicator]:
    return _flag_indicator(
        report.fire.explosion,
        name="explosion_indicator",
        confirmed_level=RiskLevel.CRITICAL,
        hedged_level=RiskLevel.CRITICAL,
        explanation="The report indicates an explosion.",
    )


def _rule_hazardous_material(report: IncidentReport) -> Optional[RiskIndicator]:
    hazmat_fields = [
        report.hazmat.chemical_spill,
        report.hazmat.fuel_spill,
        report.hazmat.gas_leak,
        report.hazmat.hazardous_material,
        report.hazmat.toxic_substance,
        report.hazmat.unknown_substance,
    ]
    present = [f for f in hazmat_fields if f.value is True]
    if not present:
        return None
    # Use the most confident matching field for certainty/evidence.
    best = min(present, key=lambda f: list(Certainty).index(f.certainty))
    level = RiskLevel.CRITICAL if best.certainty == Certainty.CONFIRMED else RiskLevel.HIGH
    return RiskIndicator(
        name="hazardous_material",
        category=level,
        certainty=best.certainty,
        evidence=best.evidence,
        explanation="The report indicates a hazardous material (chemical, fuel, gas, or unknown substance) is involved.",
    )


def _rule_road_blockage(report: IncidentReport) -> Optional[RiskIndicator]:
    traffic_fields = [
        report.traffic.road_blockage,
        report.traffic.traffic_blockage,
        report.traffic.lane_blockage,
    ]
    present = [f for f in traffic_fields if f.value is True]
    if not present:
        return None
    best = min(present, key=lambda f: list(Certainty).index(f.certainty))
    level = RiskLevel.MODERATE if best.certainty == Certainty.CONFIRMED else RiskLevel.LOW
    return RiskIndicator(
        name="road_blockage",
        category=level,
        certainty=best.certainty,
        evidence=best.evidence,
        explanation="The report indicates the road, a lane, or traffic is blocked.",
    )


_SEVERE_WEATHER_FIELDS = ("heavy_rain", "fog", "snow", "strong_wind", "flood", "icy_road", "poor_visibility")


def _rule_severe_weather(report: IncidentReport) -> Optional[RiskIndicator]:
    present = [
        getattr(report.environment, name)
        for name in _SEVERE_WEATHER_FIELDS
        if getattr(report.environment, name).value is True
    ]
    if not present:
        return None
    best = min(present, key=lambda f: list(Certainty).index(f.certainty))
    return RiskIndicator(
        name="severe_weather",
        category=RiskLevel.MODERATE,
        certainty=best.certainty,
        evidence=best.evidence,
        explanation="The report indicates adverse weather or road conditions that may affect response.",
    )


def _rule_multiple_vehicle_collision(report: IncidentReport) -> Optional[RiskIndicator]:
    count = report.vehicles.vehicle_count
    if report.incident_type != IncidentType.VEHICLE_COLLISION or count.value is None or count.value < 2:
        return None
    level = RiskLevel.MODERATE if count.certainty == Certainty.CONFIRMED else RiskLevel.LOW
    return RiskIndicator(
        name="multiple_vehicle_collision",
        category=level,
        certainty=count.certainty,
        evidence=count.evidence,
        explanation=f"The report describes a collision involving {count.value} vehicles.",
    )


def _rule_smoke_detected(report: IncidentReport) -> Optional[RiskIndicator]:
    """Smoke alone does not confirm a fire (see extraction/deterministic.py:
    "smoke" never classifies incident_type as FIRE on its own). It is still
    operationally worth flagging on its own, lower-severity terms, e.g. for
    a report like "I don't know what happened, but there is smoke."
    """
    if report.fire.fire_present.value is True:
        # Already covered by the (more specific) active_fire indicator.
        return None
    return _flag_indicator(
        report.fire.smoke_present,
        name="smoke_detected",
        confirmed_level=RiskLevel.MODERATE,
        hedged_level=RiskLevel.LOW,
        explanation="The report mentions smoke without a confirmed fire.",
    )


def _rule_infrastructure_damage(report: IncidentReport) -> Optional[RiskIndicator]:
    return _flag_indicator(
        report.traffic.structural_damage,
        name="infrastructure_damage",
        confirmed_level=RiskLevel.HIGH,
        hedged_level=RiskLevel.MODERATE,
        explanation="The report indicates structural or infrastructure damage.",
    )


# Ordered so that, if callers only want the single most severe indicator,
# the most operationally significant rules are evaluated first. The
# decision engine (decision_engine.py) considers ALL returned indicators,
# not just the first, so this order does not affect its output -- it only
# affects the natural reading order of risk_indicators on the report.
_RULES: List[Callable[[IncidentReport], Optional[RiskIndicator]]] = [
    _rule_possible_fatality,
    _rule_explosion_indicator,
    _rule_active_fire,
    _rule_smoke_detected,
    _rule_hazardous_material,
    _rule_possible_unconscious_person,
    _rule_possible_trapped_people,
    _rule_multiple_injured_people,
    _rule_infrastructure_damage,
    _rule_multiple_vehicle_collision,
    _rule_road_blockage,
    _rule_severe_weather,
]


def evaluate_risk_indicators(report: IncidentReport) -> List[RiskIndicator]:
    """Run every risk rule against an IncidentReport and return the indicators that fired."""
    indicators: List[RiskIndicator] = []
    for rule in _RULES:
        indicator = rule(report)
        if indicator is not None:
            indicators.append(indicator)
    return indicators
