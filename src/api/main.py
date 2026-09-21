"""
api/main.py

FastAPI application entrypoint. Run from the PROJECT ROOT (model/resource
paths in the existing core are relative to it):

    python -m uvicorn src.api.main:app --reload

`create_app()` is a factory so tests can build isolated app instances
with their own settings and (fake) services; `app` is the default
instance uvicorn serves.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import API_PREFIX, API_VERSION, SERVICE_NAME, Settings, load_settings
from .errors import UNKNOWN_REQUEST_ID, internal_error_response, register_exception_handlers
from .logging_utils import configure_api_logging, log_event
from .routes import analyze, health, models, resources
from .service import ResQAIApplicationService

logger = logging.getLogger("resqai.api")

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{8,64}$")

_DESCRIPTION = """
**ResQAI** is an AI-assisted emergency-response **decision-support prototype**.

It accepts a free-text emergency report, extracts structured incident information (with evidence and
uncertainty), detects rule-based operational risks, predicts crash severity with an ML model *only when
legitimately possible*, and matches **simulated demo resources**.

**It is not** an autonomous dispatch system, medical diagnosis or triage software, a replacement for
emergency personnel, or a source of live emergency-service availability. Every analysis requires
**human review**.
"""

_TAGS_METADATA = [
    {"name": "Analysis", "description": "Analyze an emergency report end to end."},
    {"name": "Health", "description": "Liveness, component health and readiness."},
    {"name": "Resources", "description": "The simulated (demo-only) resource catalog."},
    {"name": "Models", "description": "Safe metadata about the severity models and their routing."},
]


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request_id, times the request, logs one structured line, and turns any
    unhandled exception into a safe 500 (details logged, never returned)."""

    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 -- last-resort boundary; must never leak internals
            logger.exception("event=unhandled_exception request_id=%s path=%s", request_id, request.url.path)
            response = internal_error_response(request_id)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        log_event(
            logger, logging.INFO, "request_completed", request_id=request_id, method=request.method,
            path=request.url.path, status=response.status_code, duration_ms=duration_ms,
        )
        return response


def create_app(
    settings: Optional[Settings] = None,
    app_service: Optional[ResQAIApplicationService] = None,
) -> FastAPI:
    settings = settings or load_settings()
    configure_api_logging(settings.log_level)
    service = app_service or ResQAIApplicationService(environment=settings.environment)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: load the demo catalog and warm both models ONCE; requests reuse them.
        service.start()
        yield

    app = FastAPI(
        title=f"{SERVICE_NAME} API",
        description=_DESCRIPTION,
        version=API_VERSION,
        openapi_tags=_TAGS_METADATA,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.app_service = service

    # add_middleware order: the LAST added is the OUTERMOST. CORS must wrap the
    # request-context middleware so even its 500 responses carry CORS headers.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,  # no cookie/credential auth exists in Phase 4
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    register_exception_handlers(app)

    for router_module in (analyze, health, resources, models):
        app.include_router(router_module.router, prefix=API_PREFIX)
    return app


app = create_app()

__all__ = ["app", "create_app", "UNKNOWN_REQUEST_ID"]
