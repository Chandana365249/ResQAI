"""
utils/pii.py

Lightweight, best-effort PII redaction for LOGGING and TEST OUTPUT
purposes only.

IMPORTANT LIMITATION: this is a small set of regexes for common,
structurally-recognizable identifiers (emails, phone numbers). It is
NOT a general-purpose PII detector -- it will not reliably find
person names, exact street addresses written in free text, or other
unstructured personal information. Do not rely on this for any legal
or regulatory compliance claim; none is made here.

Usage guidance for this project: reusable modules should never log a
full raw report at INFO level. Where a snippet of report text is
useful for debugging, pass it through `redact_pii()` first and prefer
DEBUG level.
"""

from __future__ import annotations

import re

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Matches common phone formats: (123) 456-7890, 123-456-7890, 123.456.7890,
# +1 123 456 7890, 1234567890 (7-15 digits with optional separators).
_PHONE_PATTERN = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3,4}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,4})?"
)


def redact_pii(text: str) -> str:
    """Replace likely emails/phone numbers in `text` with redaction markers.

    Best-effort only -- see module docstring for scope and limits.
    """
    if not text:
        return text
    redacted = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    redacted = _PHONE_PATTERN.sub(_maybe_redact_phone, redacted)
    return redacted


def _maybe_redact_phone(match: re.Match) -> str:
    """Only redact matches with enough digits to plausibly be a phone number.

    Guards against the broad phone regex eating short numbers like a
    single injury count ("4 people injured") by requiring >= 7 digits.
    """
    digits = re.sub(r"\D", "", match.group(0))
    return "[REDACTED_PHONE]" if len(digits) >= 7 else match.group(0)
