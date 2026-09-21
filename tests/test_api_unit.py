"""
Phase 4 API -- UNIT tests (no HTTP, no models): configuration, request-schema
validation, logging helper, response-mapping helpers.
"""

import logging

import pytest
from pydantic import ValidationError

from src.api.config import DEFAULT_ALLOWED_ORIGINS, load_settings
from src.api.logging_utils import log_event
from src.api.mapping import _json_safe, filter_resources
from src.api.schemas.requests import AnalyzeRequest
from src.resource_engine import Resource
from src.schemas import MAX_RAW_TEXT_LENGTH


# ---------------------------------------------------------------- configuration


def test_settings_defaults_use_local_dev_origins_only():
    s = load_settings({})
    assert s.environment == "local"
    assert s.log_level == "INFO"
    assert s.allowed_origins == DEFAULT_ALLOWED_ORIGINS
    assert "*" not in s.allowed_origins


def test_settings_read_environment_variables():
    s = load_settings({
        "RESQAI_ENV": "staging", "RESQAI_LOG_LEVEL": "debug",
        "RESQAI_ALLOWED_ORIGINS": "https://a.example, https://b.example ,",
    })
    assert (s.environment, s.log_level) == ("staging", "DEBUG")
    assert s.allowed_origins == ("https://a.example", "https://b.example")


def test_invalid_log_level_is_rejected_not_silently_ignored():
    with pytest.raises(ValueError):
        load_settings({"RESQAI_LOG_LEVEL": "LOUD"})


# ---------------------------------------------------------------- request schema


def test_valid_request_and_trimming():
    req = AnalyzeRequest(raw_text="  A car crashed.  ", report_id="demo-001", source="demo")
    assert req.raw_text == "A car crashed."


@pytest.mark.parametrize("payload", [
    {},                                                      # raw_text missing
    {"raw_text": ""},
    {"raw_text": "   "},
    {"raw_text": "x" * (MAX_RAW_TEXT_LENGTH + 1)},
    {"raw_text": "ok", "latitude": 91, "longitude": 0},
    {"raw_text": "ok", "latitude": 0, "longitude": 181},
    {"raw_text": "ok", "latitude": 10.0},                   # lat without lon
    {"raw_text": "ok", "latitude": float("nan"), "longitude": 0},
    {"raw_text": "ok", "timestamp": "yesterday-ish"},
    {"raw_text": "ok", "report_id": "has spaces/and;symbols"},
    {"raw_text": "ok", "report_id": "x" * 101},
    {"raw_text": "ok", "source": "s" * 51},
    {"raw_text": "ok", "unexpected_field": 1},
])
def test_invalid_requests_are_rejected(payload):
    with pytest.raises(ValidationError):
        AnalyzeRequest(**payload)


def test_max_length_text_is_accepted():
    assert AnalyzeRequest(raw_text="x" * MAX_RAW_TEXT_LENGTH).raw_text


def test_timestamp_is_validated_but_never_rewritten():
    req = AnalyzeRequest(raw_text="ok", timestamp="2026-09-19T10:30:00+05:30")
    assert req.timestamp == "2026-09-19T10:30:00+05:30"


# ---------------------------------------------------------------- logging helper


def test_log_event_sanitises_newlines_and_truncates(caplog):
    logger = logging.getLogger("resqai.api.test")
    with caplog.at_level(logging.INFO, logger="resqai.api.test"):
        log_event(logger, logging.INFO, "demo", note="line1\nFORGED event=x", big="y" * 1000)
    line = caplog.records[0].getMessage()
    assert "\n" not in line
    assert len(line) < 500


# ---------------------------------------------------------------- mapping helpers


def _res(rid, rtype, status):
    return Resource(rid, rtype, rid, 1.0, 1.0, status, 1, [rtype], True)


def test_json_safe_never_returns_python_reprs():
    assert _json_safe(["a", ("b",)]) == ["a", ["b"]]
    assert _json_safe(object()).startswith("<object")  # stringified, not a live object
    assert _json_safe(None) is None


def test_filter_resources_exact_case_insensitive():
    catalog = [_res("A1", "ambulance", "available"), _res("A2", "ambulance", "unavailable"), _res("F1", "fire_response", "available")]
    assert [r.resource_id for r in filter_resources(catalog, "AMBULANCE", None)] == ["A1", "A2"]
    assert [r.resource_id for r in filter_resources(catalog, "ambulance", "available")] == ["A1"]
    assert filter_resources(catalog, "helicopter", None) == []
    assert len(filter_resources(catalog, None, None)) == 3
