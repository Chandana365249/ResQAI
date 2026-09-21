"""
api/config.py

Single source of truth for the Phase 4 API's version, URL prefix and
environment-driven settings. No secrets are read or required: every
setting here is a non-sensitive, local-development knob.

Environment variables (all optional):

    RESQAI_ENV              free-text environment label (default "local")
    RESQAI_LOG_LEVEL        DEBUG | INFO | WARNING | ERROR | CRITICAL (default INFO)
    RESQAI_ALLOWED_ORIGINS  comma-separated CORS origins
                            (default: common local frontend dev servers)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

API_VERSION = "0.1.0"
API_PREFIX = "/api/v1"
SERVICE_NAME = "ResQAI"

# Local frontend dev servers only (Vite default 5173, CRA/Next default 3000).
# No production domain is hard-coded -- set RESQAI_ALLOWED_ORIGINS for that.
DEFAULT_ALLOWED_ORIGINS: Tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)

_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


@dataclass(frozen=True)
class Settings:
    environment: str
    log_level: str
    allowed_origins: Tuple[str, ...]


def load_settings(env: Optional[Mapping[str, str]] = None) -> Settings:
    """Build Settings from environment variables (or a supplied mapping, for tests).

    Raises ValueError on an invalid log level rather than silently
    falling back, so a typo in configuration is visible at startup.
    """
    source = os.environ if env is None else env

    log_level = source.get("RESQAI_LOG_LEVEL", "INFO").strip().upper()
    if log_level not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"RESQAI_LOG_LEVEL={log_level!r} is invalid; expected one of {list(_VALID_LOG_LEVELS)}."
        )

    raw_origins = source.get("RESQAI_ALLOWED_ORIGINS")
    if raw_origins is None:
        origins = DEFAULT_ALLOWED_ORIGINS
    else:
        origins = tuple(o.strip() for o in raw_origins.split(",") if o.strip())

    return Settings(
        environment=source.get("RESQAI_ENV", "local").strip() or "local",
        log_level=log_level,
        allowed_origins=origins,
    )
