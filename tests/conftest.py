"""
Shared pytest configuration.

Inserts the project root onto sys.path so Phase 2 tests can import the
`src` package (`from src.report_parser import parse_report`, etc.).
Phase 1's tests/test_pipeline.py inserts the src/ directory itself and
uses bare imports (`from data_loader import ...`) -- both styles can
coexist since they add different entries to sys.path.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


import pytest  # noqa: E402  (appended for Phase 4 API tests)


@pytest.fixture(scope="session")
def real_api_client():
    """A TestClient over the REAL app/service (real models + demo catalog), started once per
    test session so the lifespan startup (model warm-up) is paid once. Phase 4 integration/E2E tests."""
    from fastapi.testclient import TestClient

    from src.api.main import create_app

    with TestClient(create_app()) as client:
        yield client
