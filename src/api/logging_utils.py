"""
api/logging_utils.py

Small structured (key=value) logging helper for the API layer.

Privacy rule: callers pass identifiers, counts, statuses and timings
ONLY -- never report text, coordinates, or contact details. Values are
still passed through a sanitiser so a stray newline or oversized value
cannot forge log lines.
"""

from __future__ import annotations

import logging
import re
from typing import Any

_UNSAFE = re.compile(r"[\r\n\t]+")
_MAX_VALUE_LENGTH = 200


def _clean(value: Any) -> str:
    return _UNSAFE.sub(" ", str(value))[:_MAX_VALUE_LENGTH]


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    """Emit `event=<name> key=value ...` at the given level."""
    if not logger.isEnabledFor(level):
        return
    parts = " ".join(f"{k}={_clean(v)}" for k, v in fields.items())
    logger.log(level, "event=%s %s", event, parts)


def configure_api_logging(level_name: str) -> None:
    """Set the 'resqai.api' logger level and ensure it has one stream handler.

    Uvicorn configures its own loggers only, so without this the API's
    INFO events would be dropped. Idempotent (safe to call per app instance).
    """
    api_logger = logging.getLogger("resqai.api")
    api_logger.setLevel(getattr(logging, level_name))
    if not api_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        api_logger.addHandler(handler)
