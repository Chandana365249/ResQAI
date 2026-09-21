"""GET /api/v1/models -- safe metadata about the two severity models."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import get_app_service
from ..schemas.responses import ModelMetricsResponse, ModelsResponse
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


@router.get(
    "/models/metrics",
    response_model=ModelMetricsResponse,
    summary="Stored evaluation metrics for both severity models",
    description=(
        "Read-only view of the evaluation metrics computed at training time on a held-out CRSS 2024 "
        "test split (accuracy, macro precision/recall/F1, fatal-class recall, per-class scores). "
        "Nothing is retrained or recalculated by this endpoint. An entry is `available=false` if its "
        "stored metrics file cannot be read."
    ),
)
def describe_model_metrics(service: ResQAIApplicationService = Depends(get_app_service)) -> ModelMetricsResponse:
    return service.describe_model_metrics()
