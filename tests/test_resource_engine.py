"""Tests for src/resource_engine.py."""

from src.location_engine import Coordinates
from src.resource_engine import (
    find_resources_for_category,
    load_resource_catalog,
)


# 19. Resource dataset loads
def test_resource_catalog_loads():
    catalog = load_resource_catalog()
    assert len(catalog) > 0
    assert all(r.resource_id for r in catalog)
    assert all(r.demo_only is True for r in catalog)


def test_resource_catalog_has_expected_types():
    catalog = load_resource_catalog()
    types = {r.resource_type for r in catalog}
    assert {"ambulance", "fire_response", "police_response", "traffic_management", "hazmat_response", "hospital"} <= types


# 20. Unavailable resources are filtered
def test_unavailable_resources_excluded():
    catalog = load_resource_catalog()
    incident = Coordinates(39.0997, -94.5786)
    result = find_resources_for_category("ambulance", incident, catalog)
    ids = {r.resource_id for r in result.resources}
    assert "AMB-DEMO-003" not in ids  # marked unavailable in the demo catalog


# 21. Correct response category is matched
def test_category_matches_only_relevant_resource_type():
    catalog = load_resource_catalog()
    incident = Coordinates(39.0997, -94.5786)
    result = find_resources_for_category("fire_response", incident, catalog)
    for rec in result.resources:
        assert rec.resource_type == "fire_response" or "fire_response" in rec.capabilities


# 22. Nearest compatible resource is selected
def test_nearest_resource_ranked_first():
    catalog = load_resource_catalog()
    incident = Coordinates(39.0997, -94.5786)  # exactly AMB-DEMO-001's location
    result = find_resources_for_category("ambulance", incident, catalog)
    assert result.resources[0].resource_id == "AMB-DEMO-001"
    assert result.resources[0].distance_km == 0.0
    distances = [r.distance_km for r in result.resources]
    assert distances == sorted(distances)


# 23. Capability matching works (dual-capable fire unit qualifies for hazmat)
def test_capability_matching_includes_dual_capable_units():
    catalog = load_resource_catalog()
    incident = Coordinates(39.0997, -94.5786)
    result = find_resources_for_category("hazardous_material_response", incident, catalog)
    ids = {r.resource_id for r in result.resources}
    assert "FIRE-DEMO-002" in ids  # fire unit with hazmat_response capability
    assert "HAZMAT-DEMO-001" in ids


def test_unavailable_hazmat_unit_excluded_even_with_capability():
    catalog = load_resource_catalog()
    incident = Coordinates(39.0997, -94.5786)
    result = find_resources_for_category("hazardous_material_response", incident, catalog)
    ids = {r.resource_id for r in result.resources}
    assert "HAZMAT-DEMO-002" not in ids  # marked unavailable


# 24. No-match scenario is handled
def test_no_match_for_unmapped_category():
    catalog = load_resource_catalog()
    incident = Coordinates(39.0997, -94.5786)
    result = find_resources_for_category("evacuation_consideration", incident, catalog)
    assert result.resource_available is False
    assert result.resources == []
    assert result.reason


def test_no_match_when_no_qualifying_resource_is_available():
    catalog = load_resource_catalog()
    # Keep every resource in the catalog EXCEPT any that could satisfy "ambulance"
    # (by type or capability), to directly exercise the no-qualifying-candidate path.
    filtered = [r for r in catalog if r.resource_type != "ambulance" and "ambulance" not in r.capabilities]
    result = find_resources_for_category("ambulance", Coordinates(39.0997, -94.5786), filtered)
    assert result.resource_available is False
    assert result.resources == []
    assert "no available demo resource" in result.reason.lower()


# 25. Missing location prevents proximity ranking safely (but capability match still works)
def test_missing_location_disables_distance_but_still_lists_candidates():
    catalog = load_resource_catalog()
    result = find_resources_for_category("ambulance", None, catalog)
    assert result.resource_available is True
    assert all(r.distance_km is None for r in result.resources)
    assert "unavailable" in (result.reason or "").lower() or "not provided" in (result.reason or "").lower()


def test_resource_recommendation_includes_reason():
    catalog = load_resource_catalog()
    incident = Coordinates(39.0997, -94.5786)
    result = find_resources_for_category("ambulance", incident, catalog)
    for rec in result.resources:
        assert rec.reason
        assert rec.demo_only is True
