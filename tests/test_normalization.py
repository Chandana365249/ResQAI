"""Tests for src/normalization.py."""

from src.normalization import normalize_text


def test_collapses_whitespace():
    assert normalize_text("Two   cars\n\ncollided") == "two cars collided"


def test_lowercases():
    assert normalize_text("FOUR PEOPLE INJURED") == "four people injured"


def test_expands_known_abbreviations():
    assert "with" in normalize_text("car crash w/ injuries")
    assert "vehicle" in normalize_text("veh fire reported")


def test_normalizes_curly_quotes_and_dashes():
    result = normalize_text("driver’s vehicle – damaged")
    assert "’" not in result
    assert "–" not in result


def test_idempotent():
    text = "Two Cars   Collided w/ Injuries"
    once = normalize_text(text)
    twice = normalize_text(once)
    assert once == twice


def test_does_not_mutate_input_string():
    original = "Four People Injured"
    normalize_text(original)
    assert original == "Four People Injured"
