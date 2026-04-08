from __future__ import annotations

from datetime import datetime, timezone

from token_usage.formatters.statusbar import format_compact

RESET = datetime(2026, 4, 8, 2, 0, 0, tzinfo=timezone.utc)


def test_baseline_format() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert "C 55%" in result
    assert " w " not in result
    assert "@" in result
    assert result.startswith("| ")
    assert result.endswith(" ")


def test_with_openai() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    openai = {"available": True, "primary_pct": 0.0}
    result = format_compact(summary, openai)
    assert "C 55%" in result
    assert "O 0%" in result
    assert "| " in result


def test_weekly_warn_above_threshold() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 87.5,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert "w 88%" in result


def test_claude_error() -> None:
    summary = {"available": False, "error": "x"}
    result = format_compact(summary, None)
    assert "C err" in result


def test_stale_marker() -> None:
    summary = {
        "available": True,
        "_stale": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert "C 55%*" in result


def test_no_reset_when_missing() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": None,
    }
    result = format_compact(summary, None)
    assert "@" not in result


def test_iso_string_reset_parses() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": "2026-04-08T02:00:00+00:00",
    }
    result = format_compact(summary, None)
    assert "@" in result
