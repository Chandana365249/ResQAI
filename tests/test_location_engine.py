"""Tests for src/location_engine.py."""

import math

import pytest

from src.location_engine import (
    Coordinates,
    CoordinateValidationError,
    assess_incident_location,
    haversine_distance_km,
    validate_coordinates,
)


# 14. Valid coordinates work
def test_valid_coordinates_accepted():
    c = validate_coordinates(39.0997, -94.5786)
    assert c.latitude == 39.0997
    assert c.longitude == -94.5786


# 15. Invalid coordinates are rejected
@pytest.mark.parametrize("lat,lon", [(999, 0), (0, 999), (-999, 0), (0, -999)])
def test_out_of_range_coordinates_rejected(lat, lon):
    with pytest.raises(CoordinateValidationError):
        validate_coordinates(lat, lon)


def test_nan_coordinates_rejected():
    with pytest.raises(CoordinateValidationError):
        validate_coordinates(float("nan"), 0)


def test_partial_coordinates_rejected():
    with pytest.raises(CoordinateValidationError):
        validate_coordinates(39.0, None)


# 16. Missing coordinates are handled
def test_assess_location_missing_both():
    assessment = assess_incident_location(None, None)
    assert assessment.available is False
    assert assessment.coordinates is None
    assert assessment.reason


def test_assess_location_missing_one():
    assessment = assess_incident_location(39.0, None)
    assert assessment.available is False


def test_assess_location_valid():
    assessment = assess_incident_location(39.0997, -94.5786)
    assert assessment.available is True
    assert assessment.coordinates is not None
    assert assessment.reason is None


def test_assess_location_invalid_range_handled_not_raised():
    assessment = assess_incident_location(999.0, 0.0)
    assert assessment.available is False
    assert assessment.coordinates is None
    assert "range" in assessment.reason.lower()


# 17. Distance calculation is deterministic
def test_distance_is_deterministic():
    a = Coordinates(39.0997, -94.5786)
    b = Coordinates(39.1210, -94.6100)
    d1 = haversine_distance_km(a, b)
    d2 = haversine_distance_km(a, b)
    assert d1 == d2


def test_distance_to_self_is_zero():
    a = Coordinates(39.0997, -94.5786)
    assert haversine_distance_km(a, a) == pytest.approx(0.0, abs=1e-9)


def test_distance_is_symmetric():
    a = Coordinates(39.0997, -94.5786)
    b = Coordinates(40.0, -95.0)
    assert haversine_distance_km(a, b) == pytest.approx(haversine_distance_km(b, a), abs=1e-9)


# 18. Known test coordinates produce reasonable distance results
def test_one_degree_longitude_at_equator_is_about_111_km():
    a = Coordinates(0.0, 0.0)
    b = Coordinates(0.0, 1.0)
    assert haversine_distance_km(a, b) == pytest.approx(111.19, abs=0.5)


def test_new_york_to_los_angeles_known_distance():
    nyc = Coordinates(40.7128, -74.0060)
    la = Coordinates(34.0522, -118.2437)
    # Widely-cited great-circle distance is ~3936 km.
    assert haversine_distance_km(nyc, la) == pytest.approx(3936, abs=20)
