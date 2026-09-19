"""
extraction/deterministic.py

DeterministicReportExtractor: a rule-based (regex + negation/hedging
heuristics), fully local, dependency-free implementation of
BaseReportExtractor. No network access, no ML model, no randomness --
identical input always produces identical output.

Organization: one keyword-pattern constant + one small extraction
function per attribute GROUP (people, vehicles, fire, hazmat,
environment, location, traffic, emergency services), plus incident
type classification. Every boolean/count attribute is produced by the
same two shared primitives from utils/text_rules.py:

  - `classify_match(clause, match_start)` for negation + hedging
  - `word_to_number(token)` for spelled-out or digit counts

so negation and uncertainty behave identically everywhere rather than
being reimplemented (and potentially inconsistently) per attribute.

Known simplification: for each attribute, only the FIRST clause that
matches its pattern is used. Conflicting statements about the same
attribute across different sentences (e.g. a retraction later in the
report) are not reconciled -- documented in docs/REPORT_INTELLIGENCE.md.
"""

from __future__ import annotations

import re
from typing import List, Optional, Pattern, Tuple

from ..schemas import (
    Certainty,
    EmergencyReportInput,
    EnvironmentInfo,
    EmergencyServicesInfo,
    ExtractedField,
    FireInfo,
    HazmatInfo,
    IncidentReport,
    IncidentType,
    LocationContext,
    PeopleInfo,
    TrafficInfo,
    VehicleInfo,
    build_evidence_list,
    collapse_whitespace,
)
from ..utils.text_rules import (
    NUMBER_TOKEN_PATTERN,
    classify_match,
    split_clauses,
    word_to_number,
)
from .base import BaseReportExtractor

_EVIDENCE_MAX_LEN = 160


def _evidence_snippet(clause: str) -> str:
    snippet = collapse_whitespace(clause)
    return snippet if len(snippet) <= _EVIDENCE_MAX_LEN else snippet[:_EVIDENCE_MAX_LEN].rstrip() + "..."


def _extract_flag(clauses: List[str], pattern: Pattern) -> ExtractedField[bool]:
    """Generic boolean-attribute extractor shared by every yes/no field."""
    for clause in clauses:
        match = pattern.search(clause)
        if match:
            value, certainty = classify_match(clause, match.start())
            return ExtractedField(value=value, certainty=certainty, evidence=_evidence_snippet(clause))
    return ExtractedField()


def _extract_count(clauses: List[str], pattern: Pattern) -> ExtractedField[int]:
    """Generic count-attribute extractor for patterns with a named 'num' group."""
    for clause in clauses:
        match = pattern.search(clause)
        if match:
            number = word_to_number(match.group("num"))
            if number is None:
                continue
            value, certainty = classify_match(clause, match.start())
            if not value:
                # e.g. "not four people were injured" -- rare, but a negated
                # count carries no meaningful positive number.
                return ExtractedField(value=None, certainty=Certainty.NOT_MENTIONED)
            return ExtractedField(value=number, certainty=certainty, evidence=_evidence_snippet(clause))
    return ExtractedField()


# ---------------------------------------------------------------------------
# Incident type classification
# ---------------------------------------------------------------------------

# Checked in this order; the first category with a non-negated match wins.
# Medical-emergency phrases are deliberately specific ("heart attack", "not
# breathing", ...) rather than generic injury words ("injured",
# "unconscious") -- those generic words commonly co-occur with a vehicle
# collision and must not override the more specific incident type (see the
# worked example in docs/REPORT_INTELLIGENCE.md).
_INCIDENT_TYPE_RULES: List[Tuple[IncidentType, Pattern]] = [
    (IncidentType.HAZARDOUS_MATERIAL, re.compile(
        r"\b(chemical spill|gas leak|hazardous material|hazmat|"
        r"toxic (?:substance|fumes|gas|chemical)|fuel spill)\b"
    )),
    (IncidentType.FIRE, re.compile(r"\b(fire|flames?|burning|blaze|on fire)\b")),
    (IncidentType.MEDICAL_EMERGENCY, re.compile(
        r"\b(heart attack|stroke|seizure|not breathing|choking|"
        r"allergic reaction|overdose|cardiac arrest|difficulty breathing)\b"
    )),
    (IncidentType.STRUCTURAL_INCIDENT, re.compile(
        r"\b(building collapse(?:d)?|structure collapsed|roof collapse(?:d)?|"
        r"wall collapse(?:d)?|collapsed building)\b"
    )),
    (IncidentType.NATURAL_DISASTER, re.compile(
        r"\b(earthquake|tornado|hurricane|landslide|wildfire|tsunami|"
        r"flash flood|severe flooding)\b"
    )),
    (IncidentType.VEHICLE_COLLISION, re.compile(
        r"\b(car crash|car accident|vehicle crash|vehicle collision|"
        r"vehicles? collided|cars? collided|collision|crash(?:ed|es)?|"
        r"rear-ended|rear ended|rollover|overturned|"
        r"hit (?:a |an |the )?(?:parked )?(?:car|vehicle|truck|motorcycle))\b"
    )),
    (IncidentType.ROAD_OBSTRUCTION, re.compile(
        r"\b(road (?:is |was )?blocked|road obstruction|debris on (?:the )?road|"
        r"fallen tree|object in (?:the )?road|blocked road)\b"
    )),
]


def _classify_incident_type(clauses: List[str]) -> Tuple[IncidentType, Optional[str]]:
    for incident_type, pattern in _INCIDENT_TYPE_RULES:
        for clause in clauses:
            match = pattern.search(clause)
            if not match:
                continue
            value, _certainty = classify_match(clause, match.start())
            if value:
                return incident_type, match.group(0)
    return IncidentType.UNKNOWN, None


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

_INJURY_KEYWORD = re.compile(r"\b(injur(?:ed|ies|y)|hurt|wounded)\b")
# Optional linking verb between a person-count and the injury keyword, e.g.
# "four people ARE injured" / "four people APPEAR injured" / "4 injured".
_LINKING = r"(?:(?:are|were|appears?)\s+(?:to\s+be\s+)?)?"
_INJURY_COUNT = re.compile(
    rf"(?P<num>{NUMBER_TOKEN_PATTERN})\s+(?:people\s+)?{_LINKING}(?:injur(?:ed|ies)|hurt|wounded)\b"
)
_SERIOUS_INJURY_COUNT = re.compile(
    rf"(?P<num>{NUMBER_TOKEN_PATTERN})\s+(?:people\s+)?{_LINKING}"
    r"(?:seriously injured|critically injured|severely injured|in critical condition)\b"
)
_PEOPLE_AFFECTED_COUNT = re.compile(rf"(?P<num>{NUMBER_TOKEN_PATTERN})\s+people\b")
_UNCONSCIOUS = re.compile(r"\bunconscious\b")
_TRAPPED = re.compile(r"\btrapped\b")
_MISSING_PERSON = re.compile(r"\b(missing person|person (?:is |was )?missing|people (?:are |were )?missing)\b")
_POSSIBLE_FATALITY = re.compile(r"\b(dead|deceased|fatalit(?:y|ies)|killed|died)\b")
_CHILD = re.compile(r"\b(child|children|kid|kids|infant|baby|toddler)\b")
_ELDERLY = re.compile(r"\b(elderly|senior citizen|older (?:man|woman|person)|elderly person)\b")

# Phase 3.5: pedestrian involvement (unlocks Phase 1's PEDS feature).
# "pedestrian" alone (as in "hit a pedestrian", "pedestrian was struck",
# "pedestrian involved") is the anchor; negation/hedging is handled by the
# same classify_match() every other flag uses (e.g. "no pedestrian was
# involved" -> False/confirmed; "possibly a pedestrian was struck" -> True/possible).
_PEDESTRIAN = re.compile(r"\b(pedestrian|person walking|person on foot)\b")
_PEDESTRIAN_COUNT = re.compile(rf"(?P<num>{NUMBER_TOKEN_PATTERN})\s+pedestrians?\b")


def _extract_people(clauses: List[str]) -> PeopleInfo:
    return PeopleInfo(
        people_affected=_extract_count(clauses, _PEOPLE_AFFECTED_COUNT),
        injuries_present=_extract_flag(clauses, _INJURY_KEYWORD),
        injured_people=_extract_count(clauses, _INJURY_COUNT),
        seriously_injured=_extract_count(clauses, _SERIOUS_INJURY_COUNT),
        unconscious_person=_extract_flag(clauses, _UNCONSCIOUS),
        trapped_person=_extract_flag(clauses, _TRAPPED),
        missing_person=_extract_flag(clauses, _MISSING_PERSON),
        possible_fatality=_extract_flag(clauses, _POSSIBLE_FATALITY),
        child_mentioned=_extract_flag(clauses, _CHILD),
        elderly_mentioned=_extract_flag(clauses, _ELDERLY),
        pedestrian_involved=_extract_flag(clauses, _PEDESTRIAN),
        pedestrian_count=_extract_count(clauses, _PEDESTRIAN_COUNT),
    )


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------

_VEHICLE_NOUN = r"(?:cars?|vehicles?|trucks?|motorcycles?|buses?|vans?)"
_VEHICLE_COUNT = re.compile(rf"(?P<num>{NUMBER_TOKEN_PATTERN}|an?)\s+{_VEHICLE_NOUN}\b")
_COLLISION = re.compile(
    r"\b(collided|collision|crash(?:ed|es)?|cars? collided|vehicles? collided|rear-ended|rear ended|"
    r"hit (?:a |an |the )?(?:parked )?(?:car|vehicle|truck|motorcycle))\b"
)
_ROLLOVER = re.compile(r"\b(rolled over|rollover|overturned|flipped (?:over)?)\b")
_VEHICLE_FIRE = re.compile(
    r"\b(vehicle (?:is |was )?on fire|car (?:is |was )?on fire|vehicle fire|car fire)\b"
)

# Phase 3.5: speeding (unlocks Phase 1's any_speeding_involved). Deliberately
# limited to explicit speeding language -- never inferred from crash severity
# elsewhere in the pipeline (e.g. a fatal crash does NOT imply speeding here).
_SPEEDING = re.compile(
    r"\b(speeding|traveling too fast|travelling too fast|"
    r"exceeding the speed limit|excessive speed)\b"
)

# Phase 3.5: hit-and-run (unlocks Phase 1's any_hit_run_involved).
_HIT_AND_RUN = re.compile(r"\b(hit[\s-]and[\s-]run|fled|left the scene(?: without stopping)?)\b")

# Phase 3.5: explicit vehicle model year only (unlocks Phase 1's
# avg_vehicle_age_years, via ml_adapter.py -- see that module for how a
# year becomes an age). Anchored to "model"/vehicle-noun/"model year"/
# "manufactured in" context so a bare 4-digit number elsewhere in the
# report (e.g. an unrelated date) is not mistaken for a model year.
# Plausible range 1950-2049 further guards against accidental matches.
_VEHICLE_YEAR = re.compile(
    r"\ba\s+(?P<year_a>19[5-9]\d|20[0-4]\d)\s+(?:model\s+)?(?:vehicle|car|truck|motorcycle)\b"
    r"|\b(?P<year_b>19[5-9]\d|20[0-4]\d)\s+model\b"
    r"|\bmodel\s+year\s+(?P<year_c>19[5-9]\d|20[0-4]\d)\b"
    r"|\b(?:manufactured|made)\s+in\s+(?P<year_d>19[5-9]\d|20[0-4]\d)\b"
)


def _extract_vehicle_count(clauses: List[str]) -> ExtractedField[int]:
    for clause in clauses:
        match = _VEHICLE_COUNT.search(clause)
        if match:
            token = match.group("num")
            number = 1 if token in ("a", "an") else word_to_number(token)
            if number is None:
                continue
            value, certainty = classify_match(clause, match.start())
            if not value:
                return ExtractedField()
            return ExtractedField(value=number, certainty=certainty, evidence=_evidence_snippet(clause))
    return ExtractedField()


def _extract_vehicle_types(clauses: List[str]) -> ExtractedField[List[str]]:
    found: List[str] = []
    evidence: Optional[str] = None
    for clause in clauses:
        match = _VEHICLE_COUNT.search(clause)
        if match:
            value, certainty = classify_match(clause, match.start())
            if value:
                noun = re.search(_VEHICLE_NOUN, clause[match.start():]).group(0)
                if noun not in found:
                    found.append(noun)
                if evidence is None:
                    evidence = _evidence_snippet(clause)
    if not found:
        return ExtractedField()
    return ExtractedField(value=found, certainty=Certainty.CONFIRMED, evidence=evidence)


def _extract_vehicle_year(clauses: List[str]) -> ExtractedField[int]:
    for clause in clauses:
        match = _VEHICLE_YEAR.search(clause)
        if match:
            year_str = (
                match.group("year_a") or match.group("year_b")
                or match.group("year_c") or match.group("year_d")
            )
            value, certainty = classify_match(clause, match.start())
            if not value:
                return ExtractedField()
            return ExtractedField(value=int(year_str), certainty=certainty, evidence=_evidence_snippet(clause))
    return ExtractedField()


def _extract_vehicles(clauses: List[str]) -> VehicleInfo:
    return VehicleInfo(
        vehicle_count=_extract_vehicle_count(clauses),
        vehicle_types=_extract_vehicle_types(clauses),
        collision=_extract_flag(clauses, _COLLISION),
        rollover=_extract_flag(clauses, _ROLLOVER),
        speeding=_extract_flag(clauses, _SPEEDING),
        hit_and_run=_extract_flag(clauses, _HIT_AND_RUN),
        vehicle_model_year=_extract_vehicle_year(clauses),
        vehicle_fire=_extract_flag(clauses, _VEHICLE_FIRE),
    )


# ---------------------------------------------------------------------------
# Fire
# ---------------------------------------------------------------------------

_FIRE_PRESENT = re.compile(r"\b(fire|flames?|burning|blaze|on fire)\b")
_SMOKE = re.compile(r"\bsmoke\b")
_EXPLOSION = re.compile(r"\b(explosion|exploded|explodes?)\b")
_SPREADING_FIRE = re.compile(r"\b(spreading|growing) fire\b|\bfire\b[^.?!;]{0,30}\bspreading\b")
_BUILDING_FIRE = re.compile(r"\bbuilding (?:is |was )?on fire\b|\bbuilding fire\b|\bhouse (?:is |was )?on fire\b")


def _extract_fire(clauses: List[str]) -> FireInfo:
    return FireInfo(
        fire_present=_extract_flag(clauses, _FIRE_PRESENT),
        smoke_present=_extract_flag(clauses, _SMOKE),
        explosion=_extract_flag(clauses, _EXPLOSION),
        spreading_fire=_extract_flag(clauses, _SPREADING_FIRE),
        building_fire=_extract_flag(clauses, _BUILDING_FIRE),
    )


# ---------------------------------------------------------------------------
# Hazardous materials
# ---------------------------------------------------------------------------

_CHEMICAL_SPILL = re.compile(r"\bchemical spill\b")
_FUEL_SPILL = re.compile(r"\b(fuel|gasoline|diesel) spill\b")
_GAS_LEAK = re.compile(r"\bgas leak\b")
_HAZMAT_GENERIC = re.compile(r"\bhazardous material\b|\bhazmat\b")
_TOXIC = re.compile(r"\btoxic (?:substance|fumes|gas|chemical)\b")
_UNKNOWN_SUBSTANCE = re.compile(r"\bunknown substance\b|\bunidentified (?:substance|chemical|liquid)\b")


def _extract_hazmat(clauses: List[str]) -> HazmatInfo:
    return HazmatInfo(
        chemical_spill=_extract_flag(clauses, _CHEMICAL_SPILL),
        fuel_spill=_extract_flag(clauses, _FUEL_SPILL),
        gas_leak=_extract_flag(clauses, _GAS_LEAK),
        hazardous_material=_extract_flag(clauses, _HAZMAT_GENERIC),
        toxic_substance=_extract_flag(clauses, _TOXIC),
        unknown_substance=_extract_flag(clauses, _UNKNOWN_SUBSTANCE),
    )


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

_HEAVY_RAIN = re.compile(r"\bheavy rain(?:fall)?\b|\braining heavily\b")
_RAIN = re.compile(r"\brain(?:ing|y|fall)?\b")
_FOG = re.compile(r"\bfog(?:gy)?\b")
_SNOW = re.compile(r"\bsnow(?:ing|y)?\b")
_STRONG_WIND = re.compile(r"\b(strong|high) winds?\b|\bwindy\b")
_FLOOD = re.compile(r"\bflood(?:ed|ing)?\b")
_POOR_VISIBILITY = re.compile(r"\bpoor visibility\b|\blow visibility\b|\bvisibility (?:is |was )?(?:poor|low|reduced)\b")
_WET_ROAD = re.compile(r"\bwet road\b|\broad (?:is |was )?wet\b")
_ICY_ROAD = re.compile(r"\bicy road\b|\bice on (?:the )?road\b|\broad (?:is |was )?icy\b")
_SMOKE_VISIBILITY = re.compile(r"\bsmoke\b[^.?!;]{0,30}\bvisibility\b|\bvisibility\b[^.?!;]{0,30}\bsmoke\b")


def _extract_environment(clauses: List[str]) -> EnvironmentInfo:
    heavy_rain = _extract_flag(clauses, _HEAVY_RAIN)
    rain = _extract_flag(clauses, _RAIN)
    if heavy_rain.value is True and not rain.is_present:
        # "heavy rain" implies "rain" even if the generic word isn't repeated.
        rain = ExtractedField(value=True, certainty=heavy_rain.certainty, evidence=heavy_rain.evidence)
    return EnvironmentInfo(
        rain=rain,
        heavy_rain=heavy_rain,
        fog=_extract_flag(clauses, _FOG),
        snow=_extract_flag(clauses, _SNOW),
        strong_wind=_extract_flag(clauses, _STRONG_WIND),
        flood=_extract_flag(clauses, _FLOOD),
        poor_visibility=_extract_flag(clauses, _POOR_VISIBILITY),
        wet_road=_extract_flag(clauses, _WET_ROAD),
        icy_road=_extract_flag(clauses, _ICY_ROAD),
        smoke_reducing_visibility=_extract_flag(clauses, _SMOKE_VISIBILITY),
    )


# ---------------------------------------------------------------------------
# Location context & traffic
# ---------------------------------------------------------------------------

_HIGHWAY = re.compile(r"\bhighway\b|\bfreeway\b|\bmotorway\b|\binterstate\b")
_INTERSECTION = re.compile(r"\bintersection\b|\bcrossroads?\b|\bjunction\b")
_BRIDGE = re.compile(r"\bbridge\b")
_TUNNEL = re.compile(r"\btunnel\b")
_RAILWAY_CROSSING = re.compile(r"\brailway crossing\b|\brail crossing\b|\btrain crossing\b|\blevel crossing\b")

_ROAD_BLOCKAGE = re.compile(r"\broad (?:is |was )?(?:blocked|closed)\b|\broad obstruction\b|\bblocked road\b")
_TRAFFIC_BLOCKAGE = re.compile(
    r"\btraffic (?:is |was )?(?:completely )?blocked\b|\btraffic (?:is |was )?backed up\b|"
    r"\btraffic jam\b|\btraffic (?:is |was )?stopped\b"
)
_LANE_BLOCKAGE = re.compile(r"\blanes? (?:is |are |was |were )?(?:blocked|closed)\b")
_STRUCTURAL_DAMAGE = re.compile(r"\bstructural damage\b|\bdamaged bridge\b|\bcollapsed (?:wall|structure|roof)\b")


def _extract_location(clauses: List[str]) -> LocationContext:
    return LocationContext(
        highway=_extract_flag(clauses, _HIGHWAY),
        intersection=_extract_flag(clauses, _INTERSECTION),
        bridge=_extract_flag(clauses, _BRIDGE),
        tunnel=_extract_flag(clauses, _TUNNEL),
        railway_crossing=_extract_flag(clauses, _RAILWAY_CROSSING),
    )


def _extract_traffic(clauses: List[str]) -> TrafficInfo:
    return TrafficInfo(
        road_blockage=_extract_flag(clauses, _ROAD_BLOCKAGE),
        traffic_blockage=_extract_flag(clauses, _TRAFFIC_BLOCKAGE),
        lane_blockage=_extract_flag(clauses, _LANE_BLOCKAGE),
        structural_damage=_extract_flag(clauses, _STRUCTURAL_DAMAGE),
    )


# ---------------------------------------------------------------------------
# Emergency services context
# ---------------------------------------------------------------------------

_AMBULANCE_REQUESTED = re.compile(
    r"\bambulance (?:is |was )?(?:requested|needed|called)\b|\bneeds? an ambulance\b|\brequesting an ambulance\b"
)
_FIRE_RESPONSE_REQUESTED = re.compile(
    r"\bfire (?:department|truck|response) (?:is |was )?(?:requested|needed|called)\b|"
    r"\bneeds? (?:the )?fire department\b"
)
_POLICE_RESPONSE_REQUESTED = re.compile(
    r"\bpolice (?:is |are |was |were )?(?:requested|needed|called)\b|\bneeds? police\b|\brequesting police\b"
)
_EVACUATION = re.compile(r"\bevacuat(?:e|ed|ing|ion)\b")


def _extract_emergency_services(clauses: List[str]) -> EmergencyServicesInfo:
    return EmergencyServicesInfo(
        ambulance_requested=_extract_flag(clauses, _AMBULANCE_REQUESTED),
        fire_response_requested=_extract_flag(clauses, _FIRE_RESPONSE_REQUESTED),
        police_response_requested=_extract_flag(clauses, _POLICE_RESPONSE_REQUESTED),
        evacuation_mentioned=_extract_flag(clauses, _EVACUATION),
    )


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


class DeterministicReportExtractor(BaseReportExtractor):
    """Rule-based extractor: regex + negation/hedging heuristics, no ML/LLM."""

    def extract(self, report_input: EmergencyReportInput, normalized_text: str) -> IncidentReport:
        clauses = split_clauses(normalized_text)
        incident_type, incident_subtype = _classify_incident_type(clauses)

        report = IncidentReport(
            report_id=report_input.report_id,
            raw_text=report_input.raw_text,
            normalized_text=normalized_text,
            incident_type=incident_type,
            incident_subtype=incident_subtype,
            people=_extract_people(clauses),
            vehicles=_extract_vehicles(clauses),
            fire=_extract_fire(clauses),
            hazmat=_extract_hazmat(clauses),
            environment=_extract_environment(clauses),
            location_context=_extract_location(clauses),
            traffic=_extract_traffic(clauses),
            emergency_services=_extract_emergency_services(clauses),
            timestamp=report_input.timestamp,
            latitude=report_input.latitude,
            longitude=report_input.longitude,
        )
        report.extraction_evidence = build_evidence_list(report)
        return report
