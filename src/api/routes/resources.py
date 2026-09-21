"""GET /api/v1/resources -- the SIMULATED demo resource catalog."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_app_service
from ..schemas.responses import ErrorResponse, ResourceCatalogResponse
from ..service import ResQAIApplicationService

router = APIRouter(tags=["Resources"])

_FILTER_PATTERN = r"^[A-Za-z_]{1,40}$"


@router.get(
    "/resources",
    response_model=ResourceCatalogResponse,
    summary="List the simulated demo resource catalog",
    description=(
        "Returns the synthetic demo catalog used for resource matching. **Every entry is simulated** "
        "(`demo_only=true`): none are real emergency units and none reflect live availability."
    ),
    responses={
        422: {"model": ErrorResponse, "description": "A query filter was malformed."},
        503: {"model": ErrorResponse, "description": "The demo catalog is not loaded."},
    },
)
def list_resources(
    resource_type: Annotated[Optional[str], Query(pattern=_FILTER_PATTERN, description="e.g. ambulance, fire_response")] = None,
    availability_status: Annotated[Optional[str], Query(pattern=_FILTER_PATTERN, description="e.g. available, unavailable")] = None,
    service: ResQAIApplicationService = Depends(get_app_service),
) -> ResourceCatalogResponse:
    return service.list_resources(resource_type, availability_status)
