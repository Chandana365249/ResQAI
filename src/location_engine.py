"""
location_engine.py

Deterministic, local, dependency-free geospatial utilities: coordinate
validation and great-circle distance. No live mapping service, no API
key, no network access -- a standard Haversine calculation using only
the Python standard library `math` module.

This module never fabricates a location. If latitude/longitude are
missing or invalid, `assess_incident_location()` says so explicitly
(`available=False`, with a human-readable `reason`) rather than
substituting a default coordinate -- callers (resource_engine.py,
orchestrator.py) must treat that as "proximity ranking cannot be
performed", not silently skip the check.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple

# Mean Earth radius in kilometers -- the standard constant used in the
# Haversine formula (IUGG mean radius, widely used for this purpose).
EARTH_RADIUS_KM = 6371.0088

_LATITUDE_RANGE = (-90.0, 90.0)
_LONGITUDE_RANGE = (-180.0, 180.0)


class CoordinateValidationError(ValueError):
    """Raised by validate_coordinates() for out-of-range or malformed input."""


@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


@dataclass
class LocationAssessment:
    """Whether incident coordinates are usable for proximity ranking, and why not if not."""

    coordinates: Optional[Coordinates]
    available: bool
    reason: Optional[str] = None


def validate_coordinates(latitude: Optional[float], longitude: Optional[float]) -> Coordinates:
    """Validate and wrap a (latitude, longitude) pair.

    Raises CoordinateValidationError with a specific message for any
    missing, non-numeric, or out-of-range value. Does not accept
    partial input (one present, one missing).
    """
    if latitude is None or longitude is None:
        raise CoordinateValidationError("Both latitude and longitude are required.")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise CoordinateValidationError("Latitude and longitude must be numeric.")
    if math.isnan(latitude) or math.isnan(longitude):
        raise CoordinateValidationError("Latitude/longitude cannot be NaN.")
    lat_low, lat_high = _LATITUDE_RANGE
    lon_low, lon_high = _LONGITUDE_RANGE
    if not (lat_low <= latitude <= lat_high):
        raise CoordinateValidationError(f"latitude={latitude} is outside the valid range [{lat_low}, {lat_high}].")
    if not (lon_low <= longitude <= lon_high):
        raise CoordinateValidationError(f"longitude={longitude} is outside the valid range [{lon_low}, {lon_high}].")
    return Coordinates(latitude=float(latitude), longitude=float(longitude))


def try_get_coordinates(
    latitude: Optional[float], longitude: Optional[float]
) -> Tuple[Optional[Coordinates], Optional[str]]:
    """Never raises. Returns (Coordinates, None) or (None, reason)."""
    if latitude is None or longitude is None:
        return None, "Latitude/longitude were not provided for this report."
    try:
        return validate_coordinates(latitude, longitude), None
    except CoordinateValidationError as exc:
        return None, str(exc)


def assess_incident_location(latitude: Optional[float], longitude: Optional[float]) -> LocationAssessment:
    """Build a LocationAssessment for an incident's reported coordinates."""
    coordinates, reason = try_get_coordinates(latitude, longitude)
    return LocationAssessment(coordinates=coordinates, available=coordinates is not None, reason=reason)


def haversine_distance_km(a: Coordinates, b: Coordinates) -> float:
    """Great-circle distance between two points, in kilometers.

    Standard Haversine formula -- deterministic, no external service.
    Accurate to within ~0.5% for terrestrial distances, which is more
    than sufficient for a resource-proximity DEMO (not for navigation).
    """
    lat1, lon1 = math.radians(a.latitude), math.radians(a.longitude)
    lat2, lon2 = math.radians(b.latitude), math.radians(b.longitude)

    d_lat = lat2 - lat1
    d_lon = lon2 - lon1

    h = math.sin(d_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2) ** 2
    c = 2 * math.asin(min(1.0, math.sqrt(h)))
    return EARTH_RADIUS_KM * c
