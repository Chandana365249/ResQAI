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
