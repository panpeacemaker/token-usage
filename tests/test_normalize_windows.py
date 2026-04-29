from __future__ import annotations

from token_usage._normalize import (
    KIMI_WINDOW_FIELDS,
    OPENAI_WINDOW_FIELDS,
    OPENCODE_WINDOW_FIELDS,
    normalize_windows,
)

NOW = 1_777_400_000
PAST = NOW - 3600
FUTURE = NOW + 3600


def test_none_payload_returns_none():
    assert normalize_windows(None, OPENAI_WINDOW_FIELDS, now=NOW) is None


def test_unavailable_payload_left_intact():
    p = {"available": False, "primary_pct": 50, "primary_reset_at": PAST}
    out = normalize_windows(p, OPENAI_WINDOW_FIELDS, now=NOW)
    assert out["primary_pct"] == 50
    assert out["primary_reset_at"] == PAST


def test_expired_primary_rolls_to_zero():
    p = {
        "available": True,
        "primary_pct": 80.0,
        "primary_reset_at": PAST,
        "weekly_pct": 50.0,
        "weekly_reset_at": FUTURE,
    }
    out = normalize_windows(p, KIMI_WINDOW_FIELDS, now=NOW)
    assert out["primary_pct"] == 0.0
    assert out["primary_reset_at"] is None
    assert out["weekly_pct"] == 50.0
    assert out["weekly_reset_at"] == FUTURE


def test_expired_weekly_rolls_to_zero():
    p = {
        "available": True,
        "primary_pct": 10.0,
        "primary_reset_at": FUTURE,
        "weekly_pct": 100.0,
        "weekly_reset_at": PAST,
    }
    out = normalize_windows(p, KIMI_WINDOW_FIELDS, now=NOW)
    assert out["primary_pct"] == 10.0
    assert out["primary_reset_at"] == FUTURE
    assert out["weekly_pct"] == 0.0
    assert out["weekly_reset_at"] is None


def test_review_window_expired_normalized_for_chatgpt():
    p = {
        "available": True,
        "primary_pct": 0.0,
        "primary_reset_at": FUTURE,
        "weekly_pct": 0.0,
        "weekly_reset_at": FUTURE,
        "review_pct": 30.0,
        "review_reset_at": PAST,
    }
    out = normalize_windows(p, OPENAI_WINDOW_FIELDS, now=NOW)
    assert out["review_pct"] == 0.0
    assert out["review_reset_at"] is None


def test_no_reset_field_left_intact():
    p = {"available": True, "primary_pct": 30.0, "primary_reset_at": None}
    out = normalize_windows(p, KIMI_WINDOW_FIELDS, now=NOW)
    assert out["primary_pct"] == 30.0
    assert out["primary_reset_at"] is None


def test_invalid_reset_field_left_intact():
    p = {"available": True, "primary_pct": 30.0, "primary_reset_at": "garbage"}
    out = normalize_windows(p, KIMI_WINDOW_FIELDS, now=NOW)
    assert out["primary_pct"] == 30.0
    assert out["primary_reset_at"] == "garbage"


def test_opencode_uses_primary_and_weekly():
    p = {
        "available": True,
        "primary_pct": 80.0,
        "primary_reset_at": PAST,
        "weekly_pct": 60.0,
        "weekly_reset_at": PAST,
    }
    out = normalize_windows(p, OPENCODE_WINDOW_FIELDS, now=NOW)
    assert out["primary_pct"] == 0.0
    assert out["primary_reset_at"] is None
    assert out["weekly_pct"] == 0.0
    assert out["weekly_reset_at"] is None


def test_reset_at_exactly_now_is_treated_as_expired():
    p = {"available": True, "primary_pct": 50.0, "primary_reset_at": NOW}
    out = normalize_windows(p, KIMI_WINDOW_FIELDS, now=NOW)
    assert out["primary_pct"] == 0.0
    assert out["primary_reset_at"] is None
