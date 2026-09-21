"""GET /api/v1/health (liveness + component status) and /api/v1/ready (readiness)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ..dependencies import get_app_service
from ..schemas.responses import HealthResponse, ReadinessResponse
from ..service import ResQAIApplicationService

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and component health",
    description=(
        "Reports whether the API process is alive plus the checked status of each component. "
        "`healthy`: everything works. `degraded`: analysis works but a severity model is unavailable. "
        "`unavailable`: a required component (parser, risk/decision engine, resource catalog) is down. "
        "Always HTTP 200 -- read the `status` field; use /ready for load-balancer decisions."
    ),
)
def health(service: ResQAIApplicationService = Depends(get_app_service)) -> HealthResponse:
    return service.health()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness to serve analysis requests",
    description=(
        "`READY` (HTTP 200) when every required component is available. `NOT_READY` (HTTP 503) otherwise. "
        "A missing severity model does not make the service NOT_READY, because analysis still works "
        "without an ML prediction."
    ),
    responses={503: {"model": ReadinessResponse, "description": "NOT_READY: a required component is unavailable."}},
)
def ready(service: ResQAIApplicationService = Depends(get_app_service)):
    result = service.readiness()
    if result.status == "READY":
        return result
    return JSONResponse(status_code=503, content=result.model_dump(exclude_none=True))
