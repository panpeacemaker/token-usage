from __future__ import annotations

import time
from datetime import datetime, timezone

from token_usage.formatters.detail import _fmt_local_time, format_detail


def _base_summary(**overrides) -> dict:
    base = {
        "available": True,
        "five_hour_pct": 42.0,
        "five_hour_resets_at": "2026-04-10T14:00:00+00:00",
        "seven_day_pct": 15.0,
        "seven_day_resets_at": "2026-04-15T22:00:00+00:00",
        "subscription_type": "claude-code",
        "rate_limit_tier": "max5",
        "_source": "statusline",
        "local": {"total_entries": 0},
    }
    base.update(overrides)
    return base


def test_basic_output():
    out = format_detail(_base_summary())
    assert "Claude" in out
    assert "42.0%" in out
    assert "15.0%" in out


def test_source_detail_display():
    s = _base_summary(
        _source="oauth",
        _source_detail={
            "chosen": "oauth",
            "rejected": [
                {"source": "statusline", "reason": "file missing"},
            ],
            "statusline_age_s": None,
        },
    )
    out = format_detail(s)
    assert "source: oauth (statusline: missing)" in out


def test_source_detail_stale_display():
    s = _base_summary(
        _source="oauth",
        _source_detail={
            "chosen": "oauth",
            "rejected": [
                {"source": "statusline", "reason": "file age 720s > 600s max"},
            ],
            "statusline_age_s": 720,
        },
    )
    out = format_detail(s)
    assert "source: oauth (statusline: stale)" in out


def test_source_detail_expired_display():
    s = _base_summary(
        _source="oauth",
        _source_detail={
            "chosen": "oauth",
            "rejected": [
                {"source": "statusline", "reason": "5h window expired at 2026-04-08T10:00:00+00:00"},
            ],
            "statusline_age_s": 60,
        },
    )
    out = format_detail(s)
    assert "source: oauth (statusline: expired)" in out


def test_source_detail_multiple_rejected():
    s = _base_summary(
        _source="local",
        _source_detail={
            "chosen": "local",
            "rejected": [
                {"source": "statusline", "reason": "file missing"},
                {"source": "oauth", "reason": "http 429: Too Many Requests"},
            ],
            "statusline_age_s": None,
        },
    )
    out = format_detail(s)
    assert "source: local (statusline: missing; oauth: http 429: Too Many Requests)" in out


def test_stale_marker():
    s = _base_summary(
        _stale=True,
        _stale_reason="oauth failed (http 429); no local data; using expired statusline",
        _fetched_at=time.time() - 120,
    )
    out = format_detail(s)
    assert "[STALE]" in out
    assert "oauth failed" in out
    assert "cached data" in out


def test_stale_without_fetched_at():
    s = _base_summary(_stale=True, _stale_reason="unknown")
    out = format_detail(s)
    assert "[STALE]" in out
    assert "showing cached data" in out


def test_opus_and_sonnet_pct():
    s = _base_summary(seven_day_opus_pct=8.5, seven_day_sonnet_pct=6.5)
    out = format_detail(s)
    assert "opus" in out
    assert "8.5%" in out
    assert "sonnet" in out
    assert "6.5%" in out


def test_unavailable():
    s = _base_summary(available=False, error="no source")
    out = format_detail(s)
    assert "unavailable" in out
    assert "no source" in out


def test_local_block_stats():
    s = _base_summary(
        local={
            "active_block": {"present": True, "tokens": 50000, "models": {"claude-sonnet-4-6": 50000}},
            "week": {"messages": 10, "tokens": 100000},
            "total_entries": 42,
        }
    )
    out = format_detail(s)
    assert "50,000" in out
    assert "Local JSONL" in out


def test_openai_section():
    openai = {"available": True, "primary_pct": 30.0, "review_pct": 5.0}
    out = format_detail(_base_summary(), openai)
    assert "ChatGPT Plus" in out
    assert "30.0%" in out


def test_openai_unavailable():
    openai = {"available": False, "error": "cookie extraction failed"}
    out = format_detail(_base_summary(), openai)
    assert "cookie extraction failed" in out


def test_kimi_section_rendered_when_provided():
    kimi = {
        "available": True,
        "primary_pct": 18.0,
        "weekly_pct": 10.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
    }
    out = format_detail(_base_summary(), None, kimi)
    assert "Kimi Code" in out
    assert "5-hour:" in out
    assert "18.0%" in out
    assert "weekly:" in out
    assert "10.0%" in out


def test_kimi_unavailable():
    kimi = {"available": False, "error": "logged out"}
    out = format_detail(_base_summary(), None, kimi)
    assert "Kimi Code" in out
    assert "logged out" in out


def test_only_kimi_skips_claude_and_chatgpt_sections():
    kimi = {
        "available": True,
        "primary_pct": 25.0,
        "weekly_pct": 12.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
    }
    out = format_detail(None, None, kimi)
    assert "Claude" not in out
    assert "ChatGPT" not in out
    assert "Kimi Code" in out
    assert "25.0%" in out


def test_only_claude_skips_chatgpt_and_kimi_sections():
    out = format_detail(_base_summary(), None, None)
    assert "Claude" in out
    assert "ChatGPT" not in out
    assert "Kimi Code" not in out


def test_only_chatgpt_skips_claude_and_kimi_sections():
    openai = {"available": True, "primary_pct": 30.0, "review_pct": 5.0}
    out = format_detail(None, openai, None)
    assert "Claude" not in out
    assert "ChatGPT Plus" in out
    assert "Kimi Code" not in out
    assert "30.0%" in out


def test_empty_summary_dict_skips_claude_section():
    out = format_detail({}, {"available": False, "error": "x"}, None)
    assert "Claude" not in out
    assert "ChatGPT Plus" in out


def test_no_args_returns_empty_string():
    assert format_detail() == ""
    assert format_detail(None, None, None) == ""


def test_sections_separated_by_blank_line():
    openai = {"available": True, "primary_pct": 30.0, "review_pct": 5.0}
    kimi = {"available": True, "primary_pct": 18.0, "weekly_pct": 10.0}
    out = format_detail(_base_summary(), openai, kimi)
    assert "\n\n" in out
    parts = out.split("\n\n")
    assert any("Claude" in p for p in parts)
    assert any("ChatGPT" in p for p in parts)
    assert any("Kimi" in p for p in parts)


def test_opencode_section_rendered_when_provided():
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "primary_pct": 18.0,
        "weekly_pct": 12.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
        "primary_tokens": 18000,
        "primary_limit_tokens": 100000,
        "weekly_tokens": 60000,
        "weekly_limit_tokens": 500000,
    }
    out = format_detail(_base_summary(), None, None, opencode)
    assert "OpenCode" in out
    assert "18.0%" in out
    assert "12.0%" in out
    assert "18,000" in out
    assert "60,000" in out
    assert "(rolling)" in out


def test_opencode_unavailable():
    opencode = {"available": False, "error": "no db"}
    out = format_detail(_base_summary(), None, None, opencode)
    assert "OpenCode" in out
    assert "no db" in out


def test_only_opencode_skips_other_sections():
    opencode = {"available": True, "provider_id": "opencode", "primary_pct": 25.0, "weekly_pct": 5.0}
    out = format_detail(None, None, None, opencode)
    assert "Claude" not in out
    assert "ChatGPT" not in out
    assert "Kimi Code" not in out
    assert "OpenCode" in out


def test_opencode_go_section_rendered_when_provided():
    opencode_go = {
        "available": True,
        "provider_id": "opencode-go",
        "primary_pct": 25.0,
        "weekly_pct": 8.0,
    }
    out = format_detail(None, None, None, None, opencode_go)
    assert "OpenCode Go" in out
    assert "opencode-go" in out
    assert "25.0%" in out


def test_opencode_and_go_both_rendered_in_detail():
    opencode = {"available": True, "provider_id": "opencode", "primary_pct": 5.0, "weekly_pct": 1.0}
    opencode_go = {"available": True, "provider_id": "opencode-go", "primary_pct": 25.0, "weekly_pct": 8.0}
    out = format_detail(None, None, None, opencode, opencode_go)
    assert "OpenCode (opencode)" in out
    assert "OpenCode Go (opencode-go)" in out


def test_opencode_monthly_line_when_limit_set():
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "primary_pct": 5.0,
        "weekly_pct": 1.0,
        "monthly_pct": 12.5,
        "monthly_reset_at": 1777820040,
        "monthly_tokens": 125000,
        "monthly_limit_tokens": 1000000,
    }
    out = format_detail(None, None, None, opencode)
    assert "monthly:" in out
    assert "12.5%" in out
    assert "mo tokens:" in out
    assert "125,000" in out
    assert "1,000,000" in out


def test_opencode_monthly_dash_when_limit_unset():
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "primary_pct": 5.0,
        "weekly_pct": 1.0,
        "monthly_tokens": 125000,
        "monthly_limit_tokens": 0,
    }
    out = format_detail(None, None, None, opencode)
    assert "monthly: —" in out
    assert "mo tokens:" in out
    assert "125,000" in out


def test_opencode_monthly_bar_marker():
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "primary_pct": 5.0,
        "weekly_pct": 1.0,
        "monthly_pct": 50.0,
        "monthly_reset_at": 1777820040,
        "monthly_tokens": 500000,
        "monthly_limit_tokens": 1000000,
    }
    out = format_detail(None, None, None, opencode)
    lines = out.split("\n")
    monthly_line = [l for l in lines if "monthly:" in l][0]
    assert "← bar" in monthly_line


def test_expired_five_hour_window():
    s = _base_summary(
        five_hour_pct=0.0,
        five_hour_resets_at=None,
        _five_hour_expired=True,
    )
    out = format_detail(s)
    assert "5-hour:  ?       expired" in out


def test_expired_seven_day_window():
    s = _base_summary(
        seven_day_pct=0.0,
        seven_day_resets_at=None,
        _seven_day_expired=True,
    )
    out = format_detail(s)
    assert "7-day:   ?       expired" in out


def test_local_stats_with_cache_read():
    s = _base_summary(
        local={
            "active_block": {"present": True, "tokens": 50000, "cache_read_tokens": 100000, "models": {}},
            "week": {"messages": 10, "tokens": 100000, "cache_read_tokens": 200000},
            "total_entries": 42,
        }
    )
    out = format_detail(s)
    assert "100,000 cache-read" in out
    assert "200,000 cache-read" in out


def test_claude_bar_marker_on_5h() -> None:
    s = _base_summary(five_hour_pct=60.0, seven_day_pct=30.0)
    out = format_detail(s)
    lines = out.split("\n")
    five_line = [l for l in lines if "5-hour:" in l][0]
    seven_line = [l for l in lines if "7-day:" in l][0]
    assert "← bar" in five_line
    assert "← bar" not in seven_line


def test_claude_bar_marker_on_weekly() -> None:
    s = _base_summary(five_hour_pct=10.0, seven_day_pct=50.0)
    out = format_detail(s)
    lines = out.split("\n")
    five_line = [l for l in lines if "5-hour:" in l][0]
    seven_line = [l for l in lines if "7-day:" in l][0]
    assert "← bar" not in five_line
    assert "← bar" in seven_line


def test_claude_bar_marker_on_weekly_when_5h_expired() -> None:
    s = _base_summary(
        five_hour_pct=0.0,
        five_hour_resets_at=None,
        _five_hour_expired=True,
        seven_day_pct=45.0,
        seven_day_resets_at="2026-04-15T22:00:00+00:00",
    )
    out = format_detail(s)
    lines = out.split("\n")
    assert "expired" in out
    seven_line = [l for l in lines if "7-day:" in l][0]
    assert "← bar" in seven_line


def test_openai_bar_marker_on_primary() -> None:
    openai = {"available": True, "primary_pct": 50.0, "weekly_pct": 20.0}
    out = format_detail(None, openai)
    lines = out.split("\n")
    primary_line = [l for l in lines if "primary:" in l][0]
    weekly_line = [l for l in lines if "weekly:" in l][0]
    assert "← bar" in primary_line
    assert "← bar" not in weekly_line


def test_openai_bar_marker_on_weekly() -> None:
    openai = {"available": True, "primary_pct": 10.0, "weekly_pct": 80.0}
    out = format_detail(None, openai)
    lines = out.split("\n")
    primary_line = [l for l in lines if "primary:" in l][0]
    weekly_line = [l for l in lines if "weekly:" in l][0]
    assert "← bar" not in primary_line
    assert "← bar" in weekly_line


def test_kimi_bar_marker_on_weekly() -> None:
    kimi = {"available": True, "primary_pct": 5.0, "weekly_pct": 25.0}
    out = format_detail(None, None, kimi)
    lines = out.split("\n")
    five_line = [l for l in lines if "5-hour:" in l][0]
    weekly_line = [l for l in lines if "weekly:" in l][0]
    assert "← bar" not in five_line
    assert "← bar" in weekly_line


def test_opencode_bar_marker_on_5h() -> None:
    opencode = {"available": True, "provider_id": "opencode", "primary_pct": 30.0, "weekly_pct": 10.0}
    out = format_detail(None, None, None, opencode)
    lines = out.split("\n")
    five_line = [l for l in lines if "5-hour:" in l][0]
    weekly_line = [l for l in lines if "weekly:" in l][0]
    assert "← bar" in five_line
    assert "← bar" not in weekly_line


def test_opencode_go_bar_marker_on_weekly() -> None:
    opencode_go = {"available": True, "provider_id": "opencode-go", "primary_pct": 0.0, "weekly_pct": 4.1}
    out = format_detail(None, None, None, None, opencode_go)
    lines = out.split("\n")
    five_line = [l for l in lines if "5-hour:" in l][0]
    weekly_line = [l for l in lines if "weekly:" in l][0]
    assert "← bar" not in five_line
    assert "← bar" in weekly_line


def test_fmt_local_time_int_epoch() -> None:
    epoch = 1777233240
    out = _fmt_local_time(epoch)
    assert out != "—"
    assert out != str(epoch)
    assert len(out) == 9
    assert out[3] == " "
    assert out[6] == ":"
    assert out[:3].isalpha()
    assert out[4:6].isdigit()
    assert out[7:9].isdigit()


def test_fmt_local_time_iso_string() -> None:
    out = _fmt_local_time("2026-04-10T14:00:00+00:00")
    assert out != "—"
    assert len(out) == 9
    assert out[3] == " "
    assert out[6] == ":"


def test_fmt_local_time_naive_datetime_assumes_utc() -> None:
    naive = datetime(2026, 4, 10, 14, 0, 0)
    out = _fmt_local_time(naive)
    assert out != "—"
    aware = naive.replace(tzinfo=timezone.utc)
    assert out == _fmt_local_time(aware)


def test_fmt_local_time_none_and_garbage() -> None:
    assert _fmt_local_time(None) == "—"
    assert _fmt_local_time("not a date") == "not a date"


def test_claude_section_with_int_epoch_resets_does_not_crash() -> None:
    s = _base_summary(
        five_hour_resets_at=1777233240,
        seven_day_resets_at=1777820040,
    )
    out = format_detail(s)
    assert "Claude" in out
    assert "5-hour:" in out
    assert "7-day:" in out


def test_opencode_idle_shows_idle_note() -> None:
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "is_idle": True,
        "primary_pct": 0.0,
        "weekly_pct": 0.0,
    }
    out = format_detail(None, None, None, opencode)
    assert "idle" in out
    assert "5-hour:" not in out
    assert "weekly:" not in out


def test_opencode_idle_suppresses_misleading_zero_pct_lines() -> None:
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "is_idle": True,
        "primary_pct": 0.0,
        "weekly_pct": 0.0,
    }
    out = format_detail(None, None, None, opencode)
    assert "5-hour:  0.0%" not in out
    assert "weekly:  0.0%" not in out


def test_opencode_idle_monthly_still_shown() -> None:
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "is_idle": True,
        "primary_pct": 0.0,
        "weekly_pct": 0.0,
        "monthly_pct": 5.0,
        "monthly_reset_at": 1777820040,
        "monthly_tokens": 50000,
        "monthly_limit_tokens": 1000000,
    }
    out = format_detail(None, None, None, opencode)
    assert "idle" in out
    assert "monthly:" in out
    assert "mo tokens" in out
    assert "5-hour:" not in out
    assert "weekly:" not in out


def test_opencode_go_idle_shows_idle_note() -> None:
    opencode_go = {
        "available": True,
        "provider_id": "opencode-go",
        "is_idle": True,
        "primary_pct": 0.0,
        "weekly_pct": 0.0,
    }
    out = format_detail(None, None, None, None, opencode_go)
    assert "idle" in out
    assert "5-hour:" not in out


def test_opencode_fixed_window_shows_fixed_label() -> None:
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "window_kind": "fixed",
        "primary_pct": 10.0,
        "weekly_pct": 5.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
    }
    out = format_detail(None, None, None, opencode)
    assert "(fixed)" in out
    assert "(rolling)" not in out


def test_opencode_fixed_window_no_tilde_in_reset_lines() -> None:
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "window_kind": "fixed",
        "primary_pct": 10.0,
        "weekly_pct": 5.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
    }
    out = format_detail(None, None, None, opencode)
    reset_lines = [ln for ln in out.split("\n") if "resets" in ln]
    for line in reset_lines:
        assert "~" not in line


def test_opencode_rolling_window_keeps_rolling_label() -> None:
    opencode = {
        "available": True,
        "provider_id": "opencode",
        "window_kind": "rolling",
        "primary_pct": 10.0,
        "weekly_pct": 5.0,
        "primary_reset_at": 1777233240,
        "weekly_reset_at": 1777820040,
    }
    out = format_detail(None, None, None, opencode)
    assert "(rolling)" in out
    assert "(fixed)" not in out


def test_local_block_effective_line_shown() -> None:
    s = _base_summary(
        local={
            "active_block": {
                "present": True,
                "tokens": 100,
                "cache_read_tokens": 900,
                "cache_read_weight": 1.0,
                "effective_tokens": 1000,
                "models": {},
            },
            "week": {"messages": 5, "tokens": 500, "cache_read_tokens": 0},
            "total_entries": 10,
        }
    )
    out = format_detail(s)
    assert "effective:" in out
    assert "billed 100" in out
    assert "cache-read 900" in out
    assert "\u00d7 1.0" in out


def test_local_block_effective_not_shown_when_no_cache_read() -> None:
    s = _base_summary(
        local={
            "active_block": {
                "present": True,
                "tokens": 1000,
                "cache_read_tokens": 0,
                "cache_read_weight": 1.0,
                "effective_tokens": 1000,
                "models": {},
            },
            "week": {"messages": 5, "tokens": 500},
            "total_entries": 10,
        }
    )
    out = format_detail(s)
    assert "effective:" not in out


def test_local_week_effective_line_shown() -> None:
    s = _base_summary(
        local={
            "active_block": {"present": False},
            "week": {
                "messages": 10,
                "tokens": 1000,
                "cache_read_tokens": 5000,
                "cache_read_weight": 0.5,
                "effective_tokens": 3500,
            },
            "total_entries": 20,
        }
    )
    out = format_detail(s)
    assert "effective:" in out
    assert "\u00d7 0.5" in out


def test_local_block_effective_fields_absent_no_crash() -> None:
    s = _base_summary(
        local={
            "active_block": {
                "present": True,
                "tokens": 50000,
                "cache_read_tokens": 100000,
                "models": {},
            },
            "week": {"messages": 10, "tokens": 100000, "cache_read_tokens": 200000},
            "total_entries": 42,
        }
    )
    out = format_detail(s)
    assert "effective:" not in out
    assert "100,000 cache-read" in out
