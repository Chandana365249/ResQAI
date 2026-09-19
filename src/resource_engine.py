"""
resource_engine.py

Loads the SYNTHETIC demo resource catalog (data/resources/demo_resources.csv
-- see that file's header and docs/PHASE3_INTEGRATION.md, "Synthetic
resource-data limitation"), filters it by availability and requested
response category/capability, ranks candidates by great-circle distance
from the incident (when incident coordinates are available), and returns
a transparent, explained recommendation list.

============================== IMPORTANT ===================================
These are DEMO resources. Nothing returned by this module represents real,
live emergency-service availability. Every ResourceRecommendation exists
to demonstrate the ranking architecture, not to be dispatched against.
==============================================================================
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .location_engine import Coordinates, haversine_distance_km

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = Path("data/resources/demo_resources.csv")

REQUIRED_COLUMNS = {
    "resource_id", "resource_type", "resource_name", "latitude", "longitude",
    "availability_status", "capacity", "service_capabilities", "demo_only",
}

# Maps a Phase 2 ResponseCategory value to the demo catalog's primary
# resource_type for that category. "hazardous_material_response" is
# deliberately mapped to "hazmat_response" (the catalog's spelling) rather
# than assumed to match by string equality -- see _matches_category, which
# also checks service_capabilities so a dual-capable unit (e.g. a fire
# engine with "hazmat_response" listed as a capability) can qualify too.
CATEGORY_TO_RESOURCE_TYPE: Dict[str, str] = {
    "ambulance": "ambulance",
    "fire_response": "fire_response",
    "police_response": "police_response",
    "traffic_management": "traffic_management",
    "hazardous_material_response": "hazmat_response",
    # "evacuation_consideration" has no dedicated catalog resource_type in
    # this demo dataset -- intentionally not mapped (see docs).
}


class ResourceValidationError(ValueError):
    """Raised when a resource catalog row is malformed."""


@dataclass(frozen=True)
class Resource:
    resource_id: str
    resource_type: str
    resource_name: str
    latitude: Optional[float]
    longitude: Optional[float]
    availability_status: str
    capacity: Optional[int]
    capabilities: List[str]
    demo_only: bool

    @property
    def is_available(self) -> bool:
        return self.availability_status.strip().lower() == "available"

    @property
    def coordinates(self) -> Optional[Coordinates]:
        if self.latitude is None or self.longitude is None:
            return None
        return Coordinates(self.latitude, self.longitude)


@dataclass
class ResourceRecommendation:
    resource_id: str
    resource_type: str
    resource_name: str
    distance_km: Optional[float]
    availability: str
    capabilities: List[str]
    reason: str
    demo_only: bool = True


@dataclass
class ResourceSearchResult:
    category: str
    resources: List[ResourceRecommendation] = field(default_factory=list)
    resource_available: bool = False
    reason: Optional[str] = None


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes")


def _parse_row(row: Dict[str, str], line_number: int) -> Resource:
    missing = REQUIRED_COLUMNS - set(row.keys())
    if missing:
        raise ResourceValidationError(f"Row {line_number}: missing columns {sorted(missing)}.")
    try:
        latitude = float(row["latitude"]) if row["latitude"].strip() else None
        longitude = float(row["longitude"]) if row["longitude"].strip() else None
        capacity = int(row["capacity"]) if row["capacity"].strip() else None
    except ValueError as exc:
        raise ResourceValidationError(f"Row {line_number} ({row.get('resource_id')}): {exc}") from exc

    if latitude is not None and not (-90.0 <= latitude <= 90.0):
        raise ResourceValidationError(f"Row {line_number} ({row['resource_id']}): latitude out of range.")
    if longitude is not None and not (-180.0 <= longitude <= 180.0):
        raise ResourceValidationError(f"Row {line_number} ({row['resource_id']}): longitude out of range.")

    return Resource(
        resource_id=row["resource_id"].strip(),
        resource_type=row["resource_type"].strip(),
        resource_name=row["resource_name"].strip(),
        latitude=latitude,
        longitude=longitude,
        availability_status=row["availability_status"].strip(),
        capacity=capacity,
        capabilities=[c.strip() for c in row["service_capabilities"].split(";") if c.strip()],
        demo_only=_parse_bool(row["demo_only"]),
    )


def load_resource_catalog(path: Path = DEFAULT_CATALOG_PATH) -> List[Resource]:
    """Load and validate the demo resource catalog. Raises ResourceValidationError
    on any malformed row rather than silently skipping or guessing a fix.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Resource catalog not found at '{path}'.")

    resources: List[Resource] = []
    with open(path, newline="", encoding="utf-8") as f:
        # The catalog's leading lines are a documented "# ..." comment block
        # explaining the synthetic nature of the data (see the file itself).
        reader = csv.DictReader((line for line in f if not line.startswith("#")))
        for line_number, row in enumerate(reader, start=2):
            resources.append(_parse_row(row, line_number))
    return resources


def _matches_category(resource: Resource, category: str) -> bool:
    target_type = CATEGORY_TO_RESOURCE_TYPE.get(category)
    if target_type is None:
        return False
    if resource.resource_type == target_type:
        return True
    return target_type in resource.capabilities


def find_resources_for_category(
    category: str,
    incident_coordinates: Optional[Coordinates],
    catalog: Optional[List[Resource]] = None,
    top_n: int = 3,
) -> ResourceSearchResult:
    """Find and rank up to `top_n` available demo resources for one response category.

    Ranking (transparent, in order): (1) availability -- already filtered;
    (2) category/capability match -- already filtered; (3) distance from
    the incident, ascending, when incident_coordinates is available;
    (4) capacity, descending, as a documented tie-break. If
    incident_coordinates is None, distance-based ranking is skipped
    entirely (never fabricated) and matching resources are still
    returned, explicitly marked as unranked by distance.
    """
    if category not in CATEGORY_TO_RESOURCE_TYPE:
        return ResourceSearchResult(
            category=category, resources=[], resource_available=False,
            reason=f"No demo resource type is defined for response category '{category}'.",
        )

    if catalog is None:
        catalog = load_resource_catalog()

    qualifying = [r for r in catalog if r.is_available and _matches_category(r, category)]

    if not qualifying:
        return ResourceSearchResult(
            category=category, resources=[], resource_available=False,
            reason="No available demo resource matched the requested response category.",
        )

    if incident_coordinates is None:
        ranked = sorted(qualifying, key=lambda r: (-(r.capacity or 0), r.resource_id))
        recommendations = [
            ResourceRecommendation(
                resource_id=r.resource_id, resource_type=r.resource_type, resource_name=r.resource_name,
                distance_km=None, availability=r.availability_status, capabilities=r.capabilities,
                reason=(
                    f"Available {category}-category demo resource (capability match); "
                    f"distance ranking unavailable because incident coordinates were not provided."
                ),
            )
            for r in ranked[:top_n]
        ]
        return ResourceSearchResult(
            category=category, resources=recommendations, resource_available=True,
            reason="Incident coordinates unavailable: resources listed by availability/capability match only, not distance.",
        )

    scored = []
    for r in qualifying:
        coords = r.coordinates
        distance = haversine_distance_km(incident_coordinates, coords) if coords else None
        scored.append((r, distance))

    # Resources without their own coordinates sort after those with a
    # known distance (None treated as infinitely far), then by capacity.
    scored.sort(key=lambda item: (item[1] if item[1] is not None else float("inf"), -(item[0].capacity or 0), item[0].resource_id))

    recommendations = []
    for r, distance in scored[:top_n]:
        if distance is not None:
            reason = f"Nearest available {category}-category demo resource ({distance:.1f} km away)."
        else:
            reason = f"Available {category}-category demo resource; this resource has no recorded coordinates."
        recommendations.append(ResourceRecommendation(
            resource_id=r.resource_id, resource_type=r.resource_type, resource_name=r.resource_name,
            distance_km=(round(distance, 2) if distance is not None else None),
            availability=r.availability_status, capabilities=r.capabilities, reason=reason,
        ))

    return ResourceSearchResult(category=category, resources=recommendations, resource_available=True)


def find_resources_for_categories(
    categories: List[str],
    incident_coordinates: Optional[Coordinates],
    catalog: Optional[List[Resource]] = None,
    top_n: int = 3,
) -> List[ResourceSearchResult]:
    """Convenience wrapper: run find_resources_for_category for each recommended category."""
    if catalog is None:
        catalog = load_resource_catalog()
    return [find_resources_for_category(c, incident_coordinates, catalog, top_n) for c in categories]
