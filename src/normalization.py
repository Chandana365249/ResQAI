"""
normalization.py

Text Normalizer: turns validated raw report text into a cleaned form
that the extractor can match patterns against reliably.

This layer is deliberately conservative. It never rewrites words in a
way that could change meaning (e.g. it will NOT map "no fire" to
"fire" or resolve synonyms by deleting/replacing content words) --
synonym handling for concepts like "car crash" / "vehicle collision"
is done in extraction/deterministic.py via multiple keyword patterns
that all point at the same attribute, not by mutating the text itself.
The ORIGINAL raw text is always preserved separately
(IncidentReport.raw_text); normalized_text is an additional field, not
a replacement.

What this layer does:
  - collapse repeated/irregular whitespace
  - lowercase (matching is case-insensitive by design)
  - normalize a few punctuation variants (curly quotes, em/en dashes)
    that would otherwise silently break regex matching
  - expand a small, explicit set of unambiguous abbreviations
"""

from __future__ import annotations

import re

# Only abbreviations with a single, unambiguous expansion are included.
# Anything even mildly ambiguous (e.g. "acc" could be "accident" or
# "account") is deliberately left out to avoid changing meaning.
ABBREVIATION_EXPANSIONS = {
    # "\b" does not match between "/" and a following space (neither side is
    # a word character), so these use a lookahead instead of a trailing "\b".
    r"\bw/o(?=\s|$)": "without",
    r"\bw/(?=\s|$)": "with",
    r"\bveh\b": "vehicle",
    r"\bvehs\b": "vehicles",
    r"\bpax\b": "passengers",
    r"\bmc\b": "motorcycle",
    r"&": "and",
}

_WHITESPACE_PATTERN = re.compile(r"\s+")

_PUNCTUATION_NORMALIZATION = {
    "‘": "'", "’": "'",   # curly single quotes
    "“": '"', "”": '"',   # curly double quotes
    "–": "-", "—": "-",   # en/em dash
}


def normalize_text(raw_text: str) -> str:
    """Produce a cleaned, lowercase version of raw_text for rule matching.

    Idempotent: normalize_text(normalize_text(x)) == normalize_text(x).
    """
    text = raw_text
    for original, replacement in _PUNCTUATION_NORMALIZATION.items():
        text = text.replace(original, replacement)

    text = text.lower()

    for pattern, expansion in ABBREVIATION_EXPANSIONS.items():
        text = re.sub(pattern, expansion, text)

    text = _WHITESPACE_PATTERN.sub(" ", text).strip()
    return text
