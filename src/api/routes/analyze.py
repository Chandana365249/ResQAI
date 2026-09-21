"""POST /api/v1/analyze -- thin route: validate (schema) -> service -> response schema."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..dependencies import get_app_service
from ..errors import request_id_of
from ..schemas.requests import AnalyzeRequest
from ..schemas.responses import AnalyzeResponse, ErrorResponse
from ..service import ResQAIApplicationService

router = APIRouter(tags=["Analysis"])


# Deliberately a plain `def`: the analysis is synchronous, CPU/model-bound
# work, so FastAPI runs it in its worker threadpool instead of blocking the
# event loop (an `async def` here would block it).
@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    summary="Analyze an emergency report",
    description=(
        "Runs the full ResQAI pipeline on one free-text emergency report: extraction with evidence "
        "and certainty, rule-based risk indicators and priority, an ML severity prediction when one "
        "can legitimately be made, and compatible SIMULATED demo resources.\n\n"
        "A successful analysis returns **200 even when no ML prediction is available** "
        "(`ml_prediction.available=false`, with reasons in `warnings`). This is decision support "
        "for a human responder, not automated dispatch."
    ),
    responses={
        422: {"model": ErrorResponse, "description": "The request body failed validation."},
        500: {"model": ErrorResponse, "description": "Unexpected internal error (details are logged, not returned)."},
        503: {"model": ErrorResponse, "description": "A required component is unavailable (see /ready)."},
    },
)
def analyze_report(
    payload: AnalyzeRequest,
    request: Request,
    service: ResQAIApplicationService = Depends(get_app_service),
) -> AnalyzeResponse:
    return service.analyze(payload, request_id=request_id_of(request))
