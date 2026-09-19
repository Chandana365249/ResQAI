"""
utils/text_rules.py

Small, generic, well-documented text-matching primitives shared by the
deterministic extractor: clause splitting, negation detection, hedging
(uncertainty) detection, and number-word parsing.

These are intentionally simple, explainable heuristics (regex + a
fixed-size lookback window), not a statistical or ML language model.
Keeping them generic here (rather than duplicated per attribute in
extraction/deterministic.py) is what lets every extracted flag/count
share identical, testable negation and hedging behaviour.
"""

from __future__ import annotations

import re
from typing import List, Optional, Pattern, Tuple

from ..schemas import Certainty

# ---------------------------------------------------------------------------
# Clause splitting
# ---------------------------------------------------------------------------

# Split on sentence-ending punctuation. Clauses (not the whole report) are
# the unit negation/hedging is evaluated over, so a negation in one sentence
# ("No injuries.") never affects a match in a different sentence
# ("Fire is spreading.").
_CLAUSE_SPLIT_PATTERN = re.compile(r"(?<=[.!?;])\s+")


def split_clauses(normalized_text: str) -> List[str]:
    """Split normalized text into sentence-like clauses for local analysis."""
    if not normalized_text:
        return []
    return [c for c in _CLAUSE_SPLIT_PATTERN.split(normalized_text) if c.strip()]


# ---------------------------------------------------------------------------
# Negation
# ---------------------------------------------------------------------------

NEGATION_CUES = {
    "no", "not", "none", "without", "never", "nobody",
    "isn't", "wasn't", "aren't", "weren't",
    "doesn't", "don't", "didn't",
    "hasn't", "haven't", "hadn't",
    "cannot", "can't", "couldn't",
}

_WORD_PATTERN = re.compile(r"[a-z']+")


def _words_before(clause: str, index: int, window: int) -> List[str]:
    prefix = clause[:index].lower()
    return _WORD_PATTERN.findall(prefix)[-window:]


def is_negated_before(clause: str, match_start: int, window: int = 4) -> bool:
    """True if a negation cue appears within `window` words before the match.

    Examples that trigger negation (window=4):
        "no injuries were reported"     -> "injuries" negated by "no"
        "there is no fire visible"      -> "fire" negated by "no"
        "no one was trapped"            -> "trapped" negated by "no"
    """
    return any(w in NEGATION_CUES for w in _words_before(clause, match_start, window))


# ---------------------------------------------------------------------------
# Hedging / uncertainty
# ---------------------------------------------------------------------------

# Softer hedges -> POSSIBLE ("might be true, stated tentatively").
_SOFT_HEDGE_WORDS = {
    "may", "maybe", "possibly", "might", "perhaps",
    "appears", "appear", "seems", "seem", "reportedly", "likely", "think", "believe",
    "suspected",  # added Phase 3.5: e.g. "suspected speeding"
}

# Stronger hedges -> UNCERTAIN ("actively flagged as unknown/unconfirmed").
_STRONG_HEDGE_PHRASES = (
    "not sure if", "not sure whether", "not sure",
    "unclear if", "unclear whether", "unclear",
    "unconfirmed", "uncertain",
)


def hedge_certainty_in_clause(clause: str) -> Optional[Certainty]:
    """Return POSSIBLE/UNCERTAIN if the clause hedges its claim, else None.

    Checked at the clause (not whole-report) level so a hedge in one
    sentence doesn't bleed into an unrelated, plainly-stated sentence.
    """
    lower = clause.lower()
    for phrase in _STRONG_HEDGE_PHRASES:
        if phrase in lower:
            return Certainty.UNCERTAIN
    words = set(_WORD_PATTERN.findall(lower))
    if words & _SOFT_HEDGE_WORDS:
        return Certainty.POSSIBLE
    return None


def classify_match(clause: str, match_start: int, window: int = 4) -> Tuple[bool, Certainty]:
    """Decide the (boolean value, certainty) for a keyword match in a clause.

    This is the single shared decision point used for every boolean
    attribute the deterministic extractor produces:
      1. negated  -> (False, CONFIRMED)   e.g. "no fire" is a confirmed negative
      2. hedged   -> (True, POSSIBLE/UNCERTAIN)
      3. neither  -> (True, CONFIRMED)
    """
    if is_negated_before(clause, match_start, window=window):
        return False, Certainty.CONFIRMED
    hedge = hedge_certainty_in_clause(clause)
    if hedge is not None:
        return True, hedge
    return True, Certainty.CONFIRMED


# ---------------------------------------------------------------------------
# Number words
# ---------------------------------------------------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12,
}

# Regex fragment matching a digit or a spelled-out number word one-twelve.
# Deliberately excludes vague quantities ("a few", "several", "a couple") --
# turning those into an exact integer would fabricate precision the report
# never gave.
NUMBER_TOKEN_PATTERN = r"(?:\d+|" + "|".join(_NUMBER_WORDS) + ")"


def word_to_number(token: str) -> Optional[int]:
    """Parse a digit string or a spelled-out number word (one-twelve)."""
    token = token.lower().strip()
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token)


def find_first_match(pattern: Pattern, clauses: List[str]) -> Optional[Tuple[str, re.Match]]:
    """Return the (clause, match) for the first clause where `pattern` matches."""
    for clause in clauses:
        m = pattern.search(clause)
        if m:
            return clause, m
    return None
