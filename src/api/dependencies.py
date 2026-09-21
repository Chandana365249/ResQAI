"""
api/dependencies.py

FastAPI dependency providers. The application service lives on
`app.state` (created in the lifespan, see main.py) rather than in a
module-level global, so each app instance -- including those built for
tests -- owns its own state and dependencies stay trivially overridable.
"""

from __future__ import annotations

from fastapi import Request

from .config import Settings
from .service import ResQAIApplicationService


def get_app_service(request: Request) -> ResQAIApplicationService:
    return request.app.state.app_service


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
