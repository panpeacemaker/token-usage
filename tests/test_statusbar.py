from __future__ import annotations

from datetime import datetime, timezone

from token_usage.formatters.statusbar import format_compact

RESET = datetime(2026, 4, 8, 2, 0, 0, tzinfo=timezone.utc)
WEEKLY_RESET_DT = datetime(2026, 4, 14, 22, 0, 0, tzinfo=timezone.utc)
WEEKLY_RESET_EPOCH = int(WEEKLY_RESET_DT.timestamp())

RESET_HHMM = RESET.astimezone().strftime("%H:%M")
WEEKLY_RESET_DAYHHMM = WEEKLY_RESET_DT.astimezone().strftime("%a%H:%M")


def test_baseline_format_includes_5h_reset() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert result == f"c55%@{RESET_HHMM}"


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


def test_with_openai_no_openai_reset() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    openai = {"available": True, "primary_pct": 0.0}
    result = format_compact(summary, openai)
    assert result == f"c55%@{RESET_HHMM} o0%"


def test_weekly_warn_above_threshold() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 87.5,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": None,
    }
    result = format_compact(summary, None)
    assert result == f"c55%@{RESET_HHMM}w88%"


def test_weekly_warn_threshold_is_80() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 10.0,
        "seven_day_pct": 80.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert result == f"c10%@{RESET_HHMM}w80%@{WEEKLY_RESET_DAYHHMM}"


def test_just_below_80_no_weekly_warn() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 10.0,
        "seven_day_pct": 79.9,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert result == f"c10%@{RESET_HHMM}"


def test_weekly_at_100_hides_5h_reset() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 100.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert result == f"c30%w100%@{WEEKLY_RESET_DAYHHMM}"


def test_weekly_at_99_keeps_5h_reset() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 99.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert result == f"c30%@{RESET_HHMM}w99%@{WEEKLY_RESET_DAYHHMM}"


def test_claude_error() -> None:
    result = format_compact({"available": False, "error": "x"}, None)
    assert result == "c err"


def test_stale_marker_precedes_reset_suffix() -> None:
    summary = {
        "available": True,
        "_stale": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert result == f"c55%*@{RESET_HHMM}"


def test_5h_reset_uses_hhmm_no_day_prefix() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
        "five_hour_resets_at": RESET,
    }
    result = format_compact(summary, None)
    assert "@" in result
    for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        assert day not in result


def test_5h_reset_omitted_when_no_reset_value() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 55.0,
        "seven_day_pct": 14.0,
    }
    result = format_compact(summary, None)
    assert result == "c55%"


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


def test_openai_5h_reset_rendered_when_present() -> None:
    openai = {
        "available": True,
        "primary_pct": 30.0,
        "weekly_pct": 10.0,
        "primary_reset_at": int(RESET.timestamp()),
    }
    result = format_compact({}, openai)
    assert result == f"o30%@{RESET_HHMM}"


def test_kimi_segment_rendered_when_provided() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    kimi = {"available": True, "primary_pct": 23.0, "weekly_pct": 0.0}
    result = format_compact(summary, None, kimi)
    assert "k23%" in result


def test_kimi_5h_reset_rendered_when_present() -> None:
    kimi = {
        "available": True,
        "primary_pct": 18.0,
        "weekly_pct": 10.0,
        "primary_reset_at": int(RESET.timestamp()),
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    result = format_compact({}, None, kimi)
    assert result == f"k18%@{RESET_HHMM}"


def test_kimi_err_segment_visible_on_failure() -> None:
    summary = {"available": True, "five_hour_pct": 1.0, "seven_day_pct": 1.0, "five_hour_resets_at": RESET}
    kimi = {"available": False, "error": "logged out"}
    result = format_compact(summary, None, kimi)
    assert "k err" in result


def test_bare_mode_keeps_5h_reset() -> None:
    summary = {"available": True, "five_hour_pct": 55.0, "seven_day_pct": 14.0, "five_hour_resets_at": RESET}
    result = format_compact(summary, None, None, bare=True)
    assert result == f"c55%@{RESET_HHMM}"


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
    assert parts[0] == f"c73%@{RESET_HHMM}"
    assert parts[1] == f"o0%w100%@{WEEKLY_RESET_DAYHHMM}"
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
    assert result == f"c30%@{RESET_HHMM}w92%@{WEEKLY_RESET_DAYHHMM}"


def test_claude_weekly_reset_hidden_when_below_threshold() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 50.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": WEEKLY_RESET_DT,
    }
    result = format_compact(summary, None)
    assert result == f"c30%@{RESET_HHMM}"


def test_openai_weekly_reset_shown_when_warn() -> None:
    openai = {
        "available": True,
        "primary_pct": 0.0,
        "weekly_pct": 100.0,
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    result = format_compact({}, openai)
    assert result == f"o0%w100%@{WEEKLY_RESET_DAYHHMM}"


def test_kimi_weekly_reset_shown_when_warn() -> None:
    kimi = {
        "available": True,
        "primary_pct": 0.0,
        "weekly_pct": 95.0,
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    result = format_compact({}, None, kimi)
    assert result == f"k0%w95%@{WEEKLY_RESET_DAYHHMM}"


def test_opencode_segment_rendered_when_provided() -> None:
    opencode = {
        "available": True,
        "primary_pct": 12.0,
        "weekly_pct": 5.0,
        "primary_reset_at": int(RESET.timestamp()),
    }
    result = format_compact({}, None, None, opencode)
    assert result == f"e12%@{RESET_HHMM}"


def test_opencode_err_segment_visible_on_failure() -> None:
    opencode = {"available": False, "error": "no db"}
    result = format_compact({}, None, None, opencode)
    assert result == "e err"


def test_opencode_weekly_warn_above_threshold() -> None:
    opencode = {
        "available": True,
        "primary_pct": 30.0,
        "weekly_pct": 90.0,
        "primary_reset_at": int(RESET.timestamp()),
        "weekly_reset_at": WEEKLY_RESET_EPOCH,
    }
    result = format_compact({}, None, None, opencode)
    assert result == f"e30%@{RESET_HHMM}w90%@{WEEKLY_RESET_DAYHHMM}"


def test_opencode_alongside_other_providers() -> None:
    summary = {"available": True, "five_hour_pct": 10.0, "seven_day_pct": 0.0, "five_hour_resets_at": RESET}
    openai = {"available": True, "primary_pct": 0.0, "weekly_pct": 0.0}
    kimi = {"available": True, "primary_pct": 5.0, "weekly_pct": 0.0}
    opencode = {"available": True, "primary_pct": 1.0, "weekly_pct": 0.0}
    result = format_compact(summary, openai, kimi, opencode)
    parts = result.split(" ")
    assert parts[0] == f"c10%@{RESET_HHMM}"
    assert parts[1] == "o0%"
    assert parts[2] == "k5%"
    assert parts[3] == "e1%"


def test_opencode_go_segment_rendered_when_provided() -> None:
    opencode_go = {
        "available": True,
        "primary_pct": 25.0,
        "weekly_pct": 8.0,
        "primary_reset_at": int(RESET.timestamp()),
    }
    result = format_compact({}, None, None, None, opencode_go)
    assert result == f"g25%@{RESET_HHMM}"


def test_opencode_go_err_segment_visible_on_failure() -> None:
    opencode_go = {"available": False, "error": "no db"}
    result = format_compact({}, None, None, None, opencode_go)
    assert result == "g err"


def test_opencode_and_go_both_rendered() -> None:
    opencode = {"available": True, "primary_pct": 1.0, "weekly_pct": 0.0}
    opencode_go = {"available": True, "primary_pct": 25.0, "weekly_pct": 0.0}
    result = format_compact({}, None, None, opencode, opencode_go)
    assert result == "e1% g25%"


def test_weekly_reset_missing_does_not_break_rendering() -> None:
    summary = {
        "available": True,
        "five_hour_pct": 30.0,
        "seven_day_pct": 92.0,
        "five_hour_resets_at": RESET,
        "seven_day_resets_at": None,
    }
    result = format_compact(summary, None)
    assert result == f"c30%@{RESET_HHMM}w92%"
