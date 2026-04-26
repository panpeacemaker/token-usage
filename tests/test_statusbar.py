from __future__ import annotations

from datetime import datetime, timezone

from token_usage.formatters.statusbar import format_compact

RESET = datetime(2026, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
WEEKLY_RESET_DT = datetime(2026, 4, 14, 22, 0, 0, tzinfo=timezone.utc)
WEEKLY_RESET_EPOCH = int(WEEKLY_RESET_DT.timestamp())


def test_baseline_format() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert result == "c55%"


def test_no_leading_pipe_no_trailing_space() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert not result.startswith("|")
    assert not result.endswith(" ")


def test_with_openai() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    openai = {"available": True, "primary_pct": 0.0}
    result = format_compact(summary, openai)
    assert result == "c55% o0%"


def test_weekly_warn_above_threshold() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 87.5,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": None,
    }
    result = format_compact(summary, None)
    assert "c55%w88%" in result


def test_claude_error() -> None:
    result = format_compact({"available": False, "error": "x"}, None)
    assert result == "c err"


def test_stale_marker() -> None:
    summary = {
        "available": True,
        "_stale": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert result == "c55%*"


def test_no_5hour_reset_in_compact_output() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert "@" not in result


def test_openai_err_segment_visible_on_failure() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    openai = {"available": False, "error": "no access token"}
    result = format_compact(summary, openai)
    assert "o err" in result


def test_openai_weekly_warn_above_threshold() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    openai = {"available": True, "primary_pct": 0.0, "weekly_pct": 92.0}
    result = format_compact(summary, openai)
    assert "o0%w92%" in result


def test_kimi_segment_rendered_when_provided() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    kimi = {"available": True, "primary_pct": 23.0, "weekly_pct": 0.0}
    result = format_compact(summary, None, kimi)
    assert "k23%" in result


def test_kimi_err_segment_visible_on_failure() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    kimi = {"available": False, "error": "logged out"}
    result = format_compact(summary, None, kimi)
    assert "k err" in result


def test_bare_mode_drops_framing() -> None:
    summary = {"available": True, "five_hour_pct": 55.0, "seven_day_pct": 14.0, "five_hour_resets_at": RESET}
    result = format_compact(summary, None, None, bare=True)
    assert result == "c55%"


def test_empty_summary_with_only_kimi_renders_just_kimi() -> None:
    kimi = {"available": True, "primary_pct": 5.0}
    result = format_compact({}, None, kimi, bare=True)
    assert result == "k5%"


def test_no_segments_returns_empty_string() -> None:
    assert format_compact({}, None, None) == ""


def test_three_provider_combined_matches_target_visual() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 73.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    openai = {
        "available": True,
        "primary_pct": 0.0,
        "weekly_pct": 100.0,
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    kimi = {"available": True, "primary_pct": 0.0, "weekly_pct": 0.0}
    result = format_compact(summary, openai, kimi)
    parts = result.split(" ")
    assert parts[0] == "c73%"
    assert parts[1].startswith("o0%w100%@")
    assert parts[2] == "k0%"


def test_claude_weekly_reset_shown_when_warn() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 92.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert result.startswith("c30%w92%@")
    assert any(day in result for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))


def test_claude_weekly_reset_hidden_when_below_threshold() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 50.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert result == "c30%"


def test_openai_weekly_reset_shown_when_warn() -> None:
    openai = {
        "available": True,
        "primary_pct": 0.0,
        "weekly_pct": 100.0,
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    result = format_compact({}, openai)
    assert result.startswith("o0%w100%@")
    assert any(day in result for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))


def test_kimi_weekly_reset_shown_when_warn() -> None:
    kimi = {
        "available": True,
        "primary_pct": 0.0,
        "weekly_pct": 95.0,
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    result = format_compact({}, None, kimi)
    assert result.startswith("k0%w95%@")
    assert any(day in result for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))


def test_weekly_reset_missing_does_not_break_rendering() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 92.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": None,
    }
    result = format_compact(summary, None)
    assert result == "c30%w92%"
