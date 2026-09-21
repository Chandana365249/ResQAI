"""
api/config.py

Single source of truth for the Phase 4 API's version, URL prefix and
environment-driven settings. No secrets are read or required: every
setting here is a non-sensitive, local-development knob.

Environment variables (all optional):

    RESQAI_ENV                       free-text environment label (default "local")
    RESQAI_LOG_LEVEL                 DEBUG | INFO | WARNING | ERROR | CRITICAL (default INFO)
    RESQAI_ALLOWED_ORIGINS           comma-separated CORS origins
                                     (default: common local frontend dev servers)
    RESQAI_REQUIRE_MODELS            true/false. When true, /ready reports NOT_READY unless
                                     BOTH severity models are loaded (default false)
    RESQAI_BOOTSTRAP_MODELS          true/false. When true, verify/download the model
                                     artifacts listed in deployment/model_artifacts.json at
                                     startup (default false: local dev uses your own models/)
    RESQAI_MODEL_ARTIFACT_BASE_URL   optional override of the manifest's artifact base URL
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple


def _read_version() -> str:
    """The ONE authoritative release version lives in the repository-root VERSION file.
    Missing/empty is a hard error (a silently wrong version is worse than none)."""
    version_file = Path(__file__).resolve().parents[2] / "VERSION"
    version = version_file.read_text(encoding="utf-8").strip()
    if not version:
        raise RuntimeError("VERSION file is empty.")
    return version


API_VERSION = _read_version()
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


_TRUE_VALUES = ("1", "true", "yes", "on")
_FALSE_VALUES = ("0", "false", "no", "off", "")


def _parse_bool(name: str, raw: str) -> bool:
    value = raw.strip().lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(f"{name}={raw!r} is invalid; use true or false.")


@dataclass(frozen=True)
class Settings:
    environment: str
    log_level: str
    allowed_origins: Tuple[str, ...]
    require_models: bool = False
    bootstrap_models: bool = False
    model_artifact_base_url: Optional[str] = None


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
        # An origin never has a trailing slash; a stray one would silently fail every CORS check.
        origins = tuple(o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip())

    return Settings(
        environment=source.get("RESQAI_ENV", "local").strip() or "local",
        log_level=log_level,
        allowed_origins=origins,
        require_models=_parse_bool("RESQAI_REQUIRE_MODELS", source.get("RESQAI_REQUIRE_MODELS", "false")),
        bootstrap_models=_parse_bool("RESQAI_BOOTSTRAP_MODELS", source.get("RESQAI_BOOTSTRAP_MODELS", "false")),
        model_artifact_base_url=(source.get("RESQAI_MODEL_ARTIFACT_BASE_URL", "").strip().rstrip("/") or None),
    )
