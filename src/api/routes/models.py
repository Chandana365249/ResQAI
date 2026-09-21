"""GET /api/v1/models -- safe metadata about the two severity models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_app_service
from ..schemas.responses import ModelsResponse
from ..service import ResQAIApplicationService

router = APIRouter(tags=["Models"])


@router.get(
    "/models",
    response_model=ModelsResponse,
    summary="Describe the severity models and routing",
    description=(
        "Safe metadata for the Historical Model and the Report-Compatible Model, plus how "
        "`/analyze` routes between them. No file paths or model internals are exposed."
    ),
)
def describe_models(service: ResQAIApplicationService = Depends(get_app_service)) -> ModelsResponse:
    return service.describe_models()
