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


def test_openai_err_segment_visible_on_failure() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    openai = {"available": False, "error": "no access token"}
    result = format_compact(summary, openai)
    assert "O err" in result


def test_openai_weekly_warn_above_threshold() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    openai = {"available": True, "primary_pct": 0.0, "weekly_pct": 92.0}
    result = format_compact(summary, openai)
    assert "O 0% w 92%" in result


def test_kimi_segment_rendered_when_provided() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    kimi = {"available": True, "primary_pct": 23.0, "weekly_pct": 0.0}
    result = format_compact(summary, None, kimi)
    assert "K 23%" in result


def test_kimi_err_segment_visible_on_failure() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    kimi = {"available": False, "error": "logged out"}
    result = format_compact(summary, None, kimi)
    assert "K err" in result


def test_bare_mode_drops_framing() -> None:
    summary = {"available": True, "five_hour_pct": 55.0, "seven_day_pct": 14.0, "five_hour_resets_at": RESET}
    result = format_compact(summary, None, None, bare=True)
    assert result.startswith("C ")
    assert not result.startswith("| ")
    assert not result.endswith(" ")


def test_empty_summary_with_only_kimi_renders_just_kimi() -> None:
    kimi = {"available": True, "primary_pct": 5.0}
    result = format_compact({}, None, kimi, bare=True)
    assert result == "K 5%"


def test_no_segments_returns_empty_string() -> None:
    assert format_compact({}, None, None) == ""


WEEKLY_RESET_DT = datetime(2026, 4, 14, 22, 0, 0, tzinfo=timezone.utc)
WEEKLY_RESET_EPOCH = int(WEEKLY_RESET_DT.timestamp())


def test_claude_weekly_reset_shown_when_warn() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 92.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert "w 92%" in result
    after_warn = result.split("w 92%", 1)[1]
    assert any(f"@{day}" in after_warn for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))


def test_claude_weekly_reset_hidden_when_below_threshold() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 50.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert "w " not in result
    for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        assert day not in result


def test_openai_weekly_reset_shown_when_warn() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    openai = {
        "available": True,
        "primary_pct": 0.0,
        "weekly_pct": 100.0,
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    result = format_compact(summary, openai)
    o_segment = result.split("O ", 1)[1]
    assert "w 100%" in o_segment
    assert any(day in o_segment for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))


def test_kimi_weekly_reset_shown_when_warn() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    kimi = {
        "available": True,
        "primary_pct": 0.0,
        "weekly_pct": 95.0,
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    result = format_compact(summary, None, kimi)
    assert "w 95%" in result
    k_segment = result.split("K ", 1)[1]
    assert any(day in k_segment for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))


def test_weekly_reset_missing_does_not_break_rendering() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 92.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": None,
    }
    result = format_compact(summary, None)
    assert "w 92%" in result
    assert "C 30%" in result
