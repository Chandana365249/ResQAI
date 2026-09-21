"""
api/errors.py

One consistent error envelope for every non-2xx response:

    {"error": {"code": "...", "message": "...", "request_id": "...", "details": [...]}}

Clients only ever see safe, generic messages. Technical detail
(exception text, tracebacks, paths) is logged server-side with the
request_id and never returned.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..schemas import ReportValidationError
from .logging_utils import log_event
from .schemas.responses import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger("resqai.api")

UNKNOWN_REQUEST_ID = "unknown"

_HTTP_ERROR_CODES = {
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
}


class ApiError(Exception):
    """An error with a deliberately client-safe message."""

    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ServiceUnavailableError(ApiError):
    status_code = 503
    code = "SERVICE_UNAVAILABLE"


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", UNKNOWN_REQUEST_ID)


def error_response(
    status_code: int, code: str, message: str, request_id: str, details: Optional[List[ErrorDetail]] = None
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, request_id=request_id, details=details))
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def internal_error_response(request_id: str) -> JSONResponse:
    return error_response(
        500, "INTERNAL_ERROR", "An internal error occurred. Please retry or contact the operator "
        "quoting the request_id.", request_id,
    )


def _validation_details(exc: RequestValidationError) -> List[ErrorDetail]:
    """Field-level problems only. Pydantic's `input` echo is deliberately dropped
    so a rejected report's text is never reflected back or logged."""
    details = []
    for err in exc.errors():
        loc = [str(p) for p in err.get("loc", ()) if p != "body"]
        details.append(ErrorDetail(field=".".join(loc) or None, message=str(err.get("msg", "Invalid value."))))
    return details


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, request_id_of(request))

    @app.exception_handler(ReportValidationError)
    async def _invalid_report(request: Request, exc: ReportValidationError) -> JSONResponse:
        # Defence in depth: the request schema normally catches these first.
        return error_response(400, "INVALID_REPORT", str(exc), request_id_of(request))

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = _validation_details(exc)
        log_event(logger, logging.INFO, "request_validation_failed",
                  request_id=request_id_of(request), fields=[d.field for d in details])
        return error_response(422, "VALIDATION_ERROR", "The request was not valid.", request_id_of(request), details)

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_ERROR_CODES.get(exc.status_code, "HTTP_ERROR")
        message = {404: "The requested resource was not found.", 405: "Method not allowed for this endpoint."}.get(
            exc.status_code, "The request could not be processed."
        )
        return error_response(exc.status_code, code, message, request_id_of(request))
